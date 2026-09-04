"""
Viewهای ورود، ثبت‌نام و حساب کاربری.

منطق امنیتی (محدودسازی تلاش) در ماژول throttling نگه داشته شده تا
این فایل فقط جریان صفحه‌ها را توصیف کند.
"""

import logging
from datetime import datetime

from django.contrib import messages
from django.contrib.auth import login as auth_login
from django.contrib.auth import logout as auth_logout
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.conf import settings
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme

from apps.courses.progress import learner_courses, learner_stats

from .forms import (
    ChangePasswordForm,
    CompleteRegistrationForm,
    LoginForm,
    OtpVerifyForm,
    PasswordResetMobileForm,
    ProfileForm,
    NationalCodeForm,
    RegisterMobileForm,
    SetNewPasswordForm,
)
from .models import OtpPurpose
from .services.identity import verify_identity
from .services.otp import seconds_until_resend, send_otp, verify_otp
from .throttling import (
    LOCKOUT_SECONDS,
    get_client_ip,
    clear_attempts,
    is_locked_out,
    mask_mobile,
    register_failed_attempt,
)

logger = logging.getLogger("hse.accounts")

User = get_user_model()


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


# ---------------------------------------------------------------------------
# مدیریت وضعیت جریان چندمرحله‌ای در Session
# ---------------------------------------------------------------------------
# بین مرحله «وارد کردن موبایل» تا «تکمیل ثبت‌نام» باید بدانیم کاربر کدام
# شماره را تأیید کرده. این اطلاعات در Session سرور نگه داشته می‌شود، نه در
# آدرس یا فرم — وگرنه کاربر می‌توانست با دست‌کاری آن، مرحله تأیید پیامکی
# را کامل دور بزند.

# اعتبار وضعیت «تأیید شده» برای تکمیل مراحل بعدی
VERIFIED_STATE_SECONDS = 15 * 60


def _pending_key(purpose: str) -> str:
    return f"otp_pending_{purpose}"


def _verified_key(purpose: str) -> str:
    return f"otp_verified_{purpose}"


def _set_pending_mobile(request: HttpRequest, mobile: str, purpose: str) -> None:
    request.session[_pending_key(purpose)] = mobile


def _get_pending_mobile(request: HttpRequest, purpose: str) -> str | None:
    return request.session.get(_pending_key(purpose))


def _mark_verified(request: HttpRequest, mobile: str, purpose: str) -> None:
    request.session[_verified_key(purpose)] = {
        "mobile": mobile,
        "at": timezone.now().isoformat(),
    }
    request.session.pop(_pending_key(purpose), None)


def _get_verified_mobile(request: HttpRequest, purpose: str) -> str | None:
    """
    شماره‌ای که کاربر در این جریان تأیید کرده است.

    اگر بیش از حد مجاز از تأیید گذشته باشد، وضعیت باطل می‌شود تا کسی
    نتواند یک Session قدیمی را روزها بعد برای ساخت حساب استفاده کند.
    """
    data = request.session.get(_verified_key(purpose))
    if not isinstance(data, dict):
        return None

    try:
        verified_at = datetime.fromisoformat(data["at"])
    except (KeyError, TypeError, ValueError):
        return None

    if (timezone.now() - verified_at).total_seconds() > VERIFIED_STATE_SECONDS:
        request.session.pop(_verified_key(purpose), None)
        return None

    return data.get("mobile")


def _clear_flow(request: HttpRequest, purpose: str) -> None:
    request.session.pop(_pending_key(purpose), None)
    request.session.pop(_verified_key(purpose), None)


def _send_and_report(request: HttpRequest, mobile: str, purpose: str) -> bool:
    """ارسال کد و نمایش پیام مناسب به کاربر."""
    result = send_otp(mobile, purpose, ip_address=get_client_ip(request))

    if result.success:
        messages.success(request, result.message)
    else:
        messages.error(request, result.message)

    return result.success


# ---------------------------------------------------------------------------
# ثبت‌نام سه‌مرحله‌ای: شماره موبایل ← کد پیامکی ← تکمیل اطلاعات
# ---------------------------------------------------------------------------


def register_view(request: HttpRequest) -> HttpResponse:
    """گام ۱ — گرفتن شماره موبایل و ارسال کد تأیید."""
    if request.user.is_authenticated:
        return redirect("accounts:dashboard")

    form = RegisterMobileForm()

    if request.method == "POST":
        form = RegisterMobileForm(request.POST)
        if form.is_valid():
            mobile = form.cleaned_data["mobile"]

            if _send_and_report(request, mobile, OtpPurpose.REGISTER):
                _set_pending_mobile(request, mobile, OtpPurpose.REGISTER)
                return redirect("accounts:register_verify")

    return render(request, "accounts/register_mobile.html", {"form": form})


