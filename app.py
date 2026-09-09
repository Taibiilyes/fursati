# -*- coding: utf-8 -*-
"""فرصتي — منصة البحث عن عروض العمل
التسجيل بالسيرة الذاتية، مطابقة ذكية، بحث تلقائي كل 12 ساعة،
تخصيص آلي للملفات (PDF + Word)، وتذكير تلقائي بعد أسبوع من الترشح."""

import base64
import json
import os
import re
import shutil
import time
import uuid
from urllib.parse import quote

from flask import (Flask, abort, flash, redirect, render_template, request,
                   send_file, send_from_directory, session, url_for)
from werkzeug.security import check_password_hash, generate_password_hash

import db as dbm
import scheduler as sch
from cvparser import extract_all
from matcher import (CONTRACTS, SECTORS, SPECIALTIES, WILAYAS_SOUTH,
                     distance_km, match_score, norm)

BASE = os.path.dirname(os.path.abspath(__file__))
UPLOADS = os.path.join(BASE, "uploads")
PHOTOS = os.path.join(UPLOADS, "photos")
CVS = os.path.join(UPLOADS, "cvs")
DOCS = os.path.join(UPLOADS, "docs")
TMP = os.path.join(UPLOADS, "tmp")
for d in (PHOTOS, CVS, DOCS, TMP):
    os.makedirs(d, exist_ok=True)

app = Flask(__name__)
app.secret_key = "fursati-secret-key-2026"
app.config["MAX_CONTENT_LENGTH"] = 12 * 1024 * 1024

dbm.ensure_db()


# ───────────────────────── إعدادات البريد المباشر (SMTP) ─────────────────────────

def get_email_cfg(uid):
    conn = dbm.get_db()
    row = conn.execute("SELECT * FROM email_config WHERE user_id=?", (uid,)).fetchone()
    conn.close()
    if not row:
        return None
    d = dict(row)
    d["password"] = base64.b64decode(d["password_b64"] or "").decode("utf-8", "ignore")
    return d


# ───────────────────────── أدوات عامة ─────────────────────────

def current_user():
    uid = session.get("uid")
    if not uid:
        return None
    conn = dbm.get_db()
    row = conn.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
    conn.close()
    return dbm.user_from_row(row)


def login_required(f):
    from functools import wraps
    @wraps(f)
    def wrapper(*a, **kw):
        if not current_user():
            flash("سجّل الدخول أولاً للوصول إلى هذه الصفحة.", "warn")
            return redirect(url_for("login"))
        return f(*a, **kw)
    return wrapper


def jobs_all():
    conn = dbm.get_db()
    rows = conn.execute("SELECT * FROM jobs ORDER BY posted_days_ago ASC, id DESC").fetchall()
    conn.close()
    return [dbm.job_from_row(r) for r in rows]


def job_by_id(jid):
    conn = dbm.get_db()
    row = conn.execute("SELECT * FROM jobs WHERE id=?", (jid,)).fetchone()
    conn.close()
    return dbm.job_from_row(row)


def enrich(jobs, user):
    if not user:
        for j in jobs:
            j["score"] = None
        return jobs
    for j in jobs:
        s, m, miss = match_score(user, j)
        j["score"], j["matched"] = s, m
    return jobs


def profile_completeness(u):
    fields = ["full_name", "email", "phone", "title", "summary", "wilaya",
              "photo", "skills", "languages", "experience", "education"]
    filled = sum(1 for f in fields if u.get(f))
    return int(filled / len(fields) * 100)


def _counts():
    u = current_user()
    if not u:
        return {"opp_new": 0, "rem_pending": 0}
    conn = dbm.get_db()
    opp_new = conn.execute("SELECT COUNT(*) FROM opportunities WHERE user_id=? AND status='جديدة'",
                           (u["id"],)).fetchone()[0]
    rem = conn.execute("SELECT COUNT(*) FROM reminders WHERE user_id=? AND status='جاهزة للإرسال'",
                       (u["id"],)).fetchone()[0]
    conn.close()
    return {"opp_new": opp_new, "rem_pending": rem}


@app.context_processor
def inject_badges():
    return _counts()


@app.template_filter("ago")
def ago_filter(days):
    if days is None:
        return ""
    if days <= 0:
        return "اليوم"
    if days == 1:
        return "منذ يوم"
    if days <= 10:
        return f"منذ {days} أيام"
    return f"منذ {days} يوماً"


@app.template_filter("dt")
def dt_filter(s):
    return (s or "").replace("-", "/").replace("T", " ")


# ───────────────────────── صفحات عامة ─────────────────────────

@app.route("/")
def index():
    user = current_user()
    jobs = jobs_all()
    latest = enrich(jobs[:6], user)
    stats = {"jobs": len(jobs), "companies": len({j["company"] for j in jobs}),
             "wilayas": len({j["wilaya"] for j in jobs})}
    return render_template("index.html", user=user, latest=latest, stats=stats)


@app.route("/sample-cv")
def sample_cv():
    return send_file(os.path.join(BASE, "static", "samples", "cv_modele.docx"),
                     as_attachment=True, download_name="نموذج_سيرة_ذاتية.docx")


# ───────────────────────── التسجيل عبر السيرة الذاتية ─────────────────────────

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        f = request.files.get("cv")
        if not f or not f.filename:
            flash("المرجو تحميل ملف السيرة الذاتية (DOCX أو PDF).", "err")
            return redirect(url_for("register"))
        ext = os.path.splitext(f.filename)[1].lower()
        if ext not in (".docx", ".pdf"):
            flash("صيغة غير مدعومة. يُقبل DOCX (الأفضل) أو PDF.", "err")
            return redirect(url_for("register"))
        tmp_name = f"cv_{uuid.uuid4().hex[:10]}{ext}"
        tmp_path = os.path.join(TMP, tmp_name)
        f.save(tmp_path)
        try:
            profile, photo_bytes, photo_ext = extract_all(tmp_path)
        except Exception:
            profile, photo_bytes, photo_ext = {}, None, None
        if not profile.get("full_name") and not profile.get("email"):
            flash("لم نتمكن من قراءة بيانات وافية من هذا الملف. جرّب ملف DOCX أو نزّل نموذجنا الجاهز.", "err")
            return redirect(url_for("register"))
        photo_file = ""
        if photo_bytes:
            photo_file = f"photo_{uuid.uuid4().hex[:10]}{photo_ext}"
            with open(os.path.join(TMP, photo_file), "wb") as fh:
                fh.write(photo_bytes)
        profile["_tmp_cv"] = tmp_name
        profile["_photo_file"] = photo_file
        session["pending"] = profile
        return redirect(url_for("register_review"))

    return render_template("register.html", user=None)


