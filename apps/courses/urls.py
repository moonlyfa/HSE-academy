"""
آدرس‌های بخش دوره‌ها.

آدرس‌ها معنادار و سئوپسند هستند: /courses/hse-officer/ نه /courses/17/
"""

from django.urls import path

from . import views

app_name = "courses"

urlpatterns = [
    path("", views.course_list, name="list"),
    # آدرس درس شامل اسلاگ دوره است تا هم خوانا باشد و هم بشود بررسی کرد
    # که درس واقعاً به همان دوره تعلق دارد.
    path("<uslug:slug>/lessons/<int:pk>/", views.lesson_detail, name="lesson"),
    path("<uslug:slug>/lessons/<int:pk>/video/", views.lesson_video, name="lesson_video"),
    path(
        "<uslug:slug>/lessons/<int:pk>/files/<int:attachment_pk>/",
        views.lesson_attachment,
        name="lesson_attachment",
    ),
    # این الگو باید آخر باشد؛ وگرنه «hse-officer/lessons/…» را هم به‌عنوان
    # اسلاگ یک دوره در نظر می‌گیرد.
    path("<uslug:slug>/", views.course_detail, name="detail"),
]