def register_verify_view(request: HttpRequest) -> HttpResponse:
    """گام ۲ — تأیید کد پیامک‌شده."""
    if request.user.is_authenticated:
        return redirect("accounts:dashboard")

    mobile = _get_pending_mobile(request, OtpPurpose.REGISTER)
    if not mobile:
        messages.info(request, "لطفاً ابتدا شماره موبایل خود را وارد کنید.")
        return redirect("accounts:register")

    form = OtpVerifyForm()

    if request.method == "POST":
        # درخواست ارسال مجدد کد
        if "resend" in request.POST:
            _send_and_report(request, mobile, OtpPurpose.REGISTER)
            return redirect("accounts:register_verify")

        form = OtpVerifyForm(request.POST)
        if form.is_valid():
            result = verify_otp(mobile, OtpPurpose.REGISTER, form.cleaned_data["code"])

            if result.success:
                _mark_verified(request, mobile, OtpPurpose.REGISTER)
                return redirect("accounts:register_complete")

            messages.error(request, result.message)

    return render(
        request,
        "accounts/otp_verify.html",
        {
            "form": form,
            "mobile": mobile,
            "resend_in": seconds_until_resend(mobile, OtpPurpose.REGISTER),
            "edit_url": reverse("accounts:register"),
            "title": "تأیید شماره موبایل",
            "show_steps": True,
        },
    )


IDENTITY_SESSION_KEY = "register_identity_verified"


def register_identity_view(request: HttpRequest) -> HttpResponse:
    """
    گام ۳ — استعلام تطبیق کد ملی با شماره موبایل.

    نکته مهم: بین «سرویس در دسترس نبود» و «کد ملی با شماره تطبیق ندارد»
    تفاوت قائل می‌شویم. اولی خطای ماست و کاربر باید بتواند دوباره تلاش
    کند؛ دومی یعنی واقعاً هویت تأیید نشده است.
    """
    if request.user.is_authenticated:
        return redirect("accounts:dashboard")

    mobile = _get_verified_mobile(request, OtpPurpose.REGISTER)
    if not mobile:
        messages.info(request, "برای ادامه، ابتدا شماره موبایل خود را تأیید کنید.")
        return redirect("accounts:register")

    form = NationalCodeForm()

    if request.method == "POST":
        form = NationalCodeForm(request.POST)
        if form.is_valid():
            national_code = form.cleaned_data["national_code"]
            result = verify_identity(
                mobile, national_code, ip_address=get_client_ip(request)
            )

            if result.success and result.matched:
                request.session[IDENTITY_SESSION_KEY] = national_code
                messages.success(request, "احراز هویت شما با موفقیت انجام شد.")
                return redirect("accounts:register_complete")

            if result.success and not result.matched:
                # سرویس جواب داد و گفت تطبیق ندارد — این خطای واقعی کاربر است.
                form.add_error(
                    "national_code",
                    "کد ملی واردشده با این شماره موبایل مطابقت ندارد. "
                    "لطفاً کد ملی صاحب همین شماره را وارد کنید.",
                )
            else:
                # سرویس در دسترس نبود — تقصیر کاربر نیست.
                messages.error(request, result.message)

    return render(
        request,
        "accounts/register_identity.html",
        {"form": form, "mobile": mobile},
    )


def register_complete_view(request: HttpRequest) -> HttpResponse:
    """گام ۴ — تکمیل نام و انتخاب رمز عبور."""
    if request.user.is_authenticated:
        return redirect("accounts:dashboard")

    mobile = _get_verified_mobile(request, OtpPurpose.REGISTER)
    if not mobile:
        messages.info(request, "برای ادامه، ابتدا شماره موبایل خود را تأیید کنید.")
        return redirect("accounts:register")

    national_code = request.session.get(IDENTITY_SESSION_KEY)

    # اگر احراز هویت اجباری است، بدون آن نمی‌توان به این مرحله رسید.
    if settings.IDENTITY_REQUIRED_FOR_REGISTRATION and not national_code:
        messages.info(request, "برای تکمیل ثبت‌نام، ابتدا احراز هویت را انجام دهید.")
        return redirect("accounts:register_identity")

    form = CompleteRegistrationForm()

    if request.method == "POST":
        form = CompleteRegistrationForm(request.POST)
        if form.is_valid():
            user = form.create_user(mobile)

            if national_code:
                user.national_code = national_code
                user.is_identity_verified = True
                user.save(update_fields=["national_code", "is_identity_verified", "updated_at"])
                # سابقه استعلام را به کاربر تازه‌ساخته وصل می‌کنیم.
                user.identity_verifications.model.objects.filter(
                    mobile=mobile, user__isnull=True
                ).update(user=user)

            _clear_flow(request, OtpPurpose.REGISTER)
            request.session.pop(IDENTITY_SESSION_KEY, None)

            auth_login(request, user)
            logger.info("ثبت‌نام کامل شد. موبایل=%s", mask_mobile(user.mobile))
            messages.success(request, "ثبت‌نام شما با موفقیت انجام شد.")
            return redirect("accounts:dashboard")

        messages.error(request, "لطفاً خطاهای فرم را برطرف کنید.")

    return render(
        request,
        "accounts/register_complete.html",
        {"form": form, "mobile": mobile},
    )


