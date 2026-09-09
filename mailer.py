# -*- coding: utf-8 -*-
"""الإرسال المباشر عبر SMTP API — يربط بريد المستخدم الخاص ويرسل طلبات العمل
مع إرفاق السيرة الذاتية والرسالة التحفيزية (PDF/Word) مباشرة إلى بريد التوظيف."""

import smtplib
import socket
import ssl
from email.message import EmailMessage
from email.utils import formataddr

# مزودات جاهزة: المفتاح ← (التسمية، الخادم، المنفذ)
PROVIDERS = {
    "gmail":     ("Gmail", "smtp.gmail.com", 587),
    "outlook":   ("Outlook / Hotmail", "smtp-mail.outlook.com", 587),
    "office365": ("Office 365", "smtp.office365.com", 587),
    "yahoo":     ("Yahoo Mail", "smtp.mail.yahoo.com", 587),
    "custom":    ("خادم مخصص (SMTP)", "", 587),
}


def error_message(e):
    """ترجمة أخطاء SMTP إلى رسائل عربية مفهومة."""
    if isinstance(e, smtplib.SMTPAuthenticationError):
        return ("بيانات الدخول مرفوضة من الخادم — تأكد من البريد ومن «كلمة مرور التطبيقات» "
                "(App Password) وليس كلمة مرور الحساب العادية.")
    if isinstance(e, (smtplib.SMTPConnectError, ConnectionRefusedError, OSError)):
        return "تعذّر الوصول إلى خادم البريد — تحقق من اسم الخادم والمنفذ ومن اتصالك بالإنترنت."
    if isinstance(e, socket.timeout):
        return "انتهت مهلة الاتصال بخادم البريد — تأكد من المنفذ (587 لـ STARTTLS أو 465 لـ SSL)."
    if isinstance(e, ssl.SSLError):
        return "مشكلة تشفير مع الخادم — جرّب منفذ 465 أو تأكد من اسم الخادم الصحيح."
    return f"خطأ غير متوقع أثناء الإرسال: {e}"


def test_connection(cfg):
    """يجرّب الاتصال وتسجيل الدخول فقط دون إرسال رسالة."""
    try:
        if int(cfg.get("port") or 587) == 465:
            with smtplib.SMTP_SSL(cfg["host"], 465, context=ssl.create_default_context(), timeout=25) as s:
                s.login(cfg["email"], cfg["password"])
        else:
            with smtplib.SMTP(cfg["host"], int(cfg.get("port") or 587), timeout=25) as s:
                s.ehlo()
                s.starttls(context=ssl.create_default_context())
                s.ehlo()
                s.login(cfg["email"], cfg["password"])
        return True, "تم الاتصال بخادم البريد وتسجيل الدخول بنجاح ✓ — جاهز للإرسال المباشر"
    except Exception as e:  # noqa: BLE001
        return False, error_message(e)


def send_mail(cfg, from_name, to_addr, subject, body, attachments=None):
    """يرسل رسالة مع مرفقات. attachments: قائمة [(مسار الملف, اسم الملف الظاهر)]"""
    msg = EmailMessage()
    msg["From"] = formataddr((str(from_name), cfg["email"]))
    msg["To"] = to_addr
    msg["Subject"] = str(subject)
    msg["X-Mailer"] = "Fursati — منصة فرصتي"
    msg.set_content(body)

    for path, fname in attachments or []:
        with open(path, "rb") as fh:
            data = fh.read()
        if str(path).lower().endswith(".pdf"):
            maintype, subtype = "application", "pdf"
        elif str(path).lower().endswith(".docx"):
            maintype, subtype = "application", "vnd.openxmlformats-officedocument.wordprocessingml.document"
        else:
            maintype, subtype = "application", "octet-stream"
        msg.add_attachment(data, maintype=maintype, subtype=subtype, filename=str(fname))

    if int(cfg.get("port") or 587) == 465:
        with smtplib.SMTP_SSL(cfg["host"], 465, context=ssl.create_default_context(), timeout=25) as s:
            s.login(cfg["email"], cfg["password"])
            s.send_message(msg)
    else:
        with smtplib.SMTP(cfg["host"], int(cfg.get("port") or 587), timeout=25) as s:
            s.ehlo()
            s.starttls(context=ssl.create_default_context())
            s.ehlo()
            s.login(cfg["email"], cfg["password"])
            s.send_message(msg)
    return True
