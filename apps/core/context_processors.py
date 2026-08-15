"""
Context Processor: داده‌هایی که باید در همه قالب‌های سایت در دسترس باشند.

به‌جای اینکه در هر View نام سایت و شماره تماس را دستی بفرستیم، اینجا یک‌بار
تعریف می‌کنیم و در همه قالب‌ها با {{ site_name }} قابل استفاده است.

در فاز ۲ این مقادیر از مدل SiteSetting در دیتابیس خوانده می‌شوند تا ادمین
بتواند بدون تغییر کد آن‌ها را ویرایش کند.
"""

from django.conf import settings
from django.http import HttpRequest


def site_context(request: HttpRequest) -> dict:
    return {
        "site_name": settings.SITE_NAME,
        "site_domain": settings.SITE_DOMAIN,
        "site_support_phone": settings.SITE_SUPPORT_PHONE,
        "site_support_email": settings.SITE_SUPPORT_EMAIL,
        "blog_enabled": settings.BLOG_ENABLED,
        "admin_url": settings.ADMIN_URL,
    }