# ---------------------------------------------------------------------------
# بازیابی رمز عبور با کد پیامکی
# ---------------------------------------------------------------------------


def password_reset_view(request: HttpRequest) -> HttpResponse:
    """گام ۱ — گرفتن شماره موبایل."""
    form = PasswordResetMobileForm()

    if request.method == "POST":
        form = PasswordResetMobileForm(request.POST)
        if form.is_valid():
            mobile = form.cleaned_data["mobile"]

            # اگر شماره در سایت نباشد، عمداً همان پیام موفقیت را نشان
            # می‌دهیم و کدی نمی‌فرستیم. این‌طور کسی نمی‌تواند با این فرم
            # بفهمد چه شماره‌هایی در سایت حساب دارند.
            if User.objects.filter(mobile=mobile, is_active=True).exists():
                send_otp(mobile, OtpPurpose.PASSWORD_RESET, get_client_ip(request))
            else:
                logger.info(
                    "درخواست بازیابی برای شماره ناموجود. موبایل=%s", mask_mobile(mobile)
                )

            _set_pending_mobile(request, mobile, OtpPurpose.PASSWORD_RESET)
            messages.success(
                request, "اگر این شماره در سایت ثبت شده باشد، کد تأیید ارسال می‌شود."
            )
            return redirect("accounts:password_reset_verify")

    return render(request, "accounts/password_reset.html", {"form": form})


def password_reset_verify_view(request: HttpRequest) -> HttpResponse:
    """گام ۲ — تأیید کد."""
    mobile = _get_pending_mobile(request, OtpPurpose.PASSWORD_RESET)
    if not mobile:
        return redirect("accounts:password_reset")

    form = OtpVerifyForm()

    if request.method == "POST":
        if "resend" in request.POST:
            if User.objects.filter(mobile=mobile, is_active=True).exists():
                _send_and_report(request, mobile, OtpPurpose.PASSWORD_RESET)
            return redirect("accounts:password_reset_verify")

        form = OtpVerifyForm(request.POST)
        if form.is_valid():
            result = verify_otp(
                mobile, OtpPurpose.PASSWORD_RESET, form.cleaned_data["code"]
            )

            if result.success:
                _mark_verified(request, mobile, OtpPurpose.PASSWORD_RESET)
                return redirect("accounts:password_reset_new")

            messages.error(request, result.message)

    return render(
        request,
        "accounts/otp_verify.html",
        {
            "form": form,
            "mobile": mobile,
            "resend_in": seconds_until_resend(mobile, OtpPurpose.PASSWORD_RESET),
            "edit_url": reverse("accounts:password_reset"),
            "title": "بازیابی رمز عبور",
        },
    )


def password_reset_new_view(request: HttpRequest) -> HttpResponse:
    """گام ۳ — انتخاب رمز جدید."""
    mobile = _get_verified_mobile(request, OtpPurpose.PASSWORD_RESET)
    if not mobile:
        messages.info(request, "برای تغییر رمز، ابتدا شماره خود را تأیید کنید.")
        return redirect("accounts:password_reset")

    user = User.objects.filter(mobile=mobile, is_active=True).first()
    if user is None:
        _clear_flow(request, OtpPurpose.PASSWORD_RESET)
        return redirect("accounts:password_reset")

    form = SetNewPasswordForm()

    if request.method == "POST":
        form = SetNewPasswordForm(request.POST)
        if form.is_valid():
            user.set_password(form.cleaned_data["new_password1"])
            user.save(update_fields=["password", "updated_at"])

            _clear_flow(request, OtpPurpose.PASSWORD_RESET)
            logger.info("رمز عبور بازیابی شد. موبایل=%s", mask_mobile(mobile))

            messages.success(
                request, "رمز عبور شما تغییر کرد. اکنون می‌توانید وارد شوید."
            )
            return redirect("accounts:login")

    return render(request, "accounts/password_reset_new.html", {"form": form})


