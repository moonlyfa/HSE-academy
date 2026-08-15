"""
Viewهای عمومی سایت.

در فاز ۱ فقط یک صفحه اصلی موقت داریم که ثابت می‌کند نصب پروژه درست انجام شده است.
در فاز ۲ این View با صفحه اصلی واقعی (Hero، دسته‌بندی‌ها، دوره‌ها و ...) جایگزین می‌شود.
"""

from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import render


def home(request: HttpRequest) -> HttpResponse:
    """صفحه اصلی موقت — فقط برای تأیید سلامت نصب."""
    return render(request, "core/home.html")


def health(request: HttpRequest) -> JsonResponse:
    """
    یک آدرس ساده برای بررسی سلامت سرویس.

    در Production، Nginx یا ابزار مانیتورینگ می‌تواند این آدرس را صدا بزند
    تا بفهمد سایت بالا است یا نه.
    """
    return JsonResponse({"status": "ok"})


# ---------------------------------------------------------------------------
# صفحات خطا
# ---------------------------------------------------------------------------
# Django امضای مشخصی برای این Viewها می‌خواهد: پارامتر exception برای ۴۰۴ و ۴۰۳.


def error_404(request: HttpRequest, exception=None) -> HttpResponse:
    return render(request, "errors/404.html", status=404)


def error_403(request: HttpRequest, exception=None) -> HttpResponse:
    return render(request, "errors/403.html", status=403)


def error_500(request: HttpRequest) -> HttpResponse:
    return render(request, "errors/500.html", status=500)
