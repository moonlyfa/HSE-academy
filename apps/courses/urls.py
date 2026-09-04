"""
آدرس‌های بخش دوره‌ها.

آدرس‌ها معنادار و سئوپسند هستند: /courses/hse-officer/ نه /courses/17/
"""

from django.urls import path

from . import views

app_name = "courses"

urlpatterns = [
    path("", views.course_list, name="list"),
    path("<uslug:slug>/", views.course_detail, name="detail"),
]
