"""
آدرس‌های بخش دوره‌ها.

آدرس‌ها معنادار و سئوپسند هستند: /courses/hse-officer/ نه /courses/17/
"""

from django.urls import path

from . import views

app_name = "courses"

urlpatterns = [
    path("", views.course_list, name="list"),
    # آدرس ثابت باید پیش از الگوی اسلاگ بیاید، وگرنه به‌عنوان اسلاگ یک
    # دوره خوانده می‌شود.
    path("my-classes/", views.my_sessions, name="my_sessions"),
    # آدرس درس و جلسه شامل اسلاگ دوره است تا هم خوانا باشد و هم بشود
    # بررسی کرد که واقعاً به همان دوره تعلق دارند.
    path("<uslug:slug>/enroll/", views.enroll_free, name="enroll_free"),
    # لینک کلاس آنلاین هیچ‌وقت در صفحه نوشته نمی‌شود؛ کاربر به این آدرس
    # می‌آید و بعد از بررسی ثبت‌نام، به کلاس هدایت می‌شود.
    path(
        "<uslug:slug>/sessions/<int:pk>/join/",
        views.session_join,
        name="session_join",
    ),
    path("<uslug:slug>/lessons/<int:pk>/", views.lesson_detail, name="lesson"),
    path("<uslug:slug>/lessons/<int:pk>/video/", views.lesson_video, name="lesson_video"),
    path(
        "<uslug:slug>/lessons/<int:pk>/complete/",
        views.lesson_complete,
        name="lesson_complete",
    ),
    path(
        "<uslug:slug>/lessons/<int:pk>/position/",
        views.lesson_position,
        name="lesson_position",
    ),
    path(
        "<uslug:slug>/lessons/<int:pk>/files/<int:attachment_pk>/",
        views.lesson_attachment,
        name="lesson_attachment",
    ),
    # این الگو باید آخر باشد؛ وگرنه «hse-officer/lessons/…» را هم به‌عنوان
    # اسلاگ یک دوره در نظر می‌گیرد.
    path("<uslug:slug>/", views.course_detail, name="detail"),
]
