"""آدرس‌های آزمون."""

from django.urls import path

from . import views

app_name = "exams"

urlpatterns = [
    path("my/", views.my_exams, name="my"),
    path("attempt/<int:pk>/", views.attempt_take, name="take"),
    path("attempt/<int:pk>/answer/", views.attempt_answer, name="answer"),
    path("attempt/<int:pk>/result/", views.attempt_result, name="result"),
    # اسلاگ دوره در آخر می‌آید تا آدرس‌های ثابت بالا را نبلعد.
    path("<uslug:slug>/start/", views.attempt_start, name="start"),
    path("<uslug:slug>/", views.exam_detail, name="detail"),
]
