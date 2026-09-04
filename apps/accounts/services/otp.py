"""
سرویس کد یکبارمصرف.

تمام قوانین امنیتی OTP اینجا جمع شده‌اند تا Viewها ساده بمانند و اگر
روزی قانونی عوض شد، فقط همین فایل تغییر کند.

قوانین:
  ۱. کد خام هرگز ذخیره یا لاگ نمی‌شود.
  ۲. هر کد فقط ۲ دقیقه معتبر است.
  ۳. حداکثر ۵ بار می‌توان یک کد را اشتباه وارد کرد.
  ۴. بین دو ارسال باید ۹۰ ثانیه فاصله باشد.
  ۵. در هر ساعت حداکثر ۵ بار می‌توان کد درخواست کرد.
  ۶. کد بعد از یک‌بار استفاده باطل می‌شود.
  ۷. با ارسال کد جدید، کدهای قبلی همان شماره باطل می‌شوند.
"""

from __future__ import annotations

import logging
import secrets
from dataclasses import dataclass
from datetime import timedelta

from django.conf import settings
from django.utils import timezone
from django.utils.crypto import constant_time_compare, salted_hmac

from apps.accounts.models import OtpCode, OtpPurpose

from .sms import get_sms_service

logger = logging.getLogger("hse.otp")

# نمکِ ثابتِ هش. با SECRET_KEY ترکیب می‌شود، پس اگر فقط دیتابیس لو برود
# کدها همچنان قابل بازیابی نیستند.
HASH_KEY_SALT = "hse.accounts.otp"


@dataclass
class OtpSendResult:
    """نتیجه درخواست ارسال کد."""

    success: bool
    message: str = ""
    cooldown_seconds: int = 0
    expires_in: int = 0


@dataclass
class OtpVerifyResult:
    """نتیجه بررسی کد واردشده."""

    success: bool
    message: str = ""
    attempts_left: int = 0


def _hash_code(mobile: str, purpose: str, code: str) -> str:
    """
    ساخت اثر انگشت کد.

    شماره موبایل و هدف هم داخل هش می‌روند، پس یک کد نمی‌تواند برای شماره
    یا هدف دیگری استفاده شود، حتی اگر عددش تصادفاً یکی باشد.
    """
    return salted_hmac(
        key_salt=HASH_KEY_SALT,
        value=f"{mobile}:{purpose}:{code}",
        algorithm="sha256",
    ).hexdigest()


def _generate_code() -> str:
    """
    ساخت کد تصادفی.

    از secrets استفاده می‌کنیم نه random: کتابخانه random برای کارهای
    امنیتی مناسب نیست چون خروجی‌اش قابل پیش‌بینی است.
    """
    length = settings.OTP_CODE_LENGTH
    upper_bound = 10**length
    return str(secrets.randbelow(upper_bound)).zfill(length)


def mask_mobile(mobile: str) -> str:
    """برای لاگ و نمایش: 0912***4567"""
    if not mobile or len(mobile) != 11:
        return "نامعتبر"
    return f"{mobile[:4]}***{mobile[-4:]}"


def get_active_code(mobile: str, purpose: str) -> OtpCode | None:
    """آخرین کد قابل استفاده این شماره برای این هدف."""
    code = (
        OtpCode.objects.filter(mobile=mobile, purpose=purpose, used_at__isnull=True)
        .order_by("-created_at")
        .first()
    )
    return code if code and code.is_usable else None


def seconds_until_resend(mobile: str, purpose: str) -> int:
    """چند ثانیه دیگر می‌توان دوباره کد خواست."""
    last = (
        OtpCode.objects.filter(mobile=mobile, purpose=purpose)
        .order_by("-created_at")
        .first()
    )
    if last is None:
        return 0

    passed = (timezone.now() - last.created_at).total_seconds()
    remaining = settings.OTP_RESEND_COOLDOWN_SECONDS - passed
    return max(int(remaining), 0)


def _sends_in_last_hour(mobile: str, purpose: str) -> int:
    one_hour_ago = timezone.now() - timedelta(hours=1)
    return OtpCode.objects.filter(
        mobile=mobile, purpose=purpose, created_at__gte=one_hour_ago
    ).count()


