"""آدرس‌های حساب کاربری."""

from django.urls import path

from . import views

app_name = "accounts"

urlpatterns = [
    # --- ورود و خروج ---
    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),

    # --- ثبت‌نام سه‌مرحله‌ای ---
    path("register/", views.register_view, name="register"),
    path("register/verify/", views.register_verify_view, name="register_verify"),
    path("register/identity/", views.register_identity_view, name="register_identity"),
    path("register/complete/", views.register_complete_view, name="register_complete"),

    # --- بازیابی رمز عبور با پیامک ---
    path("password/reset/", views.password_reset_view, name="password_reset"),
    path("password/reset/verify/", views.password_reset_verify_view, name="password_reset_verify"),
    path("password/reset/new/", views.password_reset_new_view, name="password_reset_new"),

    # --- حساب کاربری ---
    path("dashboard/", views.dashboard_view, name="dashboard"),
    path("my-courses/", views.my_courses_view, name="my_courses"),
    path("profile/", views.profile_view, name="profile"),
    path("password/", views.change_password_view, name="change_password"),
    path("verify-mobile/", views.verify_mobile_view, name="verify_mobile"),
    path("verify-identity/", views.verify_identity_view, name="verify_identity"),
]
