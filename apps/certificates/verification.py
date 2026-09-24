"""
استعلام عمومی گواهی.

این تنها بخش سایت است که **بدون حساب کاربری** به داده‌های یک دانشجو نگاه
می‌کند، پس دو نگرانی هم‌زمان دارد:

**۱. کارفرما باید بتواند اصالت را بررسی کند.** وگرنه گواهی فقط یک کاغذ
چاپی است.

**۲. کسی نباید بتواند با شمردن کدها، فهرست دانشجوها را بیرون بکشد.**
کد گواهی ترتیبی است (HSE-1405-00001) و همین یعنی حدس‌زدنی است.

تعادل این دو با یک قاعده ساده بسته شده است:

    استعلام با **کد**   → نام به‌صورت کوتاه‌شده («سارا م.»)
    استعلام با **توکن** → نام کامل

کسی که QR روی گواهی را اسکن می‌کند، خودِ گواهی را در دست دارد؛ نشان دادن
نام کامل به او چیزی را لو نمی‌دهد. اما کسی که فقط کدها را می‌شمارد، به
اسم کامل هیچ‌کس نمی‌رسد. در هر دو حالت، شماره موبایل، کد ملی و ایمیل
اصلاً وارد این صفحه نمی‌شوند.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from apps.core.throttling import CERTIFICATE_LOOKUP_LIMIT

from .models import Certificate

logger = logging.getLogger("hse.certificate")

# ارقام فارسی و عربی، چون کاربر ممکن است کد را با صفحه‌کلید فارسی بنویسد.
DIGIT_TRANSLATION = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
# انواع خط تیره‌ای که از کپی‌کردن متن در می‌آیند.
DASH_TRANSLATION = str.maketrans("–—‐‑‒−ـ", "-------")


def normalize_code(raw: str) -> str:
    """
    کدی که کاربر تایپ کرده را به شکل استاندارد برمی‌گرداند.

    کسی که کد را از روی کاغذ می‌خواند ممکن است با ارقام فارسی بنویسد، با
    حروف کوچک، یا با فاصله. هیچ‌کدام نباید باعث شود گواهی معتبر «پیدا
    نشد» بگیرد.
    """
    if not raw:
        return ""

    text = str(raw).strip().translate(DIGIT_TRANSLATION).translate(DASH_TRANSLATION)
    text = text.replace(" ", "").replace("_", "-").upper()
    return text


def mask_name(name: str) -> str:
    """«سارا محمدی» → «سارا م.»"""
    parts = name.split()
    if not parts:
        return ""
    if len(parts) == 1:
        return f"{parts[0][0]}…"
    return " ".join(parts[:-1] + [f"{parts[-1][0]}."])


@dataclass
class VerificationResult:
    """
    نتیجه یک استعلام.

    حالت‌ها عمداً از هم جدا شده‌اند: «پیدا نشد» و «باطل شده» دو حرف کاملاً
    متفاوت به کارفرما می‌زنند و نباید در یک پیام کلی قاطی شوند.
    """

    status: str  # empty | not_found | valid | revoked | expired | throttled
    certificate: Certificate | None = None
    display_name: str = ""
    full_name_shown: bool = False

    @property
    def found(self) -> bool:
        return self.certificate is not None

    @property
    def is_valid(self) -> bool:
        return self.status == "valid"


def _result_for(certificate: Certificate, *, full_name: bool) -> VerificationResult:
    if certificate.is_revoked:
        status = "revoked"
    elif certificate.is_expired:
        status = "expired"
    else:
        status = "valid"

    return VerificationResult(
        status=status,
        certificate=certificate,
        display_name=(
            certificate.holder_name if full_name else mask_name(certificate.holder_name)
        ),
        full_name_shown=full_name,
    )


def verify(*, code: str = "", token: str = "") -> VerificationResult:
    """
    جست‌وجوی گواهی با کد یا توکن.

    توکن اولویت دارد: اگر کسی QR را اسکن کرده، همان مسیر معتبرتر است.
    """
    if token:
        certificate = Certificate.objects.filter(
            verification_token=token
        ).select_related("course").first()
        if certificate is not None:
            return _result_for(certificate, full_name=True)
        # توکن اشتباه را مثل کد اشتباه جواب می‌دهیم؛ نباید معلوم شود که
        # توکن «وجود دارد ولی نامعتبر است» یا اصلاً وجود ندارد.
        return VerificationResult(status="not_found")

    normalized = normalize_code(code)
    if not normalized:
        return VerificationResult(status="empty")

    certificate = Certificate.objects.filter(
        certificate_code__iexact=normalized
    ).select_related("course").first()

    if certificate is None:
        return VerificationResult(status="not_found")

    return _result_for(certificate, full_name=False)


# ---------------------------------------------------------------------------
# محدودسازی نرخ استعلام
# ---------------------------------------------------------------------------
# بدون این، یک برنامه ساده می‌تواند کدها را از ۰۰۰۰۱ به بالا امتحان کند و
# ببیند کدام‌ها گواهی واقعی‌اند. سقف در حدی است که هیچ کارفرمای واقعی به
# آن نمی‌خورد اما شمردن کدها را بی‌فایده می‌کند. خودِ شمارنده، ابزار
# مشترک پروژه است (apps/core/throttling.py).


def is_throttled(request) -> bool:
    return CERTIFICATE_LOOKUP_LIMIT.is_exceeded(request)


def register_lookup(request) -> None:
    """یک استعلام را در شمارنده ساعتی همان IP ثبت می‌کند."""
    CERTIFICATE_LOOKUP_LIMIT.record(request)
