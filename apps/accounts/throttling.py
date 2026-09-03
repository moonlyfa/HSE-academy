"""
محدودسازی تلاش‌های ناموفق ورود.

چرا لازم است؟
بدون آن، کسی می‌تواند با یک برنامه ساده هزاران رمز را روی یک شماره
موبایل امتحان کند (حمله Brute Force). با محدود کردن تعداد تلاش، این
حمله عملاً غیرممکن می‌شود.

روش کار: تعداد تلاش‌های ناموفق را در Cache نگه می‌داریم. کلید ترکیبی از
شماره موبایل و آدرس IP است تا:
  - قفل‌شدن یک شماره، کاربر واقعی را از IP دیگری بی‌دلیل مسدود نکند
  - یک IP نتواند روی شماره‌های مختلف بی‌نهایت تلاش کند
"""

import logging

from django.core.cache import cache
from django.http import HttpRequest

logger = logging.getLogger("hse.accounts")

MAX_ATTEMPTS = 5
LOCKOUT_SECONDS = 15 * 60  # ۱۵ دقیقه


def get_client_ip(request: HttpRequest) -> str:
    """
    آدرس IP کاربر.

    در Production پشت Nginx، آدرس واقعی در هدر X-Forwarded-For است.
    اولین مقدار این هدر، IP خود کاربر است.
    """
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "unknown")


def _cache_key(mobile: str, ip: str) -> str:
    return f"login-attempts:{mobile}:{ip}"


def is_locked_out(request: HttpRequest, mobile: str) -> bool:
    """آیا این ترکیب موبایل و IP فعلاً مسدود است؟"""
    attempts = cache.get(_cache_key(mobile, get_client_ip(request)), 0)
    return attempts >= MAX_ATTEMPTS


def remaining_attempts(request: HttpRequest, mobile: str) -> int:
    attempts = cache.get(_cache_key(mobile, get_client_ip(request)), 0)
    return max(MAX_ATTEMPTS - attempts, 0)


def register_failed_attempt(request: HttpRequest, mobile: str) -> int:
    """
    یک تلاش ناموفق را ثبت و تعداد تلاش‌های باقی‌مانده را برمی‌گرداند.

    توجه: رمز عبور واردشده هرگز لاگ نمی‌شود.
    """
    ip = get_client_ip(request)
    key = _cache_key(mobile, ip)

    attempts = cache.get(key, 0) + 1
    cache.set(key, attempts, LOCKOUT_SECONDS)

    if attempts >= MAX_ATTEMPTS:
        logger.warning(
            "حساب به دلیل تلاش‌های ناموفق متعدد موقتاً قفل شد. موبایل=%s IP=%s",
            mask_mobile(mobile),
            ip,
        )

    return max(MAX_ATTEMPTS - attempts, 0)


def clear_attempts(request: HttpRequest, mobile: str) -> None:
    """بعد از ورود موفق، شمارنده صفر می‌شود."""
    cache.delete(_cache_key(mobile, get_client_ip(request)))


def mask_mobile(mobile: str) -> str:
    """برای لاگ: 0912***4567 — شماره کامل در لاگ ذخیره نمی‌شود."""
    if not mobile or len(mobile) != 11:
        return "نامعتبر"
    return f"{mobile[:4]}***{mobile[-4:]}"
