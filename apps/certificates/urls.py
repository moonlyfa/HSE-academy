"""آدرس‌های گواهی."""

from django.urls import path

from . import views

app_name = "certificates"

urlpatterns = [
    path("my/", views.my_certificates, name="my"),
    path("issue/<uslug:slug>/", views.certificate_issue, name="issue"),
    path("<str:code>/pdf/", views.certificate_pdf, name="pdf"),
    path("<str:code>/", views.certificate_detail, name="detail"),
]