# ---------------------------------------------------------------------------
# تأیید شماره موبایل برای کاربری که قبلاً ثبت‌نام کرده
# ---------------------------------------------------------------------------


@login_required
def verify_mobile_view(request: HttpRequest) -> HttpResponse:
    """تأیید شماره موبایل کاربر وارد شده."""
    user = request.user

    if user.is_mobile_verified:
        messages.info(request, "شماره موبایل شما قبلاً تأیید شده است.")
        return redirect("accounts:dashboard")

    purpose = OtpPurpose.VERIFY_MOBILE
    form = OtpVerifyForm()
    code_sent = _get_pending_mobile(request, purpose) == user.mobile

    if request.method == "POST":
        if "send" in request.POST or "resend" in request.POST:
            if _send_and_report(request, user.mobile, purpose):
                _set_pending_mobile(request, user.mobile, purpose)
            return redirect("accounts:verify_mobile")

        form = OtpVerifyForm(request.POST)
        if form.is_valid():
            result = verify_otp(user.mobile, purpose, form.cleaned_data["code"])

            if result.success:
                user.is_mobile_verified = True
                user.save(update_fields=["is_mobile_verified", "updated_at"])
                _clear_flow(request, purpose)

                logger.info("موبایل تأیید شد. موبایل=%s", mask_mobile(user.mobile))
                messages.success(request, "شماره موبایل شما با موفقیت تأیید شد.")
                return redirect("accounts:dashboard")

            messages.error(request, result.message)

    return render(
        request,
        "accounts/verify_mobile.html",
        {
            "form": form,
            "code_sent": code_sent,
            "resend_in": seconds_until_resend(user.mobile, purpose),
        },
    )


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
def verify_identity_view(request: HttpRequest) -> HttpResponse:
    """احراز هویت برای کاربری که قبلاً ثبت‌نام کرده است."""
    user = request.user

    if user.is_identity_verified:
        messages.info(request, "هویت شما قبلاً تأیید شده است.")
        return redirect("accounts:dashboard")

    form = NationalCodeForm()

    if request.method == "POST":
        form = NationalCodeForm(request.POST)
        if form.is_valid():
            national_code = form.cleaned_data["national_code"]
            result = verify_identity(
                user.mobile, national_code, user=user, ip_address=get_client_ip(request)
            )

            if result.success and result.matched:
                user.national_code = national_code
                user.is_identity_verified = True
                user.save(
                    update_fields=["national_code", "is_identity_verified", "updated_at"]
                )
                messages.success(request, "احراز هویت شما با موفقیت انجام شد.")
                return redirect("accounts:dashboard")

            if result.success and not result.matched:
                form.add_error(
                    "national_code",
                    "کد ملی واردشده با شماره موبایل شما مطابقت ندارد.",
                )
            else:
                messages.error(request, result.message)

    return render(request, "accounts/verify_identity.html", {"form": form})


@login_required
def dashboard_view(request: HttpRequest) -> HttpResponse:
    """
    داشبورد دانشجو.

    سه چیز را نشان می‌دهد: وضعیت حساب، خلاصه عددی یادگیری، و مهم‌تر از
    همه دکمه «ادامه یادگیری» که کاربر را دقیقاً به همان درسی می‌برد که
    آخرین بار رهایش کرده بود.
    """
    courses = learner_courses(request.user)

    # فهرست بر اساس تازه‌ترین فعالیت مرتب است، پس اولین مورد همان دوره‌ای
    # است که کاربر آخرین بار سراغش رفته. مقصد دکمه، «درس بعدیِ ناتمام»
    # است نه آخرین درسی که باز کرده — وگرنه کاربر دوباره به درسی می‌رود
    # که همین حالا تمامش کرده است.
    current = courses[0] if courses else None

    return render(
        request,
        "accounts/dashboard.html",
        {
            "stats": learner_stats(request.user),
            "recent_courses": courses[:3],
            "current_progress": current,
            "resume_lesson": current.resume_lesson if current else None,
        },
    )


@login_required
def my_courses_view(request: HttpRequest) -> HttpResponse:
    """
    فهرست دوره‌های کاربر با درصد پیشرفت هرکدام.

    امروز «دوره من» یعنی دوره‌ای که کاربر حداقل یک درسش را باز کرده است؛
    در فاز ۱۴ دوره‌های خریداری‌شده هم به همین فهرست اضافه می‌شوند.
    """
    progresses = learner_courses(request.user)

    return render(
        request,
        "accounts/my_courses.html",
        {
            "progresses": progresses,
            "in_progress": [p for p in progresses if not p.is_finished],
            "finished": [p for p in progresses if p.is_finished],
        },
    )


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
