"""
Viewهای عمومی سایت.

منطق سنگین داخل View نوشته نمی‌شود؛ اینجا فقط داده لازم برای قالب جمع می‌شود.
"""

from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import render

from .models import FAQ, Banner, Feature, Partner, Testimonial


def home(request: HttpRequest) -> HttpResponse:
    """
    صفحه اصلی سایت.

    هر بخش صفحه از دیتابیس خوانده می‌شود تا ادمین بتواند بدون تغییر کد
    محتوا را عوض کند یا کل بخش را خاموش کند.
    """
    # بنر فعالی که بازه تاریخی‌اش شامل «الان» است.
    banner = next(
        (b for b in Banner.objects.active() if b.is_visible_now),
        None,
    )

    context = {
        "banner": banner,
        "features": Feature.objects.active(),
        "testimonials": Testimonial.objects.active(),
        "partners": Partner.objects.active(),
        "faqs": FAQ.objects.active().filter(show_on_homepage=True)[:6],
        # بخش‌های زیر در فازهای ۶ تا ۸ به دیتابیس وصل می‌شوند.
        # فعلاً خالی‌اند و قالب به‌صورت خودکار آن‌ها را پنهان می‌کند.
        "categories": [],
        "featured_courses": [],
        "upcoming_courses": [],
        "instructors": [],
    }
    return render(request, "core/home.html", context)


def health(request: HttpRequest) -> JsonResponse:
    """آدرس ساده بررسی سلامت سرویس برای مانیتورینگ سرور."""
    return JsonResponse({"status": "ok"})


# ---------------------------------------------------------------------------
# صفحات خطا
# ---------------------------------------------------------------------------


def error_404(request: HttpRequest, exception=None) -> HttpResponse:
    return render(request, "errors/404.html", status=404)


def error_403(request: HttpRequest, exception=None) -> HttpResponse:
    return render(request, "errors/403.html", status=403)


def error_500(request: HttpRequest) -> HttpResponse:
    return render(request, "errors/500.html", status=500)
