"""
Context Processor: داده‌هایی که در همه قالب‌های سایت لازم‌اند.

به‌جای فرستادن نام سایت و اطلاعات تماس در تک‌تک Viewها، اینجا یک‌بار
تعریف می‌کنیم و در همه قالب‌ها با {{ site }} در دسترس است.
"""

from django.conf import settings
from django.http import HttpRequest

from apps.orders.cart import CART_SESSION_KEY

from .models import SiteSetting


def site_context(request: HttpRequest) -> dict:
    return {
        # آبجکت کامل تنظیمات سایت؛ در قالب‌ها: {{ site.site_name }}
        "site": SiteSetting.load(),
        "admin_url": settings.ADMIN_URL,
        "blog_enabled": settings.BLOG_ENABLED,
        # دوره‌های آنلاین/آفلاین و کلاس اسکای‌روم. خاموش یعنی منوها و بخش‌های
        # مربوط به آن‌ها در قالب‌ها نمایش داده نمی‌شوند.
        "online_courses_enabled": settings.ONLINE_COURSES_ENABLED,
        # روی سرور آزمایشی False است و قالب پایه، کل سایت را noindex می‌کند.
        "seo_allow_indexing": settings.SEO_ALLOW_INDEXING,
        # تعداد اقلام سبد برای نشان کنار آیکون سبد در هدر.
        # فقط از Session خوانده می‌شود و به دیتابیس نمی‌رود، تا این
        # Context Processor روی هر صفحه سایت کوئری اضافه نزند.
        "cart_count": len(request.session.get(CART_SESSION_KEY, [])),
    }
