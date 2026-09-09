# -*- coding: utf-8 -*-
"""محلل السيرة الذاتية: استخراج كل المعلومات (من الصورة الشخصية إلى آخر عنصر)
من ملفات DOCX و PDF، مع دعم العربية والفرنسية."""

import io
import os
import re
import unicodedata
import zipfile

from matcher import find_wilaya, scan_text_for_skills

SECTION_KEYWORDS = {
    "summary":       ["نبذة", "الملخص", "الهدف المهني", "الهدف", "profil", "profile", "objectif", "summary", "about"],
    "skills":        ["المهارات", "الكفاءات", "مهارات", "compétences", "competences", "skills"],
    "experience":    ["الخبرة", "الخبرات", "تجربة مهنية", "المسار المهني", "expérience", "experience", "expériences", "experiences"],
    "education":     ["التكوين", "التعليم", "المؤهل العلمي", "الشهادات الدراسية", "formation", "éducation", "education", "études", "etudes"],
    "languages":     ["اللغات", "لغات", "langues", "languages"],
    "certifications": ["شهادات", "certificats", "certifications", "دورات", "تكوين تكميلي", "تكوينات"],
}

DEGREE_WORDS = ["دكتوراه", "ماستر", "ماجستير", "ليسانس", "مهندس دولة", "مهندس تطبيقي", "مهندس",
                "تقني سامي", "تقني عليا", "تقني", "بكالوريا", "دبلوم", "شهادة",
                "ingénieur", "ingenieur", "master", "licence", "doctorat", "bts", "ts ", "bac", "diplôme", "diplome"]

TITLE_HINTS = ["مهندس", "تقني", "محاسب", "مدير", "مسؤول", "ممرض", "طبيب", "أستاذ", "مطور", "مصمم",
               "خبير", "فني", "ingénieur", "ingenieur", "technicien", "comptable", "directeur",
               "responsable", "infirmier", "developpeur", "développeur", "chauffeur", "سائق"]

LANG_DEFS = [
    ("العربية",   ["العربية", "عربية", "arabe", "arabic"]),
    ("الفرنسية",  ["الفرنسية", "فرنسية", "français", "francais", "french"]),
    ("الإنجليزية", ["الإنجليزية", "انجليزية", "anglais", "english"]),
    ("الأمازيغية", ["الأمازيغية", "amazigh", "tamazight", "قبائلية"]),
    ("الألمانية", ["الألمانية", "allemand", "german"]),
    ("الإسبانية", ["الإسبانية", "espagnol", "spanish"]),
    ("الإيطالية", ["الإيطالية", "italien", "italian"]),
    ("التركية",   ["التركية", "turc", "turkish"]),
]


def _clean(text: str) -> str:
    text = unicodedata.normalize("NFKC", text or "")
    text = text.replace("\u200f", "").replace("\u200e", "").replace("\x00", "")
    text = re.sub(r"ـ+", "", text)          # إزالة التطويل
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()


# ─────────────────────────── قراءة الملفات ───────────────────────────

def read_docx(path: str):
    """يرجع (نص كامل، صورة bytes أو None، نوع الصورة)"""
    text_parts = []
    photo = None
    with zipfile.ZipFile(path) as z:
        # الصور: نأخذ أكبر صورة (غالباً الصورة الشخصية)
        best, best_size, best_name = None, 0, ""
        for name in z.namelist():
            if not name.startswith("word/media/"):
                continue
            data = z.read(name)
            if len(data) > best_size and len(data) >= 5 * 1024:
                best, best_size, best_name = data, len(data), name
        if best:
            ext = os.path.splitext(best_name)[1] or ".jpg"
            photo = (best, ext)
        # النص — بترتيب المستند الفعلي (الفقرات والجداول متداخلة)
        try:
            import docx
            from docx.table import Table
            from docx.text.paragraph import Paragraph
            from docx.oxml.ns import qn as _qn
            d = docx.Document(path)
            for child in d.element.body.iterchildren():
                if child.tag == _qn("w:p"):
                    t = Paragraph(child, d).text.strip()
                    if t:
                        text_parts.append(t)
                elif child.tag == _qn("w:tbl"):
                    for row in Table(child, d).rows:
                        for cell in row.cells:
                            for p in cell.paragraphs:
                                if p.text.strip():
                                    text_parts.append(p.text.strip())
        except Exception:
            pass
    return "\n".join(text_parts), photo


