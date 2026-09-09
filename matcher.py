# -*- coding: utf-8 -*-
"""قاموس المهارات ومحرك مطابقة السيرة الذاتية مع العروض."""

import unicodedata

# ── قاموس المهارات: التسمية القياسية ← مرادفات (عربية/فرنسية/إنجليزية) ──
SKILLS = {
    "حفر آبار":        ["حفر", "forage", "drilling", "drill", "workover"],
    "صيانة صناعية":    ["صيانة", "maintenance", "gmao", "صيانة وقائية"],
    "ميكانيك":         ["ميكانيك", "ميكانيكية", "mécanique", "mecanique", "mechanic", "mechanical", "هيدروليك", "hydraulique"],
    "كهرباء":          ["كهرباء", "كهربائي", "كهرومغناطيس", "électricité", "électricité", "electricite", "electrical", "electrique", "كهروميكانيك"],
    "أوتوماتيك":       ["أوتوماتيك", "اوتوماتيك", "أتمتة", "automatisme", "automatique", "plc", "siemens", "step7", "teqnia"],
    "HSE":             ["hse", "سلامة", "sécurité", "securite", "safety", "صحة مهنية", "sst", "أمان صناعي", "hsse"],
    "جودة":            ["جودة", "qualité", "qualite", "quality", "iso 9001", "مراقبة الجودة", "contrôle qualité", "controle qualite"],
    "محاسبة":          ["محاسبة", "comptabilité", "comptabilite", "comptable", "accounting", "دفاتر"],
    "مالية":           ["مالية", "finance", "financière", "financiere", "تحليل مالي", "financial"],
    "موارد بشرية":     ["موارد بشرية", "ressources humaines", "grh", "gestion des ressources humaines", "recrutement", "ادارة الموارد"],
    "لوجستيك":         ["لوجستيك", "لوجيستيك", "logistique", "logistic", "supply chain", "سلسلة التوريد", "مخازن", "stock", "مخزن"],
    "مشتريات":         ["مشتريات", "achats", "achat", "purchasing", "procurement", "شراء"],
    "معلوماتية":       ["معلوماتية", "informatique", "it", "دعم تقني", "support technique", "helpdesk"],
    "برمجة":           ["برمجة", "développement", "developpement", "programming", "developer", "python", "java", "javascript", "php", "html", "c++"],
    "شبكات":           ["شبكات", "réseaux", "reseau", "réseau", "network", "tcp", "fibre", "ألياف بصرية"],
    "قواعد بيانات":    ["قواعد بيانات", "sql", "mysql", "oracle", "database", "postgres"],
    "Office":          ["office", "excel", "اكسل", "word", "بوربوينت", "powerpoint", "vba", "أوفيس"],
    "تحليل بيانات":    ["تحليل بيانات", "data analysis", "analyse de données", "analyse de donnees", "power bi", "tableau", "إحصاء"],
    "GIS":             ["gis", "sig", "arcgis", "qgis", "نظم المعلومات الجغرافية", "géomaticien", "جيوماتيك"],
    "جيولوجيا":        ["جيولوجيا", "géologie", "geologie", "geology", "جيولوجي"],
    "كيمياء":          ["كيمياء", "chimie", "chemistry", "كيميائي", "hydrocarbures", "هيدروكربون"],
    "مخبر":            ["مخبر", "معمل", "laboratoire", "labo", "analyses", "تحاليل"],
    "مساحة":           ["مساحة", "مساح", "topographie", "topographe", "topo", "سرفي"],
    "مدني":            ["مدني", "génie civil", "genie civil", "civil engineering", "btp", "بناء", "أشغال عمومية", "travaux publics", "طرق"],
    "لحام":            ["لحام", "soudure", "welding", "soudeur", "سادلاري"],
    "تبريد وتكييف":    ["تبريد", "تكييف", "froid", "climatisation", "clim", "froid industriel", "chaudière"],
    "طاقة شمسية":      ["طاقة شمسية", "solaire", "photovoltaïque", "photovoltaique", "pv", "طاقات متجددة", "طاقة متجددة", "renouvelable"],
    "زراعة":           ["زراعة", "فلاحة", "agronomie", "agricole", "irrigation", "ري", "زراعي", "زراعيّة", "palmeraie"],
    "صناعات غذائية":   ["صناعات غذائية", "تغذية", "agroalimentaire", "agro", "food", "غذائي"],
    "قيادة رخصة B":    ["permis b", "رخصة السياقة", "رخصة سياقة", "رخصة القيادة", "permis de conduire"],
    "قيادة شاحنات":    ["permis e", "poids lourd", "شاحنة", "شاحنات", "camion", "وزن ثقيل", "super lourd", "سيارة نقل"],
    "إدارة مشاريع":    ["إدارة مشاريع", "gestion de projet", "project management", "pmp", "ms project", "planning"],
    "سكرتارية":        ["سكرتارية", "secrétariat", "secretariat", "إداري", "administratif", "استقبال"],
    "تسويق":           ["تسويق", "marketing", "digital marketing", "إشهار"],
    "مبيعات":          ["مبيعات", "vente", "commercial", "بيع", "développement commercial"],
    "خدمة عملاء":      ["خدمة عملاء", "relation client", "customer service", "علاقات العملاء", "call center"],
    "تمريض":           ["تمريض", "ممرض", "infirmier", "infirmière", "infirmiere", "nurse", "إسعاف"],
}

