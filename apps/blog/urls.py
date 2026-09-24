"""آدرس‌های بخش مقاله و خبر."""

from django.urls import path

from . import views

app_name = "blog"

urlpatterns = [
    path("", views.post_list, name="list"),
    path("<uslug:slug>/", views.post_detail, name="detail"),
]
