"""
Context Processor: داده‌هایی که در همه قالب‌های سایت لازم‌اند.

به‌جای فرستادن نام سایت و اطلاعات تماس در تک‌تک Viewها، اینجا یک‌بار
تعریف می‌کنیم و در همه قالب‌ها با {{ site }} در دسترس است.
"""

from django.conf import settings
from django.http import HttpRequest

from .models import SiteSetting


def site_context(request: HttpRequest) -> dict:
    return {
        # آبجکت کامل تنظیمات سایت؛ در قالب‌ها: {{ site.site_name }}
        "site": SiteSetting.load(),
        "admin_url": settings.ADMIN_URL,
        "blog_enabled": settings.BLOG_ENABLED,
    }