def read_pdf(path: str):
    """يرجع (نص كامل، صورة bytes أو None، نوع الصورة)"""
    import pymupdf
    doc = pymupdf.open(path)
    parts = []
    photo = None
    best, best_size = None, 0
    for page in doc:
        parts.append(page.get_text("text"))
        try:
            for img in page.get_images(full=True):
                xref = img[0]
                base = doc.extract_image(xref)
                data = base["image"]
                if len(data) > best_size and base["width"] >= 80 and base["height"] >= 80:
                    best = (data, "." + base.get("ext", "jpg"))
                    best_size = len(data)
        except Exception:
            continue
    doc.close()
    if best and best_size >= 5 * 1024:
        photo = best
    return _clean("\n".join(parts)), photo


def read_cv(path: str):
    ext = os.path.splitext(path)[1].lower()
    if ext == ".docx":
        text, photo = read_docx(path)
        return _clean(text), photo
    elif ext == ".pdf":
        return read_pdf(path)
    else:
        raise ValueError("صيغة غير مدعومة")


# ─────────────────────────── تحليل النص ───────────────────────────

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
PHONE_RE = re.compile(r"(?:\+?\s*213|0)\s*[5-7](?:[\s.\-]*\d){8}")
PHONE_RE2 = re.compile(r"\b0\d(?:[\s.\-]?\d{2}){3,4}\b")
DATE_RE = re.compile(r"\b(?:0?[1-9]|[12]\d|3[01])[/\-.](?:0?[1-9]|1[0-2])[/\-.](19|20)\d{2}\b")
YEAR_SPAN_RE = re.compile(r"(19|20)\d{2}\s*(?:[-–—]|إلى|à|to)\s*((19|20)\d{2}|الآن|present|actuel|ce jour)", re.I)


def _section_slices(lines):
    """يحدد مواضع عناوين الأقسام ويرجع {القسم: قائمة أسطر} — سطر عنوان = قسم واحد فقط"""
    sections = {}
    headers = []
    used_idx = set()
    for i, ln in enumerate(lines):
        if len(ln) > 70:
            continue
        stripped = ln.strip().strip(":•-–— ").strip()
        low = stripped.lower()
        if 0 < len(stripped) <= 45:
            for sec, kws in SECTION_KEYWORDS.items():
                hit = False
                for kw in kws:
                    if kw in low and len(stripped) <= len(kw) + 12:
                        if i not in used_idx:
                            headers.append((i, sec))
                            used_idx.add(i)
                        hit = True
                        break
                if hit:
                    break
    sections["__headers"] = headers
    for idx, (i, sec) in enumerate(headers):
        end = headers[idx + 1][0] if idx + 1 < len(headers) else len(lines)
        sections.setdefault(sec, []).extend(lines[i + 1:end])
    return sections


def _split_entry(line):
    parts = [p.strip() for p in re.split(r"\||؛|;|—|–", line) if p.strip()]
    return parts if len(parts) >= 2 else None