def send_otp(
    mobile: str,
    purpose: str = OtpPurpose.REGISTER,
    ip_address: str | None = None,
) -> OtpSendResult:
    """
    ساخت و ارسال کد یکبارمصرف.

    قبل از ارسال، همه محدودیت‌ها بررسی می‌شوند تا کسی نتواند با درخواست
    پیاپی، هم اعتبار پنل پیامک را تمام کند و هم مزاحم صاحب شماره شود.
    """
    cooldown = seconds_until_resend(mobile, purpose)
    if cooldown > 0:
        return OtpSendResult(
            success=False,
            message=f"برای دریافت کد جدید {cooldown} ثانیه صبر کنید.",
            cooldown_seconds=cooldown,
        )

    if _sends_in_last_hour(mobile, purpose) >= settings.OTP_MAX_SENDS_PER_HOUR:
        logger.warning(
            "سقف درخواست کد در ساعت رد شد. موبایل=%s هدف=%s",
            mask_mobile(mobile),
            purpose,
        )
        return OtpSendResult(
            success=False,
            message=(
                "تعداد درخواست کد شما زیاد بوده است. لطفاً یک ساعت دیگر "
                "دوباره تلاش کنید یا با پشتیبانی تماس بگیرید."
            ),
        )

    # کدهای قبلی باطل می‌شوند تا همیشه فقط یک کد فعال وجود داشته باشد.
    OtpCode.objects.filter(
        mobile=mobile, purpose=purpose, used_at__isnull=True
    ).update(used_at=timezone.now())

    code = _generate_code()
    expires_at = timezone.now() + timedelta(seconds=settings.OTP_EXPIRY_SECONDS)

    otp = OtpCode.objects.create(
        mobile=mobile,
        purpose=purpose,
        code_hash=_hash_code(mobile, purpose, code),
        expires_at=expires_at,
        ip_address=ip_address,
    )

    sms_result = get_sms_service().send_otp(mobile, code)

    if not sms_result.success:
        # اگر پیامک نرفت، کد را باطل می‌کنیم تا شمارنده ارسال بی‌دلیل
        # مصرف نشود و کاربر بتواند فوراً دوباره تلاش کند.
        otp.mark_used()
        logger.error(
            "ارسال پیامک ناموفق. موبایل=%s پنل=%s",
            mask_mobile(mobile),
            sms_result.provider,
        )
        return OtpSendResult(
            success=False,
            message=sms_result.message or "ارسال پیامک انجام نشد. دوباره تلاش کنید.",
        )

    # توجه: خودِ کد هرگز لاگ نمی‌شود.
    logger.info("کد یکبارمصرف ارسال شد. موبایل=%s هدف=%s", mask_mobile(mobile), purpose)

    return OtpSendResult(
        success=True,
        message="کد تأیید برای شما پیامک شد.",
        cooldown_seconds=settings.OTP_RESEND_COOLDOWN_SECONDS,
        expires_in=settings.OTP_EXPIRY_SECONDS,
    )


def verify_otp(mobile: str, purpose: str, submitted_code: str) -> OtpVerifyResult:
    """
    بررسی کد واردشده توسط کاربر.

    مقایسه با constant_time_compare انجام می‌شود. مقایسه معمولی رشته‌ها
    به محض رسیدن به اولین کاراکتر متفاوت متوقف می‌شود و همین تفاوت زمانی
    می‌تواند به مهاجم سرنخ بدهد (حمله Timing).
    """
    otp = (
        OtpCode.objects.filter(mobile=mobile, purpose=purpose, used_at__isnull=True)
        .order_by("-created_at")
        .first()
    )

    if otp is None:
        return OtpVerifyResult(
            success=False,
            message="کدی برای این شماره ثبت نشده است. لطفاً کد جدید درخواست کنید.",
        )

    if otp.is_expired:
        return OtpVerifyResult(
            success=False,
            message="اعتبار کد تمام شده است. لطفاً کد جدید درخواست کنید.",
        )

    if otp.attempts >= settings.OTP_MAX_ATTEMPTS:
        return OtpVerifyResult(
            success=False,
            message="تعداد تلاش‌های مجاز تمام شد. لطفاً کد جدید درخواست کنید.",
        )

    otp.attempts += 1
    otp.save(update_fields=["attempts"])

    expected = otp.code_hash
    provided = _hash_code(mobile, purpose, (submitted_code or "").strip())

    if not constant_time_compare(expected, provided):
        attempts_left = max(settings.OTP_MAX_ATTEMPTS - otp.attempts, 0)
        logger.info(
            "کد اشتباه وارد شد. موبایل=%s هدف=%s تلاش=%s",
            mask_mobile(mobile),
            purpose,
            otp.attempts,
        )
        message = "کد واردشده درست نیست."
        if attempts_left:
            message += f" {attempts_left} تلاش دیگر باقی مانده است."
        else:
            message = "تعداد تلاش‌های مجاز تمام شد. لطفاً کد جدید درخواست کنید."

        return OtpVerifyResult(success=False, message=message, attempts_left=attempts_left)

    otp.mark_used()
    logger.info("کد با موفقیت تأیید شد. موبایل=%s هدف=%s", mask_mobile(mobile), purpose)

    return OtpVerifyResult(success=True, message="شماره موبایل شما تأیید شد.")
