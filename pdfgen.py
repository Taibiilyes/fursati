# -*- coding: utf-8 -*-
"""مولّد ملفات PDF فاخر للسيرة الذاتية والرسالة التحفيزية
بتشكيل عربي كامل وخطوط Tajawal/Amiri عبر محرك Story في PyMuPDF."""

import io
import os
from datetime import date

import pymupdf

BASE = os.path.dirname(os.path.abspath(__file__))

MONTHS_AR = ["جانفي", "فيفري", "مارس", "أفريل", "ماي", "جوان", "جويلية", "أوت",
             "سبتمبر", "أكتوبر", "نوفمبر", "ديسمبر"]
MONTHS_FR = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août",
             "septembre", "octobre", "novembre", "décembre"]

FONT_CSS = """
@font-face {font-family: taj; src: url(static/fonts/Tajawal-Regular.ttf);}
@font-face {font-family: taj; src: url(static/fonts/Tajawal-Medium.ttf); font-weight: 500;}
@font-face {font-family: taj; src: url(static/fonts/Tajawal-Bold.ttf); font-weight: 700;}
@font-face {font-family: taj; src: url(static/fonts/Tajawal-ExtraBold.ttf); font-weight: 800;}
@font-face {font-family: amiri; src: url(static/fonts/Amiri-Regular.ttf);}
@font-face {font-family: amiri; src: url(static/fonts/Amiri-Bold.ttf); font-weight: 700;}
"""

BASE_CSS = FONT_CSS + """
body { font-family: taj; font-size: 10pt; color: #232B26; }
"""


def _today_ar():
    d = date.today()
    return f"{d.day} {MONTHS_AR[d.month - 1]} {d.year}"


def _today_fr():
    d = date.today()
    return f"{d.day} {MONTHS_FR[d.month - 1]} {d.year}"


def _years_experience(experience):
    import re
    total = 0.0
    for e in experience or []:
        p = e.get("period", "") or ""
        if "-" in p or "–" in p or "إلى" in p:
            yrs = [int(x) for x in re.findall(r"((?:19|20)\d{2})", p)]
            if len(yrs) >= 2:
                total += max(0, yrs[-1] - yrs[0])
        elif re.search(r"منذ|depuis|present|الآن", p, re.I):
            m = re.findall(r"((?:19|20)\d{2})", p)
            if m:
                total += max(0, date.today().year - int(m[0]))
    if total == 0 and experience:
        total = len(experience)
    return int(round(total))


def story_to_pdf(html, css, photo_path=None):
    """يبني PDF من HTML عبر Story — مع إمكانية إدراج الصورة يدوياً بعد البناء."""
    buf = io.BytesIO()
    story = pymupdf.Story(html=html, user_css=css, archive=pymupdf.Archive(BASE))
    writer = pymupdf.DocumentWriter(buf)
    mb = pymupdf.paper_rect("a4")
    where = mb + (0, 0, 0, -18)
    while True:
        dev = writer.begin_page(mb)
        more, _ = story.place(where)
        story.draw(dev)
        writer.end_page()
        if not more:
            break
    writer.close()
    buf.seek(0)
    return buf


# ═══════════════════════ السيرة الذاتية PDF ═══════════════════════