def parse_text(text: str) -> dict:
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    full = "\n".join(lines)
    sections = _section_slices(lines)
    profile = {}

    # البريد الإلكتروني
    m = EMAIL_RE.search(full)
    profile["email"] = m.group(0) if m else ""

    # الهاتف
    m = PHONE_RE.search(full) or PHONE_RE2.search(full)
    profile["phone"] = re.sub(r"\s+", " ", m.group(0)).strip() if m else ""

    # تاريخ الميلاد
    m = DATE_RE.search(full)
    profile["birth_date"] = m.group(0) if m else ""

    # الاسم: أول سطر قبل أول عنوان قسم، بلا أرقام/بريد، من 2 إلى 4 كلمات حرفية
    headers = sections.get("__headers", [])
    first_header = headers[0][0] if headers else min(12, len(lines))
    name = ""
    for ln in lines[:first_header + 2]:
        l2 = re.sub(r"^(الاسم الكامل|الاسم|name|nom et prénom|nom prénom|nom)\s*[:：]\s*", "", ln, flags=re.I)
        l2 = l2.strip()
        if not l2 or EMAIL_RE.search(l2) or PHONE_RE.search(l2) or re.search(r"\d", l2):
            continue
        if l2.lower() in ("curriculum vitae", "cv", "السيرة الذاتية", "سيرة ذاتية"):
            continue
        words = l2.split()
        if 1 < len(words) <= 4 and all(re.match(r"^[\u0600-\u06FFA-Za-z\.\-'’]+$", w) for w in words):
            name = l2
            break
        if len(words) == 1 and re.match(r"^[\u0600-\u06FF]{3,}$", l2) and not name:
            name = l2
    profile["full_name"] = name

    # المسمى الوظيفي
    title = ""
    for ln in lines[:first_header + 6]:
        if any(h in ln for h in TITLE_HINTS) and len(ln) < 70 and not YEAR_SPAN_RE.search(ln):
            title = re.sub(r"^(الوظيفة|المسمى الوظيفي|poste|titre|title|fonction)\s*[:：]\s*", "", ln, flags=re.I).strip()
            break
    profile["title"] = title

    # الملخص
    sum_lines = sections.get("summary", [])
    if sum_lines:
        profile["summary"] = " ".join(sum_lines)[:600]
    else:
        profile["summary"] = ""

    # الولاية / العنوان
    profile["wilaya"] = find_wilaya(full)
    address = ""
    for ln in lines[:first_header + 8]:
        m2 = re.match(r"^(العنوان|adresse|address)\s*[:：]\s*(.+)", ln, flags=re.I)
        if m2:
            address = m2.group(2).strip()
            break
    profile["address"] = address

    # المهارات: من قسم المهارات + مسح شامل للنص
    skills = set()
    for ln in sections.get("skills", []):
        for tok in re.split(r"[,،;؛•/\|]| \- ", ln):
            tok = tok.strip().strip("•-–— ").strip()
            if 2 <= len(tok) <= 40:
                skills.add(tok)
    skills_found = scan_text_for_skills(full)
    all_sk = list(skills) + sorted(skills_found)
    # إزالة التكرار القياسي
    from matcher import canonical_of, _ALIASES, canon_key
    seen = set()
    final_skills = []
    for s in all_sk:
        c = canonical_of(s) or normkey(s)
        if c.lower() in seen:
            continue
        seen.add(c.lower())
        final_skills.append(s if not canonical_of(s) else canonical_of(s))
    profile["skills"] = final_skills[:20]

    # اللغات (لكل لغة مستواها الخاص في السطر)
    langs = []
    lang_src = sections.get("languages", [])
    scan_src = lang_src if lang_src else lines[:10] + lines[-8:]
    for ln in scan_src:
        low = ln.lower()
        for label, aliases in LANG_DEFS:
            if any(a in low for a in aliases):
                # ابحث عن المستوى بعد موضع ذكر اللغة في السطر
                pos = min((low.find(a) for a in aliases if a in low), default=0)
                after = low[pos + 2:]
                lvl = ""
                m3 = re.search(r"(لغة أم|ممتازة?|جيد جدا|جيد|متوسط|بداية|natif\(e\)?|bilingue|courant|bon|bien|intermédiaire|intermediaire|notions|débutant)", after)
                if m3:
                    lvl = m3.group(1)
                entry = f"{label}: {lvl}" if lvl else label
                if entry not in langs:
                    langs.append(entry)
    profile["languages"] = langs

    # الخبرة المهنية
    experience = []
    exp_lines = sections.get("experience", [])
    for ln in exp_lines:
        if not ln or len(ln) < 4:
            continue
        parts = _split_entry(ln)
        if parts and len(parts) >= 3:
            entry = {"role": parts[0], "org": parts[1], "period": parts[2], "desc": parts[3] if len(parts) > 3 else ""}
            experience.append(entry)
        elif YEAR_SPAN_RE.search(ln) or re.search(r"(19|20)\d{2}", ln) or re.search(r"(منذ|depuis|present|الآن)", ln, re.I):
            period_m = YEAR_SPAN_RE.search(ln) or re.search(r"(منذ|depuis)\s*((19|20)\d{2})", ln, re.I)
            period = period_m.group(0) if period_m else ""
            role = ln
            if period:
                role = ln.replace(period, " ").strip(" -–—|،,")
            experience.append({"role": role[:80], "org": "", "period": period, "desc": ""})
    profile["experience"] = experience[:10]

    # التكوين
    education = []
    for ln in sections.get("education", []):
        if not ln or len(ln) < 4:
            continue
        parts = _split_entry(ln)
        if parts and len(parts) >= 2:
            education.append({"degree": parts[0], "school": parts[1], "year": parts[2] if len(parts) > 2 else ""})
        elif any(d in ln for d in DEGREE_WORDS):
            ym = re.search(r"(19|20)\d{2}", ln)
            education.append({"degree": ln[:90], "school": "", "year": ym.group(0) if ym else ""})
    profile["education"] = education[:8]

    # الشهادات والتربصات
    certs = []
    for ln in sections.get("certifications", []):
        for tok in re.split(r"[,،;؛•\|]", ln):
            tok = tok.strip().strip("•-–— ").strip()
            if 3 <= len(tok) <= 60 and tok not in certs:
                certs.append(tok)
    profile["certifications"] = certs[:10]

    # LinkedIn
    m = re.search(r"(?:linkedin\.com/[^\s,;]+)", full, re.I)
    profile["linkedin"] = m.group(0) if m else ""

    return profile


def normkey(s):
    from matcher import norm
    return norm(s).strip()


def extract_all(path: str):
    """المدخل الرئيسي: يرجع (profile dict, photo bytes|None, photo_ext)"""
    text, photo = read_cv(path)
    profile = parse_text(text)
    if photo:
        return profile, photo[0], photo[1]
    return profile, None, None