@app.route("/register/review", methods=["GET", "POST"])
def register_review():
    p = session.get("pending")
    if not p:
        return redirect(url_for("register"))
    if request.method == "POST":
        form = request.form
        email = form.get("email", "").strip().lower()
        password = form.get("password", "")
        if not email or "@" not in email:
            flash("البريد الإلكتروني غير صالح.", "err")
            return render_template("review.html", p=p, wilayas=WILAYAS_SOUTH, user=None)
        if len(password or "") < 6:
            flash("كلمة المرور يجب أن تكون 6 أحرف على الأقل.", "err")
            return render_template("review.html", p=p, wilayas=WILAYAS_SOUTH, user=None)
        conn = dbm.get_db()
        exists = conn.execute("SELECT id FROM users WHERE email=?", (email,)).fetchone()
        if exists:
            conn.close()
            flash("هذا البريد مسجّل مسبقاً، سجّل الدخول مباشرة.", "warn")
            return redirect(url_for("login"))

        skills = [s.strip() for s in re.split(r"[,،]", form.get("skills", "")) if s.strip()]
        languages = [l.strip() for l in form.get("languages", "").split("\n") if l.strip()]
        certs = [s.strip() for s in re.split(r"[,،]", form.get("certifications", "")) if s.strip()]
        interests = [i.strip() for i in form.get("interests", "").split("\n") if i.strip()]
        experience = []
        for line in form.get("experience", "").split("\n"):
            parts = [x.strip() for x in line.split("|") if x.strip()]
            if parts:
                experience.append({"role": parts[0] if len(parts) > 0 else "",
                                   "org": parts[1] if len(parts) > 1 else "",
                                   "period": parts[2] if len(parts) > 2 else "",
                                   "desc": parts[3] if len(parts) > 3 else ""})
        education = []
        for line in form.get("education", "").split("\n"):
            parts = [x.strip() for x in line.split("|") if x.strip()]
            if parts:
                education.append({"degree": parts[0] if len(parts) > 0 else "",
                                  "school": parts[1] if len(parts) > 1 else "",
                                  "year": parts[2] if len(parts) > 2 else ""})
        now = time.strftime("%Y-%m-%d %H:%M")
        cur = conn.execute("""INSERT INTO users
            (full_name,email,password_hash,phone,title,summary,wilaya,address,birth_date,
             photo,skills,languages,experience,education,certifications,interests,linkedin,cv_file,created_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (form.get("full_name", ""), email, generate_password_hash(password),
             form.get("phone", ""), form.get("title", ""), form.get("summary", ""),
             form.get("wilaya", ""), form.get("address", ""), form.get("birth_date", ""),
             "", json.dumps(skills, ensure_ascii=False),
             json.dumps(languages, ensure_ascii=False),
             json.dumps(experience, ensure_ascii=False),
             json.dumps(education, ensure_ascii=False),
             json.dumps(certs, ensure_ascii=False),
             json.dumps(interests, ensure_ascii=False),
             p.get("linkedin", ""), "", now))
        uid = cur.lastrowid
        photo_file = p.get("_photo_file", "")
        if photo_file and os.path.exists(os.path.join(TMP, photo_file)):
            dest = f"u{uid}{os.path.splitext(photo_file)[1]}"
            shutil.move(os.path.join(TMP, photo_file), os.path.join(PHOTOS, dest))
            conn.execute("UPDATE users SET photo=? WHERE id=?", (dest, uid))
        tmp_cv = p.get("_tmp_cv", "")
        if tmp_cv and os.path.exists(os.path.join(TMP, tmp_cv)):
            shutil.move(os.path.join(TMP, tmp_cv), os.path.join(CVS, f"u{uid}{os.path.splitext(tmp_cv)[1]}"))
        conn.commit()
        conn.close()
        session.pop("pending", None)
        session["uid"] = uid

        # سجل النشاط + بحث فوري عن الفرص المطابقة للمستخدم الجديد
        dbm.add_activity(uid, "✅ إنشاء الحساب",
                         "استُخرجت كافة المعلومات من السيرة الذاتية وتم إنشاء الحساب بنجاح")
        try:
            conn2 = dbm.get_db()
            n = sch.scan_user(conn2, uid)
            conn2.commit()
            conn2.close()
            if n:
                dbm.add_activity(uid, "🎯 فرص مقترحة جديدة",
                                 f"وُجدت {n} فرصة مطابقة لسيرتك — جاهزة للترشح الفوري")
        except Exception:
            pass

        flash(f"مرحباً {form.get('full_name','')}! تم إنشاء حسابك من سيرتك الذاتية بنجاح 🎉", "ok")
        return redirect(url_for("dashboard"))

    return render_template("review.html", p=p, wilayas=WILAYAS_SOUTH, user=None)


@app.route("/tmp-photo/<name>")
def tmp_photo(name):
    safe = os.path.basename(name)
    return send_from_directory(TMP, safe)


# ───────────────────────── الدخول والخروج ─────────────────────────

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        conn = dbm.get_db()
        row = conn.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
        conn.close()
        if row and check_password_hash(row["password_hash"], password):
            session["uid"] = row["id"]
            dbm.add_activity(row["id"], "🔑 تسجيل دخول", "دخول ناجح إلى الحساب")
            flash(f"أهلاً بعودتك {row['full_name']}!", "ok")
            return redirect(url_for("dashboard"))
        flash("بيانات الدخول غير صحيحة.", "err")
    return render_template("login.html", user=None)


DEMO_EMAIL = "amine.final2@example.dz"


@app.route("/demo-login")
def demo_login():
    """دخول مباشر بضغطة واحدة بالحساب التجريبي الجاهز."""
    conn = dbm.get_db()
    row = conn.execute("SELECT * FROM users WHERE email=?", (DEMO_EMAIL,)).fetchone()
    conn.close()
    if not row:
        flash("الحساب التجريبي غير متوفر حالياً — سجّل بسيرتك الذاتية بدلاً من ذلك.", "warn")
        return redirect(url_for("register"))
    session["uid"] = row["id"]
    dbm.add_activity(row["id"], "🔑 دخول مباشر", "دخول فوري بضغطة واحدة إلى الحساب التجريبي")
    flash(f"تم تسجيل دخولك مباشرة — أهلاً {row['full_name']}! 👋 استكشف فرصك المقترحة", "ok")
    return redirect(url_for("dashboard"))


@app.route("/logout")
def logout():
    session.clear()
    flash("تم تسجيل الخروج.", "ok")
    return redirect(url_for("index"))


# ───────────────────────── الوظائف والبحث ─────────────────────────

@app.route("/jobs")
def jobs_page():
    user = current_user()
    jobs = jobs_all()
    q = request.args.get("q", "").strip()
    wilaya = request.args.get("wilaya", "")
    sector = request.args.get("sector", "")
    contract = request.args.get("contract", "")
    specialty = request.args.get("specialty", "")
    near = request.args.get("near", "")
    sort = request.args.get("sort", "recent")

    if q:
        jobs = [j for j in jobs if q in norm(j["title"] + " " + j["company"] + " " + j["description"])]
    if wilaya:
        jobs = [j for j in jobs if j["wilaya"] == wilaya]
    if sector:
        jobs = [j for j in jobs if j["sector"] == sector]
    if contract:
        jobs = [j for j in jobs if j["contract"] == contract]
    if specialty:
        from matcher import canonical_of
        jobs = [j for j in jobs
                if specialty in [(canonical_of(r) or r) for r in j["requirements"]]]

    jobs = enrich(jobs, user)

    # الفرص القريبة من عنوان الإقامة
    dist_note = ""
    if near and user and user.get("wilaya"):
        for j in jobs:
            j["dist"] = distance_km(user["wilaya"], j["wilaya"])
        with_dist = [j for j in jobs if j.get("dist") is not None]
        without = [j for j in jobs if j.get("dist") is None]
        with_dist.sort(key=lambda j: j["dist"])
        jobs = with_dist + without
        if with_dist:
            dist_note = f"مرتبة حسب القرب من إقامتك في {user['wilaya']} — أقربها على بُعد {with_dist[0]['dist']} كم"
    elif near:
        dist_note = "أكمل ولاية إقامتك في ملفك الشخصي لتفعيل ترتيب القرب الجغرافي."

    if sort == "match" and user:
        jobs.sort(key=lambda j: j.get("score") or 0, reverse=True)

    return render_template("jobs.html", user=user, jobs=jobs, wilayas=WILAYAS_SOUTH,
                           sectors=SECTORS, contracts=CONTRACTS, specialties=SPECIALTIES,
                           f={"q": q, "wilaya": wilaya, "sector": sector, "contract": contract,
                              "specialty": specialty, "near": near, "sort": sort},
                           dist_note=dist_note)


@app.route("/jobs/<int:jid>")
def job_page(jid):
    user = current_user()
    job = job_by_id(jid)
    if not job:
        abort(404)
    score, matched, missing = match_score(user, job) if user else (None, [], [])
    applied = False
    if user:
        conn = dbm.get_db()
        applied = conn.execute("SELECT 1 FROM applications WHERE user_id=? AND job_id=?",
                               (user["id"], jid)).fetchone() is not None
        conn.close()
    return render_template("job.html", user=user, job=job, score=score,
                           matched=matched, missing=missing, applied=applied)


# ───────────────────────── لوحة التحكم ─────────────────────────

@app.route("/dashboard")
@login_required
def dashboard():
    user = current_user()
    jobs = enrich(jobs_all(), user)
    jobs.sort(key=lambda j: j.get("score") or 0, reverse=True)
    conn = dbm.get_db()
    napps = conn.execute("SELECT COUNT(*) FROM applications WHERE user_id=?",
                         (user["id"],)).fetchone()[0]
    opps = conn.execute("""SELECT o.*, j.title, j.company, j.city, j.wilaya, j.color, j.hr_email
                           FROM opportunities o JOIN jobs j ON j.id=o.job_id
                           WHERE o.user_id=? AND o.status != 'مستبعدة'
                           ORDER BY o.score DESC, o.created_at DESC LIMIT 3""", (user["id"],)).fetchall()
    opp_total = conn.execute("""SELECT COUNT(*) FROM opportunities
                                WHERE user_id=? AND status != 'مستبعدة'""", (user["id"],)).fetchall()
    reminders = conn.execute("""SELECT r.*, j.title, j.company
                                FROM reminders r JOIN jobs j ON j.id=r.job_id
                                WHERE r.user_id=? AND r.status='جاهزة للإرسال'
                                ORDER BY r.created_at DESC""", (user["id"],)).fetchall()
    activity = conn.execute("SELECT * FROM activity_log WHERE user_id=? ORDER BY id DESC LIMIT 6",
                            (user["id"],)).fetchall()
    conn.close()
    top = jobs[:6]
    strong = sum(1 for j in jobs if (j.get("score") or 0) >= 70)
    return render_template("dashboard.html", user=user, top=top, total=len(jobs),
                           strong=strong, napps=napps,
                           completeness=profile_completeness(user),
                           opps=[dict(o) for o in opps],
                           opp_total=len(opp_total),
                           reminders=[dict(r) for r in reminders],
                           activity=[dict(a) for a in activity],
                           last_scan=dbm.get_meta("last_scan", ""))


# ───────────────────────── البحث التلقائي والفرص المقترحة ─────────────────────────

@app.route("/scan", methods=["POST"])
@login_required
def scan_now():
    s = sch.auto_scan()
    r = sch.check_reminders()
    dbm.add_activity(current_user()["id"], "🔎 بحث فوري",
                     f"بحث يدوي: {s['published']} عرضاً جديداً، و{r['created']} تذكير")
    flash(f"اكتمل البحث: نُشر {s['published']} عرضاً جديداً ووُجدت {s['opportunities']} فرصة مقترحة"
          + (f" — وحُرّر {r['created']} تذكير متابعة" if r["created"] else ""), "ok")
    return redirect(request.referrer or url_for("dashboard"))


@app.route("/opportunities")
@login_required
def opportunities():
    user = current_user()
    conn = dbm.get_db()
    rows = conn.execute("""SELECT o.*, j.title, j.company, j.city, j.wilaya, j.color,
                           j.contract, j.salary, j.hr_email, j.posted_days_ago
                           FROM opportunities o JOIN jobs j ON j.id=o.job_id
                           WHERE o.user_id=? AND o.status != 'مستبعدة'
                           ORDER BY o.score DESC, o.created_at DESC""", (user["id"],)).fetchall()
    conn.close()
    opps = []
    for r in rows:
        d = dict(r)
        d["matched"] = json.loads(r["matched"] or "[]")
        opps.append(d)
    # علّم القديم كمشاهد بعد العرض
    conn = dbm.get_db()
    conn.execute("UPDATE opportunities SET status='مقترحة' WHERE user_id=? AND status='جديدة'", (user["id"],))
    conn.commit()
    conn.close()
    return render_template("opportunities.html", user=user, opps=opps,
                           last_scan_a=dbm.get_meta("last_scan", ""))


@app.route("/opportunities/<int:oid>/dismiss", methods=["POST"])
@login_required
def opportunity_dismiss(oid):
    conn = dbm.get_db()
    conn.execute("UPDATE opportunities SET status='مستبعدة' WHERE id=? AND user_id=?",
                 (oid, session["uid"]))
    conn.commit()
    conn.close()
    flash("تم استبعاد الفرصة من قائمتك.", "ok")
    return redirect(url_for("opportunities"))


# ───────────────────────── الترشح والتخصيص ─────────────────────────

def _application(uid, jid):
    conn = dbm.get_db()
    row = conn.execute("SELECT * FROM applications WHERE user_id=? AND job_id=?",
                       (uid, jid)).fetchone()
    if not row:
        conn.execute("INSERT INTO applications (user_id, job_id, status, created_at) VALUES (?,?,?,?)",
                     (uid, jid, "تم تحضير الملفات", time.strftime("%Y-%m-%d %H:%M")))
        conn.commit()
        row = conn.execute("SELECT * FROM applications WHERE user_id=? AND job_id=?",
                           (uid, jid)).fetchone()
    conn.close()
    return dict(row)


@app.route("/apply/<int:jid>")
@login_required
def apply_page(jid):
    user = current_user()
    job = job_by_id(jid)
    if not job:
        abort(404)
    score, matched, missing = match_score(user, job)
    app_row = _application(user["id"], jid)
    subject = f"طلب ترشح لمنصب {job['title']} - {user['full_name']}"
    body = (f"السلام عليكم،\n\n"
            f"أترشح لمنصب {job['title']} المعلن لدى {job['company']} بـ{job['city']}.\n"
            f"أرفقت لكم سيرتي الذاتية ورسالتي التحفيزية المعدّتين خصيصاً لهذا المنصب.\n\n"
            f"الاسم: {user['full_name']}\nالهاتف: {user.get('phone','')}\n\n"
            f"مع فائق الاحترام.")
    mailto = f"mailto:{job['hr_email']}?subject={quote(subject)}&body={quote(body)}"
    cv_ready = app_row.get("cv_path") and os.path.exists(os.path.join(DOCS, os.path.basename(app_row["cv_path"])))
    letter_ready = app_row.get("letter_path") and os.path.exists(os.path.join(DOCS, os.path.basename(app_row["letter_path"])))
    return render_template("apply.html", user=user, job=job, score=score, matched=matched,
                           missing=missing, app_row=app_row, mailto=mailto,
                           cv_ready=cv_ready, letter_ready=letter_ready, mail_cfg=get_email_cfg(user['id']))


@app.route("/apply/<int:jid>/cv")
@login_required
def apply_cv(jid):
    fmt = request.args.get("format", "pdf")
    user, job = current_user(), job_by_id(jid)
    if not job:
        abort(404)
    score, matched, _ = match_score(user, job)
    user2 = dict(user)
    user2["_photo_path"] = f"uploads/photos/{user['photo']}" if user.get("photo") else ""
    if fmt == "docx":
        from tailor import build_tailored_cv
        buf = build_tailored_cv(user2, job, matched)
        fname = f"cv_u{user['id']}_j{jid}.docx"
        dl = f"سيرة_ذاتية_{job['title']}.docx"
    else:
        from pdfgen import build_cv_pdf
        buf = build_cv_pdf(user2, job, matched)
        fname = f"cv_u{user['id']}_j{jid}.pdf"
        dl = f"سيرة_ذاتية_{job['title']}.pdf"
    with open(os.path.join(DOCS, fname), "wb") as fh:
        fh.write(buf.getvalue())
    _application(user["id"], jid)
    conn = dbm.get_db()
    conn.execute("UPDATE applications SET cv_path=?, status=CASE WHEN status='تم الإرسال' THEN status ELSE 'تم تحضير الملفات' END WHERE user_id=? AND job_id=?",
                 (fname, user["id"], jid))
    conn.commit()
    conn.close()
    dbm.add_activity(user["id"], "📄 توليد سيرة مخصّصة",
                     f"سيرة ذاتية ({'Word' if fmt=='docx' else 'PDF'}) لمنصب {job['title']} — {job['company']}")
    flash(f"تم توليد سيرتك الذاتية المخصّصة ({'PDF' if fmt=='pdf' else 'Word'}) ✓", "ok")
    return send_file(os.path.join(DOCS, fname), as_attachment=True, download_name=dl)


@app.route("/apply/<int:jid>/letter")
@login_required
def apply_letter(jid):
    lang = request.args.get("lang", "ar")
    fmt = request.args.get("format", "pdf")
    if lang not in ("ar", "fr"):
        lang = "ar"
    user, job = current_user(), job_by_id(jid)
    if not job:
        abort(404)
    score, matched, _ = match_score(user, job)
    if fmt == "docx":
        from tailor import build_letter
        buf = build_letter(user, job, matched, lang=lang)
        fname = f"letter_{lang}_u{user['id']}_j{jid}.docx"
        dl = f"رسالة_تحفيزية_{job['title']}.docx"
    else:
        from pdfgen import build_letter_pdf
        buf = build_letter_pdf(user, job, matched, lang=lang)
        fname = f"letter_{lang}_u{user['id']}_j{jid}.pdf"
        dl = f"رسالة_تحفيزية_{job['title']}.pdf"
    with open(os.path.join(DOCS, fname), "wb") as fh:
        fh.write(buf.getvalue())
    _application(user["id"], jid)
    conn = dbm.get_db()
    conn.execute("UPDATE applications SET letter_path=? WHERE user_id=? AND job_id=?",
                 (fname, user["id"], jid))
    conn.commit()
    conn.close()
    dbm.add_activity(user["id"], "✉️ توليد رسالة تحفيزية",
                     f"رسالة ({'عربية' if lang=='ar' else 'فرنسية'} - {'Word' if fmt=='docx' else 'PDF'}) لمنصب {job['title']}")
    flash(f"تم توليد رسالتك التحفيزية المخصّصة ({'PDF' if fmt=='pdf' else 'Word'}) ✓", "ok")
    return send_file(os.path.join(DOCS, fname), as_attachment=True, download_name=dl)


@app.route("/apply/<int:jid>/sent", methods=["POST"])
@login_required
def apply_sent(jid):
    job = job_by_id(jid)
    _application(current_user()["id"], jid)
    conn = dbm.get_db()
    conn.execute("""UPDATE applications SET status='تم الإرسال عبر البريد', sent_at=?
                    WHERE user_id=? AND job_id=?""",
                 (time.strftime("%Y-%m-%d %H:%M"), session["uid"], jid))
    conn.commit()
    conn.close()
    dbm.add_activity(session["uid"], "📤 إرسال طلب الترشح",
                     f"أُرسل الطلب إلى {job['hr_email']} لمنصب {job['title']} — تذكير تلقائي بعد أسبوع")
    flash("أحسنت! تم تسجيل الإرسال — سيحرّر النظام تذكير متابعة تلقائياً بعد أسبوع ⏰", "ok")
    return redirect(url_for("applications"))


@app.route("/applications")
@login_required
def applications():
    user = current_user()
    conn = dbm.get_db()
    rows = conn.execute("""SELECT a.*, j.title, j.company, j.city, j.wilaya, j.hr_email
                           FROM applications a JOIN jobs j ON j.id=a.job_id
                           WHERE a.user_id=? ORDER BY a.created_at DESC""",
                        (user["id"],)).fetchall()
    conn.close()
    return render_template("applications.html", user=user, apps=[dict(r) for r in rows])


# ───────────────────────── التذكيرات التلقائية ─────────────────────────

@app.route("/reminders")
@login_required
def reminders():
    user = current_user()
    conn = dbm.get_db()
    rows = conn.execute("""SELECT r.*, j.title, j.company, j.city, j.color, j.hr_email
                           FROM reminders r JOIN jobs j ON j.id=r.job_id
                           WHERE r.user_id=? ORDER BY r.created_at DESC""", (user["id"],)).fetchall()
    conn.close()
    return render_template("reminders.html", user=user, reminders=[dict(r) for r in rows],
                           mail_cfg=get_email_cfg(user["id"]))


@app.route("/reminders/<int:rid>/sent", methods=["POST"])
@login_required
def reminder_sent(rid):
    conn = dbm.get_db()
    row = conn.execute("SELECT r.*, j.title, j.company FROM reminders r JOIN jobs j ON j.id=r.job_id WHERE r.id=? AND r.user_id=?",
                       (rid, session["uid"])).fetchone()
    conn.execute("UPDATE reminders SET status='تم الإرسال' WHERE id=? AND user_id=?", (rid, session["uid"]))
    conn.commit()
    conn.close()
    if row:
        dbm.add_activity(session["uid"], "📨 إرسال رسالة المتابعة",
                         f"أُرسل التذكير لمنصب {row['title']} — {row['company']}")
    flash("تم تسجيل رسالة المتابعة كمُرسلة ✓", "ok")
    return redirect(url_for("reminders"))


@app.route("/reminders/simulate", methods=["POST"])
@login_required
def reminders_simulate():
    """للتجربة: يحوّل الطلبات المرسلة إلى قبل 8 أيام ويشغّل فحص التذكيرات فوراً."""
    conn = dbm.get_db()
    conn.execute("""UPDATE applications SET created_at=datetime('now','-8 days')
                    WHERE user_id=? AND status='تم الإرسال عبر البريد'""", (session["uid"],))
    conn.commit()
    conn.close()
    r = sch.check_reminders()
    if r["created"]:
        flash(f"⏰ محاكاة مرور أسبوع: حُرّر {r['created']} تذكير متابعة تلقائياً — تجدها أدناه.", "ok")
    else:
        flash("لا توجد طلبات مُرسلة قابلة للتذكير — رشّح لعرض وعلّمه كمُرسَل أولاً.", "warn")
    return redirect(url_for("reminders"))


# ───────────────────────── سجل النشاط ─────────────────────────

@app.route("/activity")
@login_required
def activity():
    user = current_user()
    conn = dbm.get_db()
    rows = conn.execute("SELECT * FROM activity_log WHERE user_id=? ORDER BY id DESC LIMIT 200",
                        (user["id"],)).fetchall()
    conn.close()
    return render_template("activity.html", user=user, logs=[dict(r) for r in rows])


# ───────────────────────── الملف الشخصي ─────────────────────────

def _parse_textarea_lists(form):
    skills = [s.strip() for s in re.split(r"[,،]", form.get("skills", "")) if s.strip()]
    languages = [l.strip() for l in form.get("languages", "").split("\n") if l.strip()]
    certs = [s.strip() for s in re.split(r"[,،]", form.get("certifications", "")) if s.strip()]
    interests = [i.strip() for i in form.get("interests", "").split("\n") if i.strip()]
    experience = []
    for line in form.get("experience", "").split("\n"):
        parts = [x.strip() for x in line.split("|") if x.strip()]
        if parts:
            experience.append({"role": parts[0] if len(parts) > 0 else "",
                               "org": parts[1] if len(parts) > 1 else "",
                               "period": parts[2] if len(parts) > 2 else "",
                               "desc": parts[3] if len(parts) > 3 else ""})
    education = []
    for line in form.get("education", "").split("\n"):
        parts = [x.strip() for x in line.split("|") if x.strip()]
        if parts:
            education.append({"degree": parts[0] if len(parts) > 0 else "",
                              "school": parts[1] if len(parts) > 1 else "",
                              "year": parts[2] if len(parts) > 2 else ""})
    return skills, languages, certs, interests, experience, education


@app.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    user = current_user()
    if request.method == "POST":
        form = request.form
        skills, languages, certs, interests, experience, education = _parse_textarea_lists(form)
        photo = user.get("photo") or ""
        f = request.files.get("photo")
        if f and f.filename:
            ext = os.path.splitext(f.filename)[1].lower() or ".jpg"
            photo = f"u{user['id']}{ext}"
            f.save(os.path.join(PHOTOS, photo))
        conn = dbm.get_db()
        conn.execute("""UPDATE users SET full_name=?, phone=?, title=?, summary=?, wilaya=?,
                        address=?, birth_date=?, photo=?, skills=?, languages=?, experience=?,
                        education=?, certifications=?, interests=? WHERE id=?""",
                     (form.get("full_name", ""), form.get("phone", ""), form.get("title", ""),
                      form.get("summary", ""), form.get("wilaya", ""), form.get("address", ""),
                      form.get("birth_date", ""), photo,
                      json.dumps(skills, ensure_ascii=False),
                      json.dumps(languages, ensure_ascii=False),
                      json.dumps(experience, ensure_ascii=False),
                      json.dumps(education, ensure_ascii=False),
                      json.dumps(certs, ensure_ascii=False),
                      json.dumps(interests, ensure_ascii=False), user["id"]))
        conn.commit()
        conn.close()
        dbm.add_activity(user["id"], "✏️ تحديث الملف الشخصي",
                         f"حُفظت التعديلات: {len(skills)} مهارة، {len(experience)} خبرة، {len(certs)} شهادة، {len(interests)} اهتمام")
        # إعادة الفلترة بعد تعديل المهارات
        try:
            conn2 = dbm.get_db()
            n = sch.scan_user(conn2, user["id"])
            conn2.commit()
            conn2.close()
            if n:
                dbm.add_activity(user["id"], "🎯 فرص مقترحة جديدة",
                                 f"بعد تحديث ملفك: {n} فرصة إضافية مطابقة")
        except Exception:
            pass
        flash("تم حفظ كل التعديلات في ملفك ✓ وجرى تحديث فرصك المقترحة", "ok")
        return redirect(url_for("profile"))
    return render_template("profile.html", user=user, wilayas=WILAYAS_SOUTH)


@app.route("/profile/add-item", methods=["POST"])
@login_required
def profile_add_item():
    """إضافة سريعة لعنصر واحد (مهارة/خبرة/شهادة/اهتمام) من لوحة التحكم."""
    kind = request.form.get("kind", "")
    value = request.form.get("value", "").strip()
    user = current_user()
    if not value:
        return redirect(url_for("dashboard"))
    conn = dbm.get_db()
    labels = {"skill": "مهارة", "cert": "شهادة عمل", "interest": "اهتمام",
              "degree": "دبلوم", "experience": "خبرة"}
    if kind == "skill" and value not in user["skills"]:
        user["skills"].append(value)
        conn.execute("UPDATE users SET skills=? WHERE id=?",
                     (json.dumps(user["skills"], ensure_ascii=False), user["id"]))
    elif kind == "cert" and value not in user["certifications"]:
        user["certifications"].append(value)
        conn.execute("UPDATE users SET certifications=? WHERE id=?",
                     (json.dumps(user["certifications"], ensure_ascii=False), user["id"]))
    elif kind == "interest" and value not in user["interests"]:
        user["interests"].append(value)
        conn.execute("UPDATE users SET interests=? WHERE id=?",
                     (json.dumps(user["interests"], ensure_ascii=False), user["id"]))
    elif kind == "degree" and not any(d["degree"] == value for d in user["education"]):
        user["education"].append({"degree": value, "school": "", "year": ""})
        conn.execute("UPDATE users SET education=? WHERE id=?",
                     (json.dumps(user["education"], ensure_ascii=False), user["id"]))
    elif kind == "experience":
        parts = [x.strip() for x in value.split("|") if x.strip()]
        user["experience"].append({"role": parts[0] if len(parts) > 0 else "",
                                   "org": parts[1] if len(parts) > 1 else "",
                                   "period": parts[2] if len(parts) > 2 else "",
                                   "desc": parts[3] if len(parts) > 3 else ""})
        conn.execute("UPDATE users SET experience=? WHERE id=?",
                     (json.dumps(user["experience"], ensure_ascii=False), user["id"]))
    conn.commit()
    conn.close()
    dbm.add_activity(user["id"], "➕ إضافة من لوحة التحكم",
                     f"أُضيف عنصر جديد ({labels.get(kind, kind)}): {value}")
    flash(f"تمت إضافة {labels.get(kind, 'العنصر')} إلى ملفك ✓", "ok")
    return redirect(url_for("dashboard"))


@app.route("/reupload-cv", methods=["POST"])
@login_required
def reupload_cv():
    f = request.files.get("cv")
    if not f or not f.filename:
        flash("اختر ملف سيرة ذاتية أولاً.", "err")
        return redirect(url_for("profile"))
    ext = os.path.splitext(f.filename)[1].lower()
    if ext not in (".docx", ".pdf"):
        flash("صيغة غير مدعومة (DOCX أو PDF).", "err")
        return redirect(url_for("profile"))
    tmp_path = os.path.join(TMP, f"re_{uuid.uuid4().hex[:8]}{ext}")
    f.save(tmp_path)
    try:
        profile, photo_bytes, photo_ext = extract_all(tmp_path)
    except Exception:
        profile, photo_bytes, photo_ext = {}, None, None
    user = current_user()
    updates = {}
    for k in ("phone", "title", "summary", "wilaya", "address", "birth_date", "linkedin"):
        if profile.get(k):
            updates[k] = profile[k]
    if profile.get("skills"):
        updates["skills"] = json.dumps(profile["skills"], ensure_ascii=False)
    if profile.get("languages"):
        updates["languages"] = json.dumps(profile["languages"], ensure_ascii=False)
    if profile.get("experience"):
        updates["experience"] = json.dumps(profile["experience"], ensure_ascii=False)
    if profile.get("education"):
        updates["education"] = json.dumps(profile["education"], ensure_ascii=False)
    if profile.get("certifications"):
        updates["certifications"] = json.dumps(profile["certifications"], ensure_ascii=False)
    if photo_bytes:
        photo = f"u{user['id']}{photo_ext}"
        with open(os.path.join(PHOTOS, photo), "wb") as fh:
            fh.write(photo_bytes)
        updates["photo"] = photo
    conn = dbm.get_db()
    if updates:
        sets = ", ".join(f"{k}=?" for k in updates)
        conn.execute(f"UPDATE users SET {sets} WHERE id=?", (*updates.values(), user["id"]))
    conn.commit()
    conn.close()
    os.remove(tmp_path)
    dbm.add_activity(user["id"], "🔄 تحديث من سيرة ذاتية جديدة",
                     f"استُخرجت المعلومات الجديدة وحُدّث الملف ({len(updates)} حقل)")
    flash("تم استخراج المعلومات الجديدة من سيرتك وتحديث ملفك ✓", "ok")
    return redirect(url_for("profile"))


# ───────────────────────── ملفات ─────────────────────────

@app.route("/uploads/photos/<name>")
def photos(name):
    return send_from_directory(PHOTOS, os.path.basename(name))


@app.route("/uploads/docs/<name>")
def docs(name):
    return send_from_directory(DOCS, os.path.basename(name), as_attachment=True)


# ───────────────────────── تطبيق الهاتف (PWA) ─────────────────────────

@app.route("/manifest.json")
def manifest():
    return send_file(os.path.join(BASE, "static", "manifest.json"),
                     mimetype="application/manifest+json")


@app.route("/sw.js")
def sw():
    resp = send_file(os.path.join(BASE, "static", "sw.js"), mimetype="text/javascript")
    resp.headers["Service-Worker-Allowed"] = "/"
    return resp


@app.route("/offline")
def offline():
    return render_template("offline.html", user=current_user())


# ───────────────────────── ربط البريد والإرسال المباشر ─────────────────────────

@app.route("/settings/email", methods=["GET", "POST"])
@login_required
def settings_email():
    from mailer import PROVIDERS
    user = current_user()
    cfg = get_email_cfg(user["id"])
    if request.method == "POST":
        provider = request.form.get("provider", "gmail")
        label, host, port = PROVIDERS.get(provider, PROVIDERS["gmail"])
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "").strip()
        if provider == "custom":
            host = request.form.get("host", "").strip()
            try:
                port = int(request.form.get("port", "587"))
            except ValueError:
                port = 587
        if "@" not in email:
            flash("البريد الإلكتروني غير صالح.", "err")
            return redirect(url_for("settings_email"))
        pw = password if password else (cfg["password"] if cfg else "")
        conn = dbm.get_db()
        conn.execute("""INSERT INTO email_config (user_id, provider, provider_label, email,
                        password_b64, host, port, created_at) VALUES (?,?,?,?,?,?,?,?)
                        ON CONFLICT(user_id) DO UPDATE SET provider=excluded.provider,
                        provider_label=excluded.provider_label, email=excluded.email,
                        password_b64=excluded.password_b64, host=excluded.host, port=excluded.port""",
                     (user["id"], provider, label, email,
                      base64.b64encode(pw.encode()).decode(), host, port,
                      time.strftime("%Y-%m-%d %H:%M")))
        conn.commit()
        conn.close()
        dbm.add_activity(user["id"], "🔗 ربط البريد الإلكتروني",
                         f"وُصل بريد {email} عبر {label} ({host}:{port}) للإرسال المباشر")
        flash("تم ربط بريدك بنجاح ✓ — زر «إرسال مباشر» متاح الآن في كل عرض عمل", "ok")
        return redirect(url_for("settings_email"))
    return render_template("settings_email.html", user=user, cfg=cfg, providers=PROVIDERS)


@app.route("/settings/email/test", methods=["POST"])
@login_required
def email_test():
    from mailer import PROVIDERS, test_connection
    provider = request.form.get("provider", "gmail")
    label, host, port = PROVIDERS.get(provider, PROVIDERS["gmail"])
    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "").strip()
    if provider == "custom":
        host = request.form.get("host", "").strip()
        try:
            port = int(request.form.get("port", "587"))
        except ValueError:
            port = 587
    cfg_saved = get_email_cfg(current_user()["id"])
    cfg = {"email": email, "password": password or (cfg_saved["password"] if cfg_saved else ""),
           "host": host, "port": port}
    ok, msg = test_connection(cfg)
    flash(("✅ " if ok else "⚠ ") + msg, "ok" if ok else "err")
    return redirect(url_for("settings_email"))


def _ensure_apply_pdfs(user, job, matched):
    """يضمن وجود السيرة والرسالة PDF — ويولّدهما إن لم يكونا جاهزين."""
    cv_name = f"cv_u{user['id']}_j{job['id']}.pdf"
    letter_name = f"letter_ar_u{user['id']}_j{job['id']}.pdf"
    cv_path = os.path.join(DOCS, cv_name)
    letter_path = os.path.join(DOCS, letter_name)
    if not os.path.exists(cv_path):
        from pdfgen import build_cv_pdf
        u2 = dict(user)
        u2["_photo_path"] = f"uploads/photos/{user['photo']}" if user.get("photo") else ""
        with open(cv_path, "wb") as fh:
            fh.write(build_cv_pdf(u2, job, matched).read())
    if not os.path.exists(letter_path):
        from pdfgen import build_letter_pdf
        with open(letter_path, "wb") as fh:
            fh.write(build_letter_pdf(user, job, matched, "ar").read())
    return cv_path, letter_path, cv_name, letter_name


@app.route("/apply/<int:jid>/send-email", methods=["POST"])
@login_required
def apply_send_email(jid):
    from mailer import error_message, send_mail
    user, job = current_user(), job_by_id(jid)
    if not job:
        abort(404)
    cfg = get_email_cfg(user["id"])
    if not cfg:
        flash("اربط بريدك أولاً من صفحة «ربط البريد» ثم جرّب الإرسال المباشر.", "warn")
        return redirect(url_for("settings_email"))
    score, matched, _ = match_score(user, job)
    try:
        cv_path, letter_path, cv_name, letter_name = _ensure_apply_pdfs(user, job, matched)
        subject = f"طلب ترشح لمنصب {job['title']} - {user['full_name']}"
        body = (f"السلام عليكم،\n\n"
                f"أترشح لمنصب {job['title']} المعلن لدى {job['company']} بـ{job['city']} ({job['wilaya']}).\n"
                f"أرفقت لكم سيرتي الذاتية ورسالتي التحفيزية المعدّتين خصيصاً لهذا المنصب.\n\n"
                f"الاسم: {user['full_name']}\nالهاتف: {user.get('phone','')}\nالبريد: {cfg['email']}\n\n"
                f"مع فائق الاحترام.")
        send_mail(cfg, f"{user['full_name']} — ترشح لمنصب {job['title']}", job["hr_email"],
                  subject, body,
                  attachments=[(cv_path, f"سيرة_ذاتية_{job['title']}.pdf"),
                               (letter_path, f"رسالة_تحفيزية_{job['title']}.pdf")])
    except Exception as e:  # noqa: BLE001
        dbm.add_activity(user["id"], "⚠️ فشل الإرسال المباشر",
                         f"منصب {job['title']}: {error_message(e)}", ok=0)
        flash("⚠ " + error_message(e), "err")
        return redirect(url_for("apply_page", jid=jid))

    _application(user["id"], jid)
    conn = dbm.get_db()
    conn.execute("""UPDATE applications SET status='تم الإرسال المباشر عبر البريد', sent_at=?
                    WHERE user_id=? AND job_id=?""",
                 (time.strftime("%Y-%m-%d %H:%M"), user["id"], jid))
    conn.execute("""UPDATE opportunities SET status='مُرشَّح' WHERE user_id=? AND job_id=?""",
                 (user["id"], jid))
    conn.commit()
    conn.close()
    dbm.add_activity(user["id"], "🚀 إرسال مباشر ناجح",
                     f"أُرسل الطلب آلياً من {cfg['email']} إلى {job['hr_email']} مع سيرة + رسالة PDF — منصب {job['title']}")
    flash(f"🚀 أُرسل طلب ترشحك مباشرة إلى {job['hr_email']} مع إرفاق السيرة والرسالة — وسيأتي تذكير المتابعة بعد أسبوع تلقائياً", "ok")
    return redirect(url_for("applications"))


@app.route("/reminders/<int:rid>/send-email", methods=["POST"])
@login_required
def reminder_send_email(rid):
    from mailer import error_message, send_mail
    user = current_user()
    cfg = get_email_cfg(user["id"])
    conn = dbm.get_db()
    r = conn.execute("""SELECT r.*, j.title, j.company, j.hr_email FROM reminders r
                        JOIN jobs j ON j.id=r.job_id WHERE r.id=? AND r.user_id=?""",
                     (rid, user["id"])).fetchone()
    if not r or not cfg:
        conn.close()
        if not cfg:
            flash("اربط بريدك أولاً من صفحة «ربط البريد».", "warn")
            return redirect(url_for("settings_email"))
        abort(404)
    try:
        atts = []
        if r["pdf_path"] and os.path.exists(os.path.join(DOCS, r["pdf_path"])):
            atts.append((os.path.join(DOCS, r["pdf_path"]), "رسالة_متابعة.pdf"))
        send_mail(cfg, user["full_name"], r["hr_email"], r["subject"], r["body"], attachments=atts)
    except Exception as e:  # noqa: BLE001
        conn.close()
        dbm.add_activity(user["id"], "⚠️ فشل إرسال التذكير", error_message(e), ok=0)
        flash("⚠ " + error_message(e), "err")
        return redirect(url_for("reminders"))
    conn.execute("UPDATE reminders SET status='تم الإرسال' WHERE id=?", (rid,))
    conn.commit()
    conn.close()
    dbm.add_activity(user["id"], "📨 تذكير مُرسل مباشرة",
                     f"أُرسل تذكير المتابعة لمنصب {r['title']} — {r['company']}")
    flash("📨 أُرسل تذكير المتابعة مباشرة ✓", "ok")
    return redirect(url_for("reminders"))


@app.errorhandler(404)
def nf(e):
    return render_template("404.html", user=current_user()), 404


if __name__ == "__main__":
    # دورة بحث أولى عند الإقلاع + الحلقة الدورية كل 12 ساعة
    try:
        sch.auto_scan()
        sch.check_reminders()
    except Exception as e:
        print("[startup-scan]", e)
    sch.start_loop()
    app.run(host="0.0.0.0", port=5000, debug=False)