_WILAYAS = [
    "أدرار", "الشلف", "الأغواط", "أم البواقي", "باتنة", "بجاية", "بسكرة", "بشار", "البليدة",
    "البويرة", "تمنراست", "تبسة", "تلمسان", "تيارت", "تيزي وزو", "الجزائر", "الجلفة", "جيجل",
    "سطيف", "سعيدة", "سكيكدة", "سيدي بلعباس", "عنابة", "قالمة", "قسنطينة", "المدية", "مستغانم",
    "المسيلة", "معسكر", "ورقلة", "وهران", "البيض", "إليزي", "برج بوعريريج", "بومرداس", "الطارف",
    "تندوف", "تيسمسيلت", "الوادي", "خنشلة", "سوق أهراس", "تيبازة", "ميلة", "عين الدفلى", "النعامة",
    "عين تموشنت", "غرداية", "غليزان", "تيميمون", "برج باجي مختار", "أولاد جلال", "بني عباس",
    "عين صالح", "عين قزام", "تقرت", "جانت", "المغير", "المنيعة",
]

WILAYAS_SOUTH = ["أدرار", "الأغواط", "بسكرة", "بشار", "تمنراست", "ورقلة", "البيض", "إليزي",
                 "تندوف", "غرداية", "تيميمون", "برج باجي مختار", "أولاد جلال", "بني عباس",
                 "عين صالح", "عين قزام", "تقرت", "جانت", "المغير", "المنيعة"]

SECTORS = ["نفط وغاز", "خدمات نفطية", "كهرباء وطاقات متجددة", "صناعات غذائية", "اتصالات وتكنولوجيا",
           "بناء وأشغال عمومية", "نقل ولوجستيك", "صحة", "خدمات ومقاولات", "فلاحة", "بنوك ومالية"]

CONTRACTS = ["عقد دائم (CDI)", "عقد محدد المدة (CDD)", "تربص (Stage)", "تنصيب", "حسب الاتفاقية"]


def norm(s: str) -> str:
    """تطبيع النص للمقارنة: صغير الحروف + إزالة التشكيل اللاتيني + توحيد المسافات."""
    s = unicodedata.normalize("NFKC", str(s or "")).lower()
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = " ".join(s.split())
    return s


def canon_key(label: str) -> str:
    return norm(label)


# فهرس: المفتاح المطبع ← التسمية القياسية
_ALIASES = {}
for _canon, _alts in SKILLS.items():
    _ALIASES[canon_key(_canon)] = _canon
    for _a in _alts:
        _ALIASES[canon_key(_a)] = _canon


def canonical_of(raw: str):
    """يرجع التسمية القياسية لمهارة إن وُجدت، وإلا None."""
    return _ALIASES.get(canon_key(raw))


def scan_text_for_skills(text: str):
    """يمسح نص السيرة الذاتية كاملاً ويرجع مجموعة التسميات القياسية الموجودة."""
    t = norm(text)
    found = set()
    for alias, canon in _ALIASES.items():
        if len(alias) >= 3 and alias in t:
            found.add(canon)
    return found


def user_skill_set(skills_list):
    """يحوّل قائمة مهارات المترشح إلى مجموعة تسميات قياسية (+ نصوص خام غير المصنفة)."""
    out = set()
    for s in skills_list or []:
        c = canonical_of(s)
        out.add(c if c else norm(s))
    return out


TITLE_STOP = {"مهندس", "دولة", "تقني", "سامي", "في", "من", "أخصائي", "مسؤول", "مساعدة", "رئيسي", "supérieur"}


def title_tokens(title: str):
    toks = [norm(w) for w in str(title or "").replace("-", " ").split()]
    return {t for t in toks if len(t) >= 3 and t not in TITLE_STOP}


