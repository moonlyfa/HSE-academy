"""آدرس‌های صفحات عمومی سایت."""

from django.urls import path

from apps.courses import views as course_views

from . import views

app_name = "core"

urlpatterns = [
    path("", views.home, name="home"),
    # صفحات ثابت
    path("about/", views.about, name="about"),
    path("contact/", views.contact, name="contact"),
    path("faq/", views.faq, name="faq"),
    path("privacy/", views.privacy, name="privacy"),
    path("terms/", views.terms, name="terms"),
    # استعلام گواهی — صفحه مستقل، نه بخشی از صفحه اصلی
    path("certificate/verify/", views.certificate_verify, name="certificate_verify"),
    # تقویم آموزشی، جست‌وجو و صفحات مدرسان در اپ دوره‌ها پیاده شده‌اند،
    # اما آدرسشان در ریشه سایت است تا کوتاه و سئوپسند بماند.
    path("calendar/", course_views.training_calendar, name="calendar"),
    path("search/", course_views.search, name="search"),
    path("instructors/", course_views.instructor_list, name="instructors"),
    path(
        "instructors/<uslug:slug>/",
        course_views.instructor_detail,
        name="instructor_detail",
    ),
    # بررسی سلامت سرویس
    path("health/", views.health, name="health"),
]
