"""
نقشه اصلی آدرس‌های سایت (URL Configuration).

هر درخواستی که به سایت می‌رسد، اول به این فایل می‌آید و از اینجا به
اپلیکیشن مربوطه هدایت می‌شود.
"""

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path, re_path, register_converter

from apps.core.converters import UnicodeSlugConverter
from apps.courses import views as course_views

# مبدل «uslug» اجازه می‌دهد آدرس دوره‌ها و مدرسان فارسی هم باشد.
# باید پیش از استفاده در الگوها ثبت شود.
register_converter(UnicodeSlugConverter, "uslug")

urlpatterns = [
    # آدرس پنل مدیریت از طریق .env قابل تغییر است تا در Production
    # آدرس /admin/ حدس‌زدنی نباشد.
    path(f"{settings.ADMIN_URL}/", admin.site.urls),
    path("accounts/", include("apps.accounts.urls")),
    path("courses/", include("apps.courses.urls")),
    # فایل‌های محافظت‌شده دوره‌ها: فقط برای مدیران، و صرفاً برای اینکه
    # لینک فایل در پنل مدیریت کار کند. دانشجو از آدرس خودِ درس می‌گیرد.
    re_path(
        r"^protected-media/(?P<path>.+)$",
        course_views.protected_media,
        name="protected_media",
    ),
    path("", include("apps.core.urls")),
]

# در محیط توسعه، فایل‌های آپلودشده (مدیا) را خود Django سرو می‌کند.
# در Production این کار بر عهده Nginx است.
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

# صفحات خطای سفارشی (فارسی). در فاز ۲ قالب آن‌ها ساخته می‌شود.
handler404 = "apps.core.views.error_404"
handler500 = "apps.core.views.error_500"
handler403 = "apps.core.views.error_403"
