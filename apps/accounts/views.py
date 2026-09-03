"""
Viewهای ورود، ثبت‌نام و حساب کاربری.

منطق امنیتی (محدودسازی تلاش) در ماژول throttling نگه داشته شده تا
این فایل فقط جریان صفحه‌ها را توصیف کند.
"""

import logging

from django.contrib import messages
from django.contrib.auth import login as auth_login
from django.contrib.auth import logout as auth_logout
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme

from .forms import ChangePasswordForm, LoginForm, ProfileForm, RegisterForm
from .throttling import (
    LOCKOUT_SECONDS,
    clear_attempts,
    is_locked_out,
    mask_mobile,
    register_failed_attempt,
)

logger = logging.getLogger("hse.accounts")


def _safe_redirect_target(request: HttpRequest, fallback: str) -> str:
    """
    آدرس بازگشت بعد از ورود.

    اگر آدرس next را بدون بررسی قبول کنیم، مهاجم می‌تواند لینکی بسازد که
    کاربر بعد از ورود به سایت جعلی هدایت شود (Open Redirect). این تابع
    فقط آدرس‌های داخل همین سایت را می‌پذیرد.
    """
    target = request.POST.get("next") or request.GET.get("next")

    if target and url_has_allowed_host_and_scheme(
        url=target,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return target
    return fallback


def login_view(request: HttpRequest) -> HttpResponse:
    """ورود با شماره موبایل و رمز عبور."""
    if request.user.is_authenticated:
        return redirect("accounts:dashboard")

    form = LoginForm(request=request)

    if request.method == "POST":
        form = LoginForm(request, data=request.POST)
        # شماره را حتی وقتی فرم نامعتبر است می‌خواهیم، تا شمارنده تلاش را بسازیم.
        submitted_mobile = form.data.get("mobile", "")

        if is_locked_out(request, submitted_mobile):
            messages.error(
                request,
                "به دلیل تلاش‌های ناموفق متعدد، ورود با این شماره موقتاً "
                f"مسدود شده است. لطفاً {LOCKOUT_SECONDS // 60} دقیقه دیگر تلاش کنید.",
            )
        elif form.is_valid():
            user = form.user
            auth_login(request, user)
            clear_attempts(request, user.mobile)

            logger.info("ورود موفق. موبایل=%s", mask_mobile(user.mobile))
            messages.success(request, f"خوش آمدید، {user.get_short_name()}.")

            return redirect(_safe_redirect_target(request, reverse("accounts:dashboard")))
        else:
            left = register_failed_attempt(request, submitted_mobile)
            logger.info("ورود ناموفق. موبایل=%s", mask_mobile(submitted_mobile))

            if 0 < left <= 2:
                messages.warning(request, f"{left} تلاش دیگر باقی مانده است.")

    return render(
        request,
        "accounts/login.html",
        {"form": form, "next": request.GET.get("next", "")},
    )


def register_view(request: HttpRequest) -> HttpResponse:
    """
    ثبت‌نام کاربر جدید.

    در فاز ۴ بین ثبت فرم و ورود خودکار، مرحله تأیید کد پیامکی اضافه
    می‌شود. تا آن زمان حساب ساخته و کاربر وارد می‌شود، اما فیلد
    is_mobile_verified همچنان False می‌ماند.
    """
    if request.user.is_authenticated:
        return redirect("accounts:dashboard")

    form = RegisterForm()

    if request.method == "POST":
        form = RegisterForm(request.POST)
        if form.is_valid():
            user = form.save()
            auth_login(request, user)

            logger.info("ثبت‌نام جدید. موبایل=%s", mask_mobile(user.mobile))
            messages.success(
                request,
                "ثبت‌نام شما با موفقیت انجام شد. برای دسترسی کامل، "
                "احراز هویت خود را تکمیل کنید.",
            )
            return redirect("accounts:dashboard")

        messages.error(request, "لطفاً خطاهای فرم را برطرف کنید.")

    return render(request, "accounts/register.html", {"form": form})


def logout_view(request: HttpRequest) -> HttpResponse:
    """
    خروج از حساب — با تأیید کاربر.

    خروج فقط با POST انجام می‌شود. اگر با GET ممکن بود، مهاجم می‌توانست
    با گذاشتن یک تصویر مخفی در صفحه‌ای دیگر، کاربر را ناخواسته خارج کند.

    درخواست GET صفحه تأیید را نشان می‌دهد. این صفحه پشتیبانِ پنجره تأیید
    است: کاربرانی که جاوااسکریپت ندارند هم باید بتوانند خارج شوند.
    """
    if request.method == "POST":
        auth_logout(request)
        messages.info(request, "از حساب کاربری خارج شدید.")
        return redirect("core:home")

    if not request.user.is_authenticated:
        return redirect("core:home")

    return render(request, "accounts/logout_confirm.html")


@login_required
def dashboard_view(request: HttpRequest) -> HttpResponse:
    """
    داشبورد دانشجو — نسخه اولیه.

    داشبورد کامل با دوره‌ها، آزمون‌ها و گواهی‌ها در فاز ۱۰ ساخته می‌شود.
    """
    return render(request, "accounts/dashboard.html")


@login_required
def profile_view(request: HttpRequest) -> HttpResponse:
    """ویرایش اطلاعات شخصی."""
    form = ProfileForm(instance=request.user)

    if request.method == "POST":
        form = ProfileForm(request.POST, instance=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, "اطلاعات شما با موفقیت ذخیره شد.")
            return redirect("accounts:profile")
        messages.error(request, "لطفاً خطاهای فرم را برطرف کنید.")

    return render(request, "accounts/profile.html", {"form": form})


@login_required
def change_password_view(request: HttpRequest) -> HttpResponse:
    """تغییر رمز عبور."""
    form = ChangePasswordForm(request.user)

    if request.method == "POST":
        form = ChangePasswordForm(request.user, request.POST)
        if form.is_valid():
            form.save()
            # بدون این خط، کاربر بعد از تغییر رمز از حساب خودش بیرون می‌افتد.
            update_session_auth_hash(request, request.user)

            logger.info("تغییر رمز عبور. موبایل=%s", mask_mobile(request.user.mobile))
            messages.success(request, "رمز عبور شما با موفقیت تغییر کرد.")
            return redirect("accounts:profile")
        messages.error(request, "لطفاً خطاهای فرم را برطرف کنید.")

    return render(request, "accounts/change_password.html", {"form": form})
