# -*- coding: utf-8 -*-
"""المحرك التلقائي:
• بحث دوري كل 12 ساعة عن عروض جديدة + فلترتها لكل مستخدم وخلق «فرص مقترحة»
  جاهزة للترشح الفوري دون أي تدخل من صاحب الحساب.
• تذكير تلقائي بعد أسبوع لكل منصب تم التقدم إليه: تحرير رسالة متابعة + PDF
  وتجهيزها للإرسال آلياً.
"""

import json
import os
import threading
import time
from datetime import datetime, timedelta

from matcher import match_score

SCAN_INTERVAL_SECONDS = 12 * 60 * 60      # كل 12 ساعة
REMINDER_AFTER_DAYS = 7                    # تذكير بعد أسبوع
OPPORTUNITY_MIN_SCORE = 55                 # حد الفلترة


def _now():
    return datetime.utcnow().strftime("%Y-%m-%d %H:%M")


def _publish_new_jobs(conn):
    """يُنشر عدداً من العروض الجديدة من المخزون مع كل دورة بحث (محاكاة الوصول)."""
    pool = conn.execute("SELECT COUNT(*) FROM jobs WHERE is_new=1").fetchone()[0]
    if pool == 0:
        return []
    import db as dbm
    published = []
    rows = conn.execute("SELECT * FROM jobs WHERE is_new=1 ORDER BY id LIMIT 2").fetchall()
    for r in rows:
        conn.execute("UPDATE jobs SET is_new=0, posted_days_ago=0 WHERE id=?", (r["id"],))
        published.append(dbm.job_from_row(r))
    return published


def scan_user(conn, uid, published=None):
    """يفلتر العروض لمستخدم محدد ويضيف الفرص المقترحة الجديدة. يرجع عددها."""
    import db as dbm
    user = dbm.user_from_row(conn.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone())
    if not user:
        return 0
    created = 0
    rows = conn.execute("SELECT * FROM jobs").fetchall()
    existing = {r["job_id"] for r in conn.execute(
        "SELECT job_id FROM opportunities WHERE user_id=?", (uid,)).fetchall()}
    for r in rows:
        if r["id"] in existing:
            continue
        job = dbm.job_from_row(r)
        score, matched, _ = match_score(user, job)
        if score >= OPPORTUNITY_MIN_SCORE:
            conn.execute("""INSERT OR IGNORE INTO opportunities (user_id, job_id, score, matched, status, created_at)
                            VALUES (?,?,?,?, 'جديدة', ?)""",
                         (uid, job["id"], score, json.dumps(matched, ensure_ascii=False), _now()))
            created += 1
    return created


def auto_scan():
    """دورة البحث التلقائي الكاملة: نشر الجديد + فلترة لكل المستخدمين."""
    import db as dbm
    summary = {"published": 0, "opportunities": 0, "users": 0}
    conn = dbm.get_db()
    try:
        new_jobs = _publish_new_jobs(conn)
        summary["published"] = len(new_jobs)
        uids = [r["id"] for r in conn.execute("SELECT id FROM users").fetchall()]
        for uid in uids:
            summary["opportunities"] += scan_user(conn, uid, new_jobs)
            summary["users"] += 1
        conn.execute("INSERT OR REPLACE INTO meta (key, value) VALUES ('last_scan', ?)", (_now(),))
        conn.commit()
        for uid in uids:
            dbm.add_activity(uid, "🔎 بحث تلقائي دوري",
                             f"نُشر {summary['published']} عرضاً جديداً — {summary['opportunities']} فرصة مقترحة إجمالاً")
    finally:
        conn.close()
    return summary


def check_reminders():
    """يبحث عن الطلبات المُرسلة التي مضى عليها أسبوع ويحرّر تذكيرات المتابعة آلياً."""
    import db as dbm
    from pdfgen import build_reminder_pdf
    from urllib.parse import quote

    created = 0
    log_entries = []
    conn = dbm.get_db()
    try:
        limit = (datetime.utcnow() - timedelta(days=REMINDER_AFTER_DAYS)).strftime("%Y-%m-%d %H:%M")
        rows = conn.execute("""SELECT a.*, j.title, j.company, j.hr_email, j.city
                               FROM applications a JOIN jobs j ON j.id=a.job_id
                               WHERE a.status='تم الإرسال عبر البريد' AND a.created_at <= ?""",
                            (limit,)).fetchall()
        for a in rows:
            has = conn.execute("SELECT 1 FROM reminders WHERE application_id=?", (a["id"],)).fetchone()
            if has:
                continue
            uid = a["user_id"]
            user = dbm.user_from_row(conn.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone())
            name = user["full_name"] if user else ""
            subject = f"متابعة طلب الترشح لمنصب {a['title']} - {name}"
            body = (f"السلام عليكم،\n\n"
                    f"أودّ المتابعة بخصوص طلب ترشحي لمنصب {a['title']} لدى {a['company']} بـ{a['city']}، "
                    f"المُرسل بتاريخ {a['created_at'][:10]} إلى بريدكم المخصص للتوظيف.\n"
                    f"ما زلت مهتماً بالمنصب وجاهزاً لإجراء مقابلة في أي وقت يناسبكم.\n\n"
                    f"مع فائق الشكر والتقدير.\n{name}")
            mailto = f"mailto:{a['hr_email']}?subject={quote(subject)}&body={quote(body)}"
            # توليد رسالة المتابعة PDF تلقائياً
            pdf_name = f"reminder_u{uid}_j{a['job_id']}.pdf"
            if user:
                try:
                    buf = build_reminder_pdf(user, dict(a), subject, body)
                    docs_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "uploads", "docs")
                    with open(os.path.join(docs_dir, pdf_name), "wb") as fh:
                        fh.write(buf.read())
                except Exception:
                    pdf_name = ""
            conn.execute("""INSERT INTO reminders (user_id, application_id, job_id, subject, body,
                             pdf_path, mailto, status, created_at)
                             VALUES (?,?,?,?,?,?,?, 'جاهزة للإرسال', ?)""",
                         (uid, a["id"], a["job_id"], subject, body, pdf_name, mailto, _now()))
            log_entries.append((uid, f"حان وقت متابعة الترشح لمنصب {a['title']} — {a['company']}"))
            created += 1
        conn.commit()
    finally:
        conn.close()
    for uid, detail in log_entries:
        dbm.add_activity(uid, "⏰ تذكير تلقائي (أسبوع)", detail)
    return {"created": created}


def start_loop():
    """يشغّل حلقة البحث الدورية في خيط خلفي (كل 12 ساعة)."""

    def _loop():
        while True:
            try:
                auto_scan()
                check_reminders()
            except Exception as e:
                print("[scheduler]", e)
            time.sleep(SCAN_INTERVAL_SECONDS)

    t = threading.Thread(target=_loop, daemon=True)
    t.start()
    return t
