"""
ساخت فایل PDF گواهی.

**چرا PDF را خودمان می‌سازیم و نه با یک سرویس آنلاین؟**
گواهی سند دانشجوست و نباید برای ساخته‌شدنش به سرویسی بیرون از سرور
وابسته باشیم؛ روزی که آن سرویس قطع باشد، گواهی صادر نمی‌شود. ضمناً
اطلاعات هویتی دانشجو هم از سرور بیرون نمی‌رود.

**چرا فارسی روی PDF کار اضافه دارد؟**
حروف فارسی بسته به جایشان در کلمه شکل عوض می‌کنند (ب ← بـ ← ـبـ ← ـب) و
جهت نوشتار هم راست‌به‌چپ است. کتابخانه PDF هیچ‌کدام را خودش انجام
نمی‌دهد؛ اگر متن خام بدهیم، حروف جدا و برعکس چاپ می‌شوند. پس هر رشته
قبل از چاپ از دو مرحله رد می‌شود: «چسباندن حروف» و «چیدن راست‌به‌چپ».

فونت هم همان Vazirmatn داخل خود پروژه است (نسخه TTF کنار فایل‌های woff2
سایت) — یعنی ساخت گواهی به هیچ فونت سیستمی یا اینترنت وابسته نیست.
"""

from __future__ import annotations

import io
from functools import lru_cache

import arabic_reshaper
import qrcode
from bidi.algorithm import get_display
from django.conf import settings
from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

from apps.core.jalali import PERSIAN_MONTHS, to_persian_digits

FONT_DIR = settings.BASE_DIR / "static" / "fonts" / "vazirmatn"
FONT_REGULAR = "Vazirmatn"
FONT_BOLD = "Vazirmatn-Bold"

# رنگ‌ها از شیوه‌نامه برند «سپر آکادمی» گرفته شده‌اند تا گواهی و سایت یک
# خانواده دیده شوند: قرمز سپر و مشکی برند.
COLOR_BRAND = HexColor("#88261B")
COLOR_SECONDARY = HexColor("#231F20")
COLOR_TEXT = HexColor("#231F20")
COLOR_MUTED = HexColor("#6b6465")

# نشان سپر (سه ستون HSE) — همان شکل static/img/brand/separ-mark.svg، با
# مختصات کادر ۳۹۵×۳۹۵ و محور y رو به پایین. گوشه‌های گرد ریز فایل SVG در
# این اندازه دیده نمی‌شوند و حذف شده‌اند.
SHIELD_MARK = (
    ((87.9, 0), (182.9, 0), (182.9, 383.8), (39.05, 280.5), (39.05, 48.9)),
    ((197.4, 0), (266.9, 0), (266.9, 345.0), (197.4, 394.9)),
    ((281.4, 0), (306.9, 0), (355.8, 48.9), (355.8, 279.5), (281.4, 333.4)),
)
SHIELD_MARK_BOX = 394.88


@lru_cache(maxsize=1)
def register_fonts() -> bool:
    """
    ثبت فونت فارسی در موتور PDF — فقط یک‌بار در طول عمر پردازه.

    اگر فایل فونت نبود، خطا نمی‌دهیم و با فونت پیش‌فرض ادامه می‌دهیم؛
    گواهیِ بدقواره بهتر از گواهیِ صادرنشده است. (متن لاتین و اعداد
    درست چاپ می‌شوند.)
    """
    try:
        pdfmetrics.registerFont(TTFont(FONT_REGULAR, FONT_DIR / "Vazirmatn-Regular.ttf"))
        pdfmetrics.registerFont(TTFont(FONT_BOLD, FONT_DIR / "Vazirmatn-Bold.ttf"))
        return True
    except Exception:  # noqa: BLE001 — نبودِ فونت نباید صدور را متوقف کند
        return False


def fa(text: str) -> str:
    """آماده‌سازی متن فارسی برای چاپ: چسباندن حروف و چیدن راست‌به‌چپ."""
    if not text:
        return ""
    return get_display(arabic_reshaper.reshape(str(text)))


def _font(bold: bool = False) -> str:
    if register_fonts():
        return FONT_BOLD if bold else FONT_REGULAR
    return "Helvetica-Bold" if bold else "Helvetica"


def _centered(pdf: canvas.Canvas, text: str, y: float, size: int, *, bold=False, color=COLOR_TEXT):
    pdf.setFont(_font(bold), size)
    pdf.setFillColor(color)
    pdf.drawCentredString(landscape(A4)[0] / 2, y, fa(text))


def qr_image(url: str) -> ImageReader:
    """QR استعلام. خروجی در حافظه می‌ماند و روی دیسک چیزی نوشته نمی‌شود."""
    qr = qrcode.QRCode(box_size=10, border=1)
    qr.add_data(url)
    qr.make(fit=True)
    image = qr.make_image(fill_color="black", back_color="white").convert("RGB")

    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    buffer.seek(0)
    return ImageReader(buffer)


def jalali_date_text(certificate) -> str:
    year, month, day = certificate.issued_jalali
    return to_persian_digits(f"{day} {PERSIAN_MONTHS[month - 1]} {year}")


