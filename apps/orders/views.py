"""
Viewهای سبد خرید، تسویه و سفارش‌ها.

نکته امنیتی که در همه این Viewها رعایت شده: هیچ مبلغی از سمت مرورگر
پذیرفته نمی‌شود. فرم‌ها فقط «کدام دوره» و «کدام کد تخفیف» را می‌فرستند؛
عددها همیشه از دیتابیس خوانده و در سرور حساب می‌شوند.
"""

from __future__ import annotations

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from apps.core.jalali import to_persian_digits
from apps.courses.models import Course

from .cart import Cart
from .models import Order, OrderStatus
from .services import (
    check_coupon,
    create_order,
    mark_order_paid,
    purchased_course_ids,
)

COUPON_SESSION_KEY = "coupon_code"


def _safe_next(request: HttpRequest, fallback: str) -> str:
    """
    بازگشت امن به صفحه قبلی.

    بدون این بررسی، کسی می‌توانست لینکی بسازد که کاربر بعد از افزودن به
    سبد، به سایت جعلی هدایت شود (حمله Open Redirect).
    """
    target = request.POST.get("next") or request.GET.get("next") or ""

    if target and url_has_allowed_host_and_scheme(
        target, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        return target
    return fallback


# ---------------------------------------------------------------------------
# سبد خرید
# ---------------------------------------------------------------------------


def cart_view(request: HttpRequest) -> HttpResponse:
    """صفحه سبد خرید."""
    cart = Cart(request)
    lines = cart.lines
    subtotal = cart.subtotal

    coupon_check = None
    code = request.session.get(COUPON_SESSION_KEY, "")
    if code and lines:
        coupon_check = check_coupon(
            code,
            user=request.user,
            courses=[line.course for line in lines],
            subtotal=subtotal,
        )
        # کدی که دیگر معتبر نیست از Session پاک می‌شود تا در صفحه بعد
        # دوباره پیام خطا تکرار نشود.
        if not coupon_check.valid:
            request.session.pop(COUPON_SESSION_KEY, None)

    discount = coupon_check.discount if coupon_check and coupon_check.valid else 0

    return render(
        request,
        "orders/cart.html",
        {
            "lines": lines,
            "subtotal": subtotal,
            "discount": discount,
            "total": max(subtotal - discount, 0),
            "coupon_check": coupon_check,
            "already_purchased": purchased_course_ids(request.user),
            "nav_active": "cart",
        },
    )


@require_POST
def cart_add(request: HttpRequest, slug: str) -> HttpResponse:
    """
    افزودن دوره به سبد.

    فقط POST است چون وضعیت را تغییر می‌دهد؛ اگر با GET کار می‌کرد، یک
    تصویر یا لینک در صفحه‌ای دیگر می‌توانست بی‌اجازه سبد کاربر را پر کند.
    """
    course = get_object_or_404(Course.objects.published(), slug=slug)
    cart = Cart(request)

    if course.pk in purchased_course_ids(request.user):
        messages.info(request, "شما قبلاً این دوره را خریده‌اید.")
        return redirect(course.get_absolute_url())

    if not course.registration_open:
        messages.error(request, "مهلت ثبت‌نام این دوره به پایان رسیده است.")
        return redirect(course.get_absolute_url())

    if cart.add(course):
        messages.success(request, f"«{course.title}» به سبد خرید اضافه شد.")
    else:
        messages.info(request, "این دوره از قبل در سبد خرید شماست.")

    return redirect(_safe_next(request, reverse("orders:cart")))


@require_POST
def cart_remove(request: HttpRequest, slug: str) -> HttpResponse:
    course = get_object_or_404(Course, slug=slug)

    if Cart(request).remove(course.pk):
        messages.success(request, f"«{course.title}» از سبد خرید حذف شد.")

    return redirect(_safe_next(request, reverse("orders:cart")))


@require_POST
def coupon_apply(request: HttpRequest) -> HttpResponse:
    """
    اعمال کد تخفیف روی سبد.

    خودِ کد در Session ذخیره می‌شود، نه مبلغ تخفیف. یعنی حتی اگر کاربر
    محتوای Session را دستکاری کند، باز هم اعتبار کد و مبلغ تخفیف در سرور
    از نو حساب می‌شود.
    """
    cart = Cart(request)
    lines = cart.lines

    if not lines:
        messages.error(request, "سبد خرید شما خالی است.")
        return redirect("orders:cart")

    result = check_coupon(
        request.POST.get("code", ""),
        user=request.user,
        courses=[line.course for line in lines],
        subtotal=cart.subtotal,
    )

    if result.valid:
        request.session[COUPON_SESSION_KEY] = result.coupon.code
        messages.success(
            request,
            "کد تخفیف اعمال شد. "
            f"{to_persian_digits(f'{result.discount:,}')} تومان تخفیف گرفتید.",
        )
    else:
        request.session.pop(COUPON_SESSION_KEY, None)
        messages.error(request, result.message)

    return redirect(_safe_next(request, reverse("orders:cart")))


@require_POST
def coupon_remove(request: HttpRequest) -> HttpResponse:
    request.session.pop(COUPON_SESSION_KEY, None)
    messages.info(request, "کد تخفیف حذف شد.")
    return redirect("orders:cart")


# ---------------------------------------------------------------------------
# تسویه حساب
# ---------------------------------------------------------------------------


@login_required
def checkout_view(request: HttpRequest) -> HttpResponse:
    """
    صفحه نهایی کردن سفارش.

    با GET خلاصه سفارش نشان داده می‌شود و با POST سفارش ساخته می‌شود.
    ساختن سفارش با GET خطرناک است: رفرش صفحه یا پیش‌بارگذاری مرورگر
    می‌توانست چند سفارش تکراری بسازد.
    """
    cart = Cart(request)
    lines = cart.lines

    if not lines:
        messages.info(request, "برای تسویه حساب، ابتدا دوره‌ای به سبد اضافه کنید.")
        return redirect("courses:list")

    # دوره‌ای که کاربر قبلاً خریده نباید دوباره فاکتور شود.
    purchased = purchased_course_ids(request.user)
    duplicates = [line for line in lines if line.course.pk in purchased]
    if duplicates:
        for line in duplicates:
            cart.remove(line.course.pk)
        messages.info(
            request,
            "دوره‌هایی که قبلاً خریده بودید از سبد حذف شدند.",
        )
        return redirect("orders:cart")

    subtotal = cart.subtotal
    code = request.session.get(COUPON_SESSION_KEY, "")
    coupon_check = (
        check_coupon(
            code,
            user=request.user,
            courses=[line.course for line in lines],
            subtotal=subtotal,
        )
        if code
        else None
    )
    coupon = coupon_check.coupon if coupon_check and coupon_check.valid else None
    discount = coupon_check.discount if coupon_check and coupon_check.valid else 0

    if request.method == "POST":
        order = create_order(
            user=request.user,
            lines=lines,
            coupon=coupon,
            note=request.POST.get("note", "").strip()[:1000],
        )

        cart.clear()
        request.session.pop(COUPON_SESSION_KEY, None)

        # سفارش با مبلغ صفر — دوره رایگان، یا تخفیف صددرصدی — به درگاه
        # فرستاده نمی‌شود. تا پیش از این، چنین سفارشی برای همیشه در حالت
        # «در انتظار پرداخت» می‌ماند چون درگاه مبلغ صفر را نمی‌پذیرد.
        if order.total == 0:
            mark_order_paid(order)
            messages.success(
                request, "ثبت‌نام شما انجام شد و دسترسی به دوره‌ها فعال است."
            )

        return redirect("orders:detail", order_number=order.order_number)

    return render(
        request,
        "orders/checkout.html",
        {
            "lines": lines,
            "subtotal": subtotal,
            "discount": discount,
            "total": max(subtotal - discount, 0),
            "coupon": coupon,
            "nav_active": "cart",
        },
    )


# ---------------------------------------------------------------------------
# سفارش‌های کاربر
# ---------------------------------------------------------------------------


@login_required
def order_list(request: HttpRequest) -> HttpResponse:
    orders = (
        Order.objects.filter(user=request.user)
        .prefetch_related("items")
        .order_by("-created_at")
    )

    return render(request, "orders/order_list.html", {"orders": orders})


@login_required
def order_detail(request: HttpRequest, order_number: str) -> HttpResponse:
    """
    صفحه یک سفارش.

    فیلتر روی user حیاتی است: بدون آن، هرکسی با داشتن شماره سفارش دیگری
    می‌توانست فاکتور و اطلاعات تماس او را ببیند.
    """
    order = get_object_or_404(
        Order.objects.prefetch_related("items", "items__course"),
        order_number=order_number,
        user=request.user,
    )

    return render(
        request,
        "orders/order_detail.html",
        {
            "order": order,
            "statuses": OrderStatus,
            "payments": order.payments.order_by("-created_at"),
            # برای اینکه در محیط آزمایشی، کاربر بداند پرداخت واقعی نیست.
            "mock_payment": settings.USE_MOCK_PAYMENT,
        },
    )


@login_required
@require_POST
def order_cancel(request: HttpRequest, order_number: str) -> HttpResponse:
    """لغو سفارشی که هنوز پرداخت نشده است."""
    order = get_object_or_404(Order, order_number=order_number, user=request.user)

    if order.is_paid:
        messages.error(request, "سفارش پرداخت‌شده قابل لغو نیست.")
    elif order.status == OrderStatus.CANCELED:
        messages.info(request, "این سفارش قبلاً لغو شده است.")
    else:
        order.status = OrderStatus.CANCELED
        order.save(update_fields=["status", "updated_at"])
        messages.success(request, "سفارش لغو شد.")

    return redirect(order.get_absolute_url())
