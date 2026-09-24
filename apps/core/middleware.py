"""
هدرهای امنیتی پاسخ.

جنگو بیشتر هدرهای امنیتی را خودش می‌فرستد (`SECURE_*` در تنظیمات)، اما دو
تای مهم را ندارد و اینجا اضافه می‌شوند:

**Content-Security-Policy** — به مرورگر می‌گوید حق دارد محتوا را از کجا
بارگذاری و اجرا کند. این آخرین خط دفاع در برابر XSS است: اگر روزی، با یک
اشتباه در یک قالب، متنی از کاربر بدون Escape داخل صفحه برود، باز هم
مرورگر اجازه اجرای اسکریپتش را نمی‌دهد.

چون این پروژه هیچ فایل جاوااسکریپت یا فونت خارجی ندارد (قاعده «استقلال از
اینترنت خارجی» از فاز اول)، می‌توانیم سخت‌گیرترین حالت ممکن را بگذاریم:
`script-src 'self'`.

**Permissions-Policy** — دسترسی صفحه به دوربین، میکروفون، موقعیت مکانی و
درگاه پرداخت مرورگر را می‌بندد. سایت به هیچ‌کدام نیاز ندارد.

**Nonce:** بلوک‌های داده ساختاریافته (`application/ld+json`) درون‌خطی‌اند.
بیشتر مرورگرها آن‌ها را اجرا نمی‌کنند و مشمول CSP نمی‌دانند، اما بعضی
سخت‌گیرتر عمل می‌کنند. برای اینکه در هیچ مرورگری حذف نشوند، هر پاسخ یک
nonce تصادفی می‌گیرد و همان روی این بلوک‌ها می‌نشیند.
"""

from __future__ import annotations

import logging
import secrets

from django.conf import settings
from django.http import HttpResponse

from .throttling import ADMIN_LOGIN_LIMIT, get_client_ip

logger = logging.getLogger("hse.security")


class SecurityHeadersMiddleware:
    """CSP و Permissions-Policy را به هر پاسخ اضافه می‌کند."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # nonce پیش از پردازش View ساخته می‌شود چون قالب‌ها هنگام رندر
        # به آن نیاز دارند.
        request.csp_nonce = secrets.token_urlsafe(16)

        response = self.get_response(request)

        if settings.PERMISSIONS_POLICY:
            response.setdefault("Permissions-Policy", settings.PERMISSIONS_POLICY)

        if settings.CSP_ENABLED:
            header = (
                "Content-Security-Policy-Report-Only"
                if settings.CSP_REPORT_ONLY
                else "Content-Security-Policy"
            )
            response.setdefault(header, self.policy(request))

        return response

    def policy(self, request) -> str:
        directives = []
        for directive in settings.CSP_DIRECTIVES:
            if directive.startswith("script-src"):
                directive = f"{directive} 'nonce-{request.csp_nonce}'"
            directives.append(directive)

        return "; ".join(directives)


class AdminLoginThrottleMiddleware:
    """
    محدودسازی تلاش ورود به پنل مدیریت.

    صفحه ورود سایت، محدودیت تلاش ناموفق دارد (apps/accounts/throttling.py)
    اما فرم ورود **پنل مدیریت** فرم خود جنگو است و از آن مسیر رد نمی‌شود.
    پنل مدیریت ارزشمندترین هدف سایت است: یک حساب مدیر یعنی دسترسی به همه
    دوره‌ها، سفارش‌ها و اطلاعات کاربران.

    آدرس پنل با تنظیمات قابل تغییر است و همین حدس‌زدنش را سخت می‌کند، اما
    «سخت» کافی نیست وقتی می‌شود ساعتی هزاران رمز را امتحان کرد.

    فقط درخواست‌های POST شمرده می‌شوند؛ باز کردن صفحه ورود محدود نیست.
    """

    def __init__(self, get_response):
        self.get_response = get_response
        self.login_path = f"/{settings.ADMIN_URL}/login/"

    def __call__(self, request):
        if request.method == "POST" and request.path == self.login_path:
            if ADMIN_LOGIN_LIMIT.is_exceeded(request):
                logger.warning(
                    "تلاش ورود به پنل مدیریت به دلیل تعداد زیاد مسدود شد. IP=%s",
                    get_client_ip(request),
                )
                return HttpResponse(
                    "تعداد تلاش‌های ورود زیاد بوده است. لطفاً بعداً دوباره تلاش کنید.",
                    status=429,
                    content_type="text/plain; charset=utf-8",
                )

            ADMIN_LOGIN_LIMIT.record(request)

        return self.get_response(request)