def render_certificate(certificate, verification_url: str, site_name: str) -> bytes:
    """
    یک برگ گواهی A4 افقی.

    چیدمان عمداً ساده است: هرچه روی گواهی نوشته می‌شود باید در یک نگاه
    خوانده شود — نام، دوره، تاریخ، کد و QR. تزئین بیشتر، خوانایی کمتر.
    """
    width, height = landscape(A4)
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=landscape(A4))
    pdf.setTitle(f"{certificate.certificate_code}")

    # --- کادر ---
    pdf.setStrokeColor(COLOR_BRAND)
    pdf.setLineWidth(6)
    pdf.rect(22, 22, width - 44, height - 44)
    pdf.setStrokeColor(COLOR_SECONDARY)
    pdf.setLineWidth(1)
    pdf.rect(34, 34, width - 68, height - 68)

    # --- سربرگ ---
    _shield_mark(pdf, x=width - 130, top=height - 62, size=64)
    _centered(pdf, site_name, height - 90, 20, bold=True, color=COLOR_SECONDARY)
    _centered(pdf, "گواهی پایان دوره", height - 145, 32, bold=True, color=COLOR_BRAND)

    # خط زیر عنوان با فاصله از پایین‌ترین بخش حروف کشیده می‌شود؛ حروف
    # فارسی دنباله‌دارند (ی، ج، ر) و خطِ نزدیک، رویشان می‌افتد.
    pdf.setStrokeColor(COLOR_BRAND)
    pdf.setLineWidth(2)
    pdf.line(width / 2 - 70, height - 175, width / 2 + 70, height - 175)

    # --- متن گواهی ---
    _centered(pdf, "بدین‌وسیله گواهی می‌شود", height - 218, 14, color=COLOR_MUTED)
    _centered(pdf, certificate.holder_name, height - 265, 26, bold=True)

    hours = certificate.course_hours
    if hours:
        body = f"دوره «{certificate.course_title}» را به مدت {to_persian_digits(hours)} ساعت با موفقیت گذرانده است."
    else:
        body = f"دوره «{certificate.course_title}» را با موفقیت گذرانده است."
    _centered(pdf, body, height - 308, 15)

    if certificate.score is not None:
        _centered(
            pdf,
            f"نمره آزمون پایان دوره: {to_persian_digits(certificate.score)} از ۱۰۰",
            height - 338,
            13,
            color=COLOR_MUTED,
        )

    # --- پانویس: سمت راست تاریخ و امضا، سمت چپ QR و کد ---
    pdf.setFont(_font(), 12)
    pdf.setFillColor(COLOR_TEXT)
    pdf.drawRightString(width - 90, 185, fa(f"تاریخ صدور: {jalali_date_text(certificate)}"))

    if certificate.instructor_name:
        pdf.drawRightString(width - 90, 160, fa(f"مدرس دوره: {certificate.instructor_name}"))

    pdf.setStrokeColor(COLOR_MUTED)
    pdf.setLineWidth(1)
    pdf.line(width - 240, 115, width - 90, 115)
    pdf.setFont(_font(), 11)
    pdf.setFillColor(COLOR_MUTED)
    pdf.drawRightString(width - 90, 96, fa("مهر و امضای آکادمی"))

    # --- QR و کد گواهی ---
    pdf.drawImage(qr_image(verification_url), 90, 96, width=96, height=96, mask="auto")

    pdf.setFont(_font(bold=True), 12)
    pdf.setFillColor(COLOR_TEXT)
    pdf.drawString(200, 172, certificate.certificate_code)

    pdf.setFont(_font(), 10)
    pdf.setFillColor(COLOR_MUTED)
    pdf.drawString(200, 150, fa("کد گواهی"))
    pdf.drawString(200, 128, fa("اصالت این گواهی را با اسکن QR"))
    pdf.drawString(200, 112, fa("یا وارد کردن کد در سایت بررسی کنید."))

    if not certificate.is_valid:
        _stamp(pdf, width, height, certificate.status_label)

    pdf.showPage()
    pdf.save()
    return buffer.getvalue()


def _shield_mark(pdf: canvas.Canvas, *, x: float, top: float, size: float) -> None:
    """نشان سپر را در کادری مربعی به ضلع size می‌کشد؛ (x, top) گوشه بالا-چپ است."""
    scale = size / SHIELD_MARK_BOX
    pdf.saveState()
    pdf.setFillColor(COLOR_BRAND)
    for points in SHIELD_MARK:
        path = pdf.beginPath()
        first, *rest = points
        path.moveTo(x + first[0] * scale, top - first[1] * scale)
        for px, py in rest:
            path.lineTo(x + px * scale, top - py * scale)
        path.close()
        pdf.drawPath(path, stroke=0, fill=1)
    pdf.restoreState()


def _stamp(pdf: canvas.Canvas, width: float, height: float, label: str) -> None:
    """
    مهر «باطل‌شده» روی گواهی‌های بی‌اعتبار.

    فایل گواهیِ باطل‌شده همچنان قابل دانلود است (دانشجو باید بتواند
    ببیند چه چیزی باطل شده) اما نباید با نسخه معتبر اشتباه گرفته شود.
    """
    pdf.saveState()
    pdf.translate(width / 2, height / 2)
    pdf.rotate(30)
    pdf.setFont(_font(bold=True), 72)
    pdf.setFillColor(HexColor("#d1352b"), alpha=0.28)
    pdf.drawCentredString(0, 0, fa(label))
    pdf.restoreState()