def match_score(user, job):
    """يحسب نسبة مطابقة المترشح مع عرض العمل.
    user: dict فيه skills, title, wilaya | job: dict فيه requirements, title, wilaya
    يرجع (score 0-100, matched list, missing list)
    """
    uset = user_skill_set(user.get("skills"))
    reqs = job.get("requirements") or []
    matched, missing = [], []
    for r in reqs:
        rc = canonical_of(r) or norm(r)
        if rc in uset:
            matched.append(r)
        else:
            # مطابقة جزئية: كلمة مشتركة
            rw = set(rc.split())
            hit = False
            for u in uset:
                if rw & set(u.split()):
                    hit = True
                    break
            if hit:
                matched.append(r)
            else:
                missing.append(r)

    if reqs:
        score = len(matched) / len(reqs) * 75.0
    else:
        score = 40.0

    # تقاطع كلمات المسمى الوظيفي
    jtok = title_tokens(job.get("title"))
    utok = title_tokens(user.get("title"))
    if jtok and utok:
        score += min(len(jtok & utok) * 7.0, 15.0)

    # مكافأة الولاية
    if norm(user.get("wilaya")) and norm(user.get("wilaya")) == norm(job.get("wilaya")):
        score += 10.0

    score = max(0, min(round(score), 100))
    return score, matched, missing


def find_wilaya(text: str):
    """يرجع الولاية الأقرب لبداية النص (الأولى ذكراً)."""
    t = norm(text)
    best, best_pos = "", 10**9
    for w in _WILAYAS:
        pos = t.find(norm(w))
        if pos != -1 and pos < best_pos:
            best, best_pos = w, pos
    return best


# ── الاختصاصات (للبحث) ──
SPECIALTIES = sorted(SKILLS.keys())

# ── إحداثيات الولايات (تقريبية) لحساب القرب من عنوان الإقامة ──
WILAYA_COORDS = {
    "أدرار": (27.87, -0.29), "الشلف": (36.17, 1.33), "الأغواط": (33.80, 2.86),
    "أم البواقي": (35.87, 7.11), "باتنة": (35.55, 6.17), "بجاية": (36.75, 5.08),
    "بسكرة": (34.85, 5.73), "بشار": (31.62, -2.22), "البليدة": (36.47, 2.83),
    "البويرة": (36.37, 3.90), "تمنراست": (22.79, 5.53), "تبسة": (35.40, 8.12),
    "تلمسان": (34.88, -1.32), "تيارت": (35.37, 1.32), "تيزي وزو": (36.72, 4.05),
    "الجزائر": (36.75, 3.06), "الجلفة": (34.67, 3.25), "جيجل": (36.82, 5.77),
    "سطيف": (36.19, 5.41), "سعيدة": (34.83, 0.15), "سكيكدة": (36.88, 6.91),
    "سيدي بلعباس": (35.19, -0.63), "عنابة": (36.90, 7.77), "قالمة": (36.46, 7.43),
    "قسنطينة": (36.37, 6.61), "المدية": (36.26, 2.75), "مستغانم": (35.93, 0.09),
    "المسيلة": (35.70, 4.54), "معسكر": (35.40, 0.14), "ورقلة": (31.95, 5.33),
    "وهران": (35.70, -0.63), "البيض": (33.68, 1.02), "إليزي": (26.50, 8.47),
    "برج بوعريريج": (36.07, 4.76), "بومرداس": (36.76, 3.47), "الطارف": (36.77, 8.31),
    "تندوف": (27.67, -8.15), "تيسمسيلت": (35.61, 1.81), "الوادي": (33.37, 6.86),
    "خنشلة": (35.44, 7.14), "سوق أهراس": (36.29, 7.95), "تيبازة": (36.59, 2.45),
    "ميلة": (36.45, 6.26), "عين الدفلى": (36.26, 1.97), "النعامة": (33.27, -0.31),
    "عين تموشنت": (35.30, -1.14), "غرداية": (32.49, 3.67), "غليزان": (35.74, 0.56),
    "تيميمون": (29.26, 0.23), "برج باجي مختار": (21.32, 0.95), "أولاد جلال": (34.43, 3.40),
    "بني عباس": (30.13, -2.17), "عين صالح": (27.19, 2.48), "عين قزام": (19.57, 5.77),
    "تقرت": (33.10, 6.06), "جانت": (24.55, 9.48), "المغير": (33.95, 5.92),
    "المنيعة": (30.58, 2.88), "عين عمر": (31.93, 5.73),
}


def distance_km(w1: str, w2: str):
    """المسافة بالكيلومتر بين ولايتين (Haversine) — None إن لم تتوفر الإحداثيات."""
    c1, c2 = WILAYA_COORDS.get(norm(w1)), WILAYA_COORDS.get(norm(w2))
    if not c1 or not c2:
        return None
    import math
    lat1, lon1, lat2, lon2 = map(math.radians, (c1[0], c1[1], c2[0], c2[1]))
    dlat, dlon = lat2 - lat1, lon2 - lon1
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return int(round(6371 * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))))
