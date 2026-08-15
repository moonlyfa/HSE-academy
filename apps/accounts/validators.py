"""
اعتبارسنج‌های اختصاصی مربوط به هویت کاربر ایرانی.

این توابع هم در سطح مدل (validators) و هم در فرم‌ها استفاده می‌شوند.
"""

import re

from django.core.exceptions import ValidationError

MOBILE_PATTERN = re.compile(r"^09\d{9}$")


def validate_iranian_mobile(value: str) -> None:
    """شماره موبایل باید دقیقاً ۱۱ رقم و با 09 شروع شود. مثال: 09121234567"""
    if not MOBILE_PATTERN.match(value or ""):
        raise ValidationError(
            "شماره موبایل معتبر نیست. شماره باید ۱۱ رقم و به شکل 09xxxxxxxxx باشد."
        )


def validate_national_code(value: str) -> None:
    """
    اعتبارسنجی کد ملی ایران با الگوریتم رقم کنترلی.

    کد ملی ۱۰ رقم است. نه رقم اول در وزن‌های ۱۰ تا ۲ ضرب می‌شوند، مجموع بر ۱۱
    تقسیم می‌شود و باقیمانده تعیین می‌کند رقم دهم (رقم کنترل) چه باید باشد:
    - اگر باقیمانده کمتر از ۲ باشد، رقم کنترل باید برابر خودِ باقیمانده باشد.
    - در غیر این صورت رقم کنترل باید برابر (۱۱ منهای باقیمانده) باشد.

    این کار جلوی ثبت کدهای ملی کاملاً ساختگی را می‌گیرد و قبل از مصرف
    سرویس پولی استعلام هویت، خطاهای واضح را حذف می‌کند.
    """
    code = (value or "").strip()

    if not code.isdigit() or len(code) != 10:
        raise ValidationError("کد ملی باید دقیقاً ۱۰ رقم عددی باشد.")

    # کدهایی مثل 0000000000 یا 1111111111 از نظر ریاضی درست‌اند اما معتبر نیستند.
    if code == code[0] * 10:
        raise ValidationError("کد ملی وارد شده معتبر نیست.")

    checksum = sum(int(code[i]) * (10 - i) for i in range(9))
    remainder = checksum % 11
    control_digit = int(code[9])

    is_valid = (
        control_digit == remainder if remainder < 2 else control_digit == 11 - remainder
    )
    if not is_valid:
        raise ValidationError("کد ملی وارد شده معتبر نیست.")