def build_cv_pdf(profile, job, matched):
    esc = lambda s: (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    name = esc(profile.get("full_name") or "مترشح")
    title = esc(profile.get("title") or "")
    contact_parts = [esc(x) for x in [profile.get("phone"), profile.get("email"),
                                      profile.get("wilaya")] if x]
    years = _years_experience(profile.get("experience"))
    years_txt = f"تفوق {years} سنوات في" if years else "في"
    matched_txt = "، ".join(esc(m) for m in (matched or [])[:5]) or "مجال التخصص"

    chips = []
    for s in (profile.get("skills") or [])[:16]:
        if s in (matched or []):
            chips.append(f'<span style="background-color:#FDF3D7; color:#8A6410; font-weight:700">★ {esc(s)}</span>')
        else:
            chips.append(f'<span style="background-color:#E7F2EE; color:#0B4232">{esc(s)}</span>')
    chips_html = "  ".join(chips) if chips else "—"

    def entries(items, k1, k2, k3):
        out = []
        for e in items or []:
            head = f'<p class="ehead">{esc(e.get(k1))}' + \
                   (f' <span class="esub">— {esc(e.get(k2))}</span>' if e.get(k2) else "") + \
                   (f' <span class="eper">{esc(e.get(k3))}</span>' if e.get(k3) else "") + "</p>"
            if e.get("desc"):
                head += f'<p class="edesc">{esc(e["desc"])}</p>'
            out.append(head)
        return "".join(out)

    langs = " • ".join(esc(l) for l in (profile.get("languages") or []))
    certs = " • ".join("◇ " + esc(c) for c in (profile.get("certifications") or []))

    summary = (f"مترشح ذو خبرة {years_txt} مجال «{title or matched_txt}»، أترشح لمنصب {esc(job['title'])} "
               f"لدى {esc(job['company'])} بـ{esc(job['city'])} ({esc(job['wilaya'])}). "
               f"أُتقن الكفاءات الأساسية المطلوبة لهذا المنصب أبرزها: {matched_txt}. "
               f"أسعى للمساهمة في أنشطة {esc(job['company'])} في قطاع {esc(job['sector'])}، "
               f"مع جاهزية كاملة للعمل بنظام {esc(job['contract'])} والاستقرار بالمنطقة.")

    html = f"""
<body>
<div id="band">
  <div id="bname">{name}</div>
  <div id="btitle">{title}</div>
  <div id="bcontact">{'  ✦  '.join(contact_parts)}</div>
</div>
<div id="gold">
  المنصب المستهدف: {esc(job['title'])} &nbsp;—&nbsp; {esc(job['company'])} &nbsp;•&nbsp; {esc(job['city'])} ({esc(job['wilaya'])}) &nbsp;•&nbsp; {esc(job['contract'])}
</div>
<div id="content">
  <img src="{esc(profile.get('_photo_path') or 'static/img/sample_photo.jpg')}" width="92">
  <h2><span class="dot">●</span> الملخص المهني</h2>
  <p class="body">{summary}</p>
  <h2><span class="dot">●</span> المهارات والكفاءات</h2>
  <p>{chips_html}</p>
  <h2><span class="dot">●</span> الخبرة المهنية</h2>
  {entries(profile.get('experience'), 'role', 'org', 'period')}
  <h2><span class="dot">●</span> التكوين والشهادات</h2>
  {entries(profile.get('education'), 'degree', 'school', 'year')}
  <h2><span class="dot">●</span> اللغات</h2>
  <p class="body">{langs}</p>
  {'<h2><span class=\"dot\">●</span> شهادات ودورات</h2><p class=\"body\">' + certs + '</p>' if certs else ''}
</div>
<div id="foot">ملف مخصَّص آلياً لمنصب {esc(job['title'])} — {esc(job['company'])} &nbsp;|&nbsp; وُلِّد في {_today_ar()} عبر منصة «فرصتي»</div>
</body>
"""
    css = BASE_CSS + """
#band { background-color: #0B4232; color: #fff; padding: 18px 22px 14px 22px; }
#bname { font-size: 21pt; font-weight: 800; color: #F5C445; }
#btitle { font-size: 11.5pt; font-weight: 700; color: #FFFFFF; margin-top: 1px;}
#bcontact { font-size: 9pt; color: #C9DED5; margin-top: 3px; }
#gold { background-color: #F5C445; color: #3D2E05; font-size: 9.5pt; font-weight: 700;
        padding: 6px 22px; }
#content { padding: 14px 22px; }
h2 { font-size: 12.5pt; font-weight: 800; color: #0B4232; border-bottom: 1.6px solid #F5C445;
     padding-bottom: 2px; margin: 13px 0 5px 0; }
.dot { color: #A87D1D; font-size: 8pt; }
p { margin: 3px 0; line-height: 1.55; }
.body { font-size: 9.8pt; color: #39413D; }
span.chipx { }
p span { font-size: 9pt; padding: 2px 8px; border-radius: 0; margin: 0 0 2px 2px; }
.ehead { font-weight: 700; font-size: 10.3pt; margin-top: 6px; }
.esub { font-weight: 500; color: #39413D; }
.eper { font-weight: 500; color: #A87D1D; font-size: 9pt; }
.edesc { font-size: 9.3pt; color: #5A6460; margin-top: 0; }
#foot { margin-top: 16px; border-top: 1.2px solid #F5C445; color: #8B948E; font-size: 8pt;
        padding: 6px 22px; text-align: center; }
"""
    return story_to_pdf(html, css)

def build_letter_pdf(profile, job, matched, lang="ar"):
    esc = lambda s: (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    name = esc(profile.get("full_name") or "مترشح")
    years = _years_experience(profile.get("experience"))
    matched_txt = "، ".join(esc(m) for m in (matched or [])[:5]) or "كفاءاتي في مجال التخصص"
    contact = " – ".join(esc(x) for x in [profile.get("phone"), profile.get("email")] if x)

    if lang == "fr":
        years_txt = f"plus de {years} années" if years else "une solide expérience"
        body1 = (f"Très intéressé par le poste de {esc(job['title'])} proposé par {esc(job['company'])} à "
                 f"{esc(job['city'])} ({esc(job['wilaya'])}), je vous soumets ma candidature. Votre entreprise, "
                 f"acteur majeur du secteur « {esc(job['sector'])} » en Algérie, représente pour moi "
                 f"une opportunité concrète de mettre mes compétences au service de projets structurants.")
        body2 = (f"Fort de {years_txt} d'expérience et maîtrisant notamment {matched_txt}, je suis prêt à "
                 f"m'investir pleinement, en {esc(job['contract'])}, et à m'installer dans la région. "
                 f"Mon parcours, détaillé dans le CV ci-joint, correspond aux exigences du poste.")
        body3 = ("Je me tiens à votre disposition pour un entretien afin de vous exposer plus en détail ma "
                 "motivation. Dans l'attente de votre retour, je vous prie d'agréer, Madame, Monsieur, "
                 "l'expression de mes salutations distinguées.")
        html = f"""
<body dir="ltr">
<div id="rule"></div>
<div id="head">
  <table id="ht"><tr>
    <td><div id="name">{name}</div><div id="cinfo">{contact}</div></td>
    <td id="hright"><div id="place">{esc(job['city'])}, le {_today_fr()}</div></td>
  </tr></table>
</div>
<div id="content" dir="ltr">
  <p id="dest">À l'attention du Service Recrutement — <b>{esc(job['company'])}</b><br>
  <span class="mut">📧 {esc(job['hr_email'])}</span></p>
  <p id="obj">Objet : Candidature au poste de {esc(job['title'])}</p>
  <p>Madame, Monsieur,</p>
  <p class="jbody">{body1}</p>
  <p class="jbody">{body2}</p>
  <p class="jbody">{body3}</p>
  <p id="sig">{name}</p>
</div>
<div id="foot">Lettre générée automatiquement pour le poste de {esc(job['title'])} — {esc(job['company'])} | {_today_fr()}</div>
</body>"""
        css = BASE_CSS + """
body { text-align: left; }
#rule { background-color: #F5C445; height: 4px; margin: 0 22px; }
#head { padding: 10px 22px 2px 22px; }
#ht { width: 100%; }
#name { font-size: 14pt; font-weight: 800; color: #0B4232; }
#cinfo { font-size: 8.5pt; color: #5A6460; }
#hright { text-align: right; font-size: 9pt; color: #5A6460; }
#content { padding: 8px 22px; }
#dest { font-size: 10pt; margin: 8px 0; }
.mut { font-size: 8.5pt; color: #5A6460; }
#obj { font-size: 11.5pt; font-weight: 700; color: #A87D1D; border-bottom: 1.2px solid #F5C445;
       padding-bottom: 3px; margin: 10px 0; }
.jbody { font-family: amiri; font-size: 11.5pt; line-height: 1.75; text-align: justify;
         color: #232B26; margin: 7px 0; }
#sig { font-weight: 700; margin-top: 14px; color: #0B4232; }
#foot { border-top: 1px solid #E4E0D5; color: #8B948E; font-size: 7.5pt; padding: 6px 22px;
        margin-top: 18px; }
"""
    else:
        years_txt = f"أكثر من {years} سنوات" if years else "خبرة ميدانية"
        body1 = (f"إنني بكل اهتمام أودّ التقدم لمنصب {esc(job['title'])} المعروض من طرف شركة "
                 f"{esc(job['company'])} بمدينة {esc(job['city'])} ({esc(job['wilaya'])}). وقد لفت انتباهي "
                 f"التزام شركتكم المرموقة في قطاع «{esc(job['sector'])}» بمشاريعها التنموية الكبرى، "
                 f"وهو ما يجسّد طموحي المهني وأرغبت في أن أكون جزءاً منه.")
        body2 = (f"يتيح لي مساري المهني، الممتد لـ{years_txt} في مجال تخصصي، إتقان كفاءات تتوافق مباشرة مع "
                 f"متطلبات المنصب، أبرزها: {matched_txt}. كما أنّ جاهزيتي الكاملة للعمل بنظام "
                 f"{esc(job['contract'])} والاستقرار بمنطقة {esc(job['wilaya'])} تعززان قدرتي على الاندماج "
                 f"الفوري في فرق العمل لديكم.")
        body3 = ("وقد أرفقت لكم سيرتي الذاتية المعدّة خصيصاً لهذا المنصب، وأبقى رهن إشارتكم لإجراء مقابلة "
                 "شخصية أقدّم خلالها دافعياتي ومؤهلاتي عن قرب. وتفضلوا بقبول فائق عبارات الاحترام والتقدير.")
        html = f"""
<body>
<div id="rule"></div>
<div id="head">
  <table id="ht"><tr>
    <td><div id="name">{name}</div><div id="cinfo">{contact} – {esc(profile.get('wilaya') or '')}</div></td>
    <td id="hright"><div id="place">{esc(job['city'])}، في {_today_ar()}</div></td>
  </tr></table>
</div>
<div id="content">
  <p id="dest">إلى السيد(ة) مسؤول التوظيف — <b>{esc(job['company'])}</b><br>
  <span class="mut">📧 البريد الإلكتروني للتوظيف: {esc(job['hr_email'])}</span></p>
  <p id="obj">الموضوع: طلب ترشح لمنصب {esc(job['title'])}</p>
  <p>تحية طيبة وبعد،</p>
  <p class="jbody">{body1}</p>
  <p class="jbody">{body2}</p>
  <p class="jbody">{body3}</p>
  <p id="sig">{name}</p>
</div>
<div id="foot">رسالة مخصَّصة آلياً لمنصب {esc(job['title'])} — {esc(job['company'])} &nbsp;|&nbsp; وُلِّدت في {_today_ar()} عبر منصة «فرصتي»</div>
</body>"""
        css = BASE_CSS + """
#rule { background-color: #F5C445; height: 4px; margin: 0 22px; }
#head { padding: 10px 22px 2px 22px; }
#ht { width: 100%; direction: rtl; }
#ht td { direction: rtl; text-align: right; }
#hright { text-align: left; }
#name { font-size: 14pt; font-weight: 800; color: #0B4232; }
#cinfo { font-size: 8.5pt; color: #5A6460; }
#place { font-size: 9pt; color: #5A6460; }
#content { padding: 8px 22px; }
#dest { font-size: 10.5pt; margin: 8px 0; }
.mut { font-size: 8.5pt; color: #5A6460; }
#obj { font-size: 12pt; font-weight: 700; color: #A87D1D; border-bottom: 1.2px solid #F5C445;
       padding-bottom: 3px; margin: 10px 0; }
.jbody { font-family: amiri; font-size: 12pt; line-height: 1.85; color: #232B26; margin: 7px 0; }
#sig { font-weight: 700; margin-top: 14px; color: #0B4232; }
#foot { border-top: 1px solid #E4E0D5; color: #8B948E; font-size: 8pt; padding: 6px 22px;
        margin-top: 18px; text-align: center; }
"""
    return story_to_pdf(html, css)


# ═══════════════════════ رسالة تذكير المتابعة (بعد أسبوع) ═══════════════════════

def build_reminder_pdf(profile, app_row, subject, body):
    """رسالة متابعة مهذبة لطلب ترشح أُرسل قبل أسبوع — تُولَّد آلياً."""
    esc = lambda s: (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    name = esc(profile.get("full_name") or "مترشح")
    lines = esc(body).replace("\n", "<br>")
    html = f"""
<body>
<div id="rule"></div>
<div id="head">
  <div id="name">{name}</div>
  <div id="cinfo">{esc(profile.get('phone'))} – {esc(profile.get('email'))}</div>
</div>
<div id="content">
  <p id="obj">الموضوع: متابعة طلب ترشح — {esc(subject.split('لمنصب')[-1].strip())}</p>
  <p class="jbody">{lines}</p>
  <p id="sig">{name}</p>
</div>
<div id="foot">تذكير تلقائي أعدّته منصة «فرصتي» بعد أسبوع من إرسال طلب الترشح — {_today_ar()}</div>
</body>"""
    css = BASE_CSS + """
#rule { background-color: #F5C445; height: 4px; margin: 0 22px; }
#head { padding: 10px 22px 2px 22px; }
#name { font-size: 14pt; font-weight: 800; color: #0B4232; }
#cinfo { font-size: 8.5pt; color: #5A6460; }
#content { padding: 8px 22px; }
#obj { font-size: 12pt; font-weight: 700; color: #A87D1D; border-bottom: 1.2px solid #F5C445;
       padding-bottom: 3px; margin: 10px 0; }
.jbody { font-family: amiri; font-size: 12pt; line-height: 1.85; color: #232B26; margin: 7px 0; }
#sig { font-weight: 700; margin-top: 14px; color: #0B4232; }
#foot { border-top: 1px solid #E4E0D5; color: #8B948E; font-size: 8pt; padding: 6px 22px;
        margin-top: 18px; text-align: center; }
"""
    return story_to_pdf(html, css)
