"""
محدودسازی نرخ درخواست — ابزار مشترک همه بخش‌ها.

چرا لازم است؟ هر فرم عمومی سایت، اگر سقف نداشته باشد، با یک اسکریپت ساده
قابل سوءاستفاده است: هزار پیام تماس در دقیقه، هزار حساب کاربری، یا امتحان
کردن کدهای گواهی یکی‌یکی. هیچ‌کدام «نفوذ» نیستند، اما هر سه سایت را از کار
می‌اندازند یا داده بیرون می‌کشند.

**روش: پنجره ثابت ساعتی.**
شمارنده در Cache با کلیدی ذخیره می‌شود که ساعت جاری داخلش است. مزیتش این
است که از Cache نمی‌پرسیم «چقدر از عمر این کلید مانده» — چیزی که همه
بک‌اندهای Cache جواب نمی‌دهند — و پنجره هر ساعت تمیز باز می‌شود.

**نکته مهم درباره Production:** این شمارنده در Cache است، و در سرور واقعی
Gunicorn چند Worker جداگانه دارد. اگر کش حافظه‌ای (LocMemCache) بماند، هر
Worker شمارنده خودش را دارد و سقف عملاً چند برابر می‌شود. تنظیمات
Production عمداً از DatabaseCache استفاده می‌کند که بین Workerها مشترک است.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from django.conf import settings
from django.core.cache import cache
from django.http import HttpRequest
from django.utils import timezone

logger = logging.getLogger("hse.security")


def get_client_ip(request: HttpRequest) -> str:
    """
    آدرس IP کاربر.

    هدر `X-Forwarded-For` را **فقط وقتی** باور می‌کنیم که تنظیمات بگوید
    سایت پشت یک Proxy مورد اعتماد (Nginx خودمان) است. اگر همیشه باور
    می‌کردیم، هر کسی می‌توانست با فرستادن یک هدر ساختگی، سقف‌ها را دور
    بزند: هر درخواست، یک IP جدید.

    در سرور، Nginx باید این هدر را خودش بازنویسی کند:

        proxy_set_header X-Forwarded-For $remote_addr;
    """
    if settings.TRUST_X_FORWARDED_FOR:
        forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
        if forwarded:
            return forwarded.split(",")[0].strip()

    return request.META.get("REMOTE_ADDR", "unknown")


@dataclass(frozen=True)
class RateLimit:
    """
    یک سقف نام‌دار: «چند بار در ساعت، برای هر IP».

    نمونه:
        if CONTACT_LIMIT.is_exceeded(request):
            ...پیام خطا...
        CONTACT_LIMIT.record(request)

    مقدار سقف با **نام تنظیمات** نگهداری می‌شود نه با عدد، تا اگر مدیر
    سرور عدد را در .env عوض کند (یا تستی آن را موقتاً تغییر دهد) همین
    شیء بدون ساخته‌شدن دوباره، مقدار تازه را ببیند.
    """

    name: str
    setting: str

    @property
    def limit(self) -> int:
        return getattr(settings, self.setting, 0)

    def key(self, request: HttpRequest, scope: str = "") -> str:
        hour = timezone.now().strftime("%Y%m%d%H")
        parts = ["ratelimit", self.name, get_client_ip(request), hour]
        if scope:
            parts.append(scope)
        return ":".join(parts)

    def count(self, request: HttpRequest, scope: str = "") -> int:
        return cache.get(self.key(request, scope), 0)

    def is_exceeded(self, request: HttpRequest, scope: str = "") -> bool:
        """صفر یعنی بدون محدودیت — برای خاموش کردن سقف در تنظیمات."""
        if not self.limit:
            return False
        return self.count(request, scope) >= self.limit

    def record(self, request: HttpRequest, scope: str = "") -> int:
        """
        یک تلاش را می‌شمارد.

        فقط تلاش‌هایی شمرده می‌شوند که واقعاً کاری انجام می‌دهند (ارسال
        فرم، جست‌وجوی کد)، نه باز کردن صفحه؛ وگرنه کاربری که چند بار صفحه
        را می‌بیند بی‌دلیل مسدود می‌شود.
        """
        if not self.limit:
            return 0

        key = self.key(request, scope)
        count = cache.get(key, 0) + 1
        cache.set(key, count, 3600)

        if count == self.limit:
            logger.warning(
                "سقف «%s» برای این IP پر شد. IP=%s", self.name, get_client_ip(request)
            )

        return count


# ---------------------------------------------------------------------------
# سقف‌های تعریف‌شده پروژه
# ---------------------------------------------------------------------------
# همه در یک جا هستند تا با یک نگاه معلوم باشد چه چیزهایی محدود شده‌اند و
# هیچ فرم عمومی تازه‌ای بدون سقف جا نماند.

# فرم تماس با ما: بدون سقف، با یک اسکریپت ساده هزاران پیام ثبت می‌شود.
CONTACT_LIMIT = RateLimit("contact", "CONTACT_MAX_PER_HOUR")

# ثبت‌نام: سرویس پیامک برای هر شماره سقف دارد، اما یک مهاجم می‌تواند با
# هزار شماره مختلف کار کند. این سقف روی خود IP است.
REGISTRATION_LIMIT = RateLimit("registration", "REGISTRATION_MAX_PER_HOUR")

# بازیابی رمز: همان منطق، به‌علاوه جلوگیری از پیامک‌باران یک نفر.
PASSWORD_RESET_LIMIT = RateLimit("password-reset", "PASSWORD_RESET_MAX_PER_HOUR")

# ورود به پنل مدیریت: ارزشمندترین هدف سایت. فرم ورود پنل، فرم خود جنگو
# است و از محدودیت تلاش صفحه ورود سایت رد نمی‌شود.
ADMIN_LOGIN_LIMIT = RateLimit("admin-login", "ADMIN_LOGIN_MAX_PER_HOUR")

# استعلام گواهی: کد گواهی ترتیبی است و بدون سقف می‌شود کدها را شمرد.
CERTIFICATE_LOOKUP_LIMIT = RateLimit(
    "certificate-lookup", "CERTIFICATE_LOOKUP_MAX_PER_HOUR"
)
