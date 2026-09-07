"""
منطق کد تخفیف و ساخت سفارش.

هرچه به پول مربوط است اینجا جمع شده تا در یک نگاه بشود دید مبلغ نهایی
چطور حساب می‌شود — و مطمئن شد که هیچ عددی از سمت مرورگر نمی‌آید.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from django.db import transaction
from django.utils import timezone

from apps.core.jalali import to_persian_digits
from apps.courses.models import Course

from .models import Coupon, Order, OrderItem, OrderStatus

logger = logging.getLogger("hse.orders")


@dataclass(frozen=True)
class CouponCheck:
    """نتیجه بررسی یک کد تخفیف."""

    valid: bool
    coupon: Coupon | None = None
    message: str = ""
    discount: int = 0

    def __bool__(self) -> bool:
        return self.valid


def check_coupon(code: str, *, user, courses: list[Course], subtotal: int) -> CouponCheck:
    """
    بررسی اینکه این کد برای این کاربر و این سبد معتبر است یا نه.

    پیام خطا عمداً مشخص است («منقضی شده»، «سقف استفاده») چون کاربر باید
    بفهمد مشکل از کجاست. اما نمی‌گوییم «این کد وجود دارد ولی برای شما نیست»
    به شکلی که بشود کدهای فعال سایت را حدس زد.
    """
    code = (code or "").strip().upper()
    if not code:
        return CouponCheck(False, message="کد تخفیف را وارد کنید.")

    coupon = Coupon.objects.filter(code=code, is_active=True).first()
    if coupon is None:
        return CouponCheck(False, message="کد تخفیف واردشده معتبر نیست.")

    if coupon.is_expired:
        return CouponCheck(False, message="مهلت استفاده از این کد تخفیف تمام شده است.")

    if coupon.is_exhausted:
        return CouponCheck(False, message="ظرفیت استفاده از این کد تخفیف تکمیل شده است.")

    if subtotal < coupon.min_order_amount:
        # مبلغ‌ها در متن فارسی باید با ارقام فارسی نوشته شوند، وگرنه وسط
        # جمله فارسی یک عدد انگلیسی می‌نشیند و بد خوانده می‌شود.
        return CouponCheck(
            False,
            message=(
                "این کد برای سفارش‌های بالای "
                f"{to_persian_digits(f'{coupon.min_order_amount:,}')} تومان است."
            ),
        )

    # محدودیت تعداد استفاده هر کاربر — فقط سفارش‌های پرداخت‌شده حساب می‌شوند،
    # چون سفارش رهاشده نباید سهمیه کاربر را بسوزاند.
    if user.is_authenticated and coupon.per_user_limit:
        used = Order.objects.filter(
            user=user, coupon=coupon, status=OrderStatus.PAID
        ).count()
        if used >= coupon.per_user_limit:
            return CouponCheck(
                False, message="شما قبلاً از این کد تخفیف استفاده کرده‌اید."
            )

    # محدودیت به دوره‌های خاص
    allowed_ids = set(coupon.courses.values_list("pk", flat=True))
    if allowed_ids and not any(course.pk in allowed_ids for course in courses):
        return CouponCheck(
            False, message="این کد تخفیف برای دوره‌های داخل سبد شما معتبر نیست."
        )

    discount = coupon.discount_for(subtotal)
    if discount <= 0:
        return CouponCheck(False, message="این کد روی سبد فعلی تخفیفی ایجاد نمی‌کند.")

    return CouponCheck(True, coupon=coupon, discount=discount)


def purchased_course_ids(user) -> set[int]:
    """
    دوره‌هایی که کاربر قبلاً خریده است.

    تا وقتی مدل ثبت‌نام (فاز ۱۴) ساخته نشده، «خریده» یعنی در یک سفارش
    پرداخت‌شده وجود دارد. همین منبع بعداً مبنای ساخت ثبت‌نام هم خواهد بود.
    """
    if not user.is_authenticated:
        return set()

    return set(
        OrderItem.objects.filter(
            order__user=user, order__status=OrderStatus.PAID
        ).values_list("course_id", flat=True)
    )


@transaction.atomic
def create_order(*, user, lines, coupon: Coupon | None = None, note: str = "") -> Order:
    """
    ساخت سفارش از روی سبد.

    داخل transaction انجام می‌شود: یا سفارش با همه اقلامش ساخته می‌شود، یا
    هیچ‌کدام. سفارشی که نصفه ساخته شده باشد (سرآیند بدون قلم) فاکتور
    خالی و مبلغ صفر تولید می‌کند.

    قیمت‌ها از روی آبجکت دوره خوانده می‌شوند — یعنی از دیتابیس — نه از
    چیزی که مرورگر فرستاده است.
    """
    order = Order.objects.create(
        user=user,
        coupon=coupon,
        coupon_code=coupon.code if coupon else "",
        full_name=user.get_full_name(),
        mobile=user.mobile,
        note=note,
    )

    OrderItem.objects.bulk_create(
        [
            OrderItem(
                order=order,
                course=line.course,
                title=line.course.title,
                unit_price=line.course.price,
                final_price=line.course.final_price,
            )
            for line in lines
        ]
    )

    order.recalculate()

    logger.info(
        "سفارش ثبت شد. شماره=%s کاربر=%s تعداد=%s مبلغ=%s",
        order.order_number,
        user.masked_mobile,
        order.item_count,
        order.total,
    )
    return order


def mark_order_paid(order: Order) -> None:
    """
    ثبت پرداخت موفق یک سفارش.

    تنها جایی که وضعیت سفارش به «پرداخت شده» تغییر می‌کند. در فاز ۱۲ و ۱۳
    فقط بعد از تأیید سمت سرورِ درگاه صدا زده می‌شود.
    """
    if order.is_paid:
        return

    with transaction.atomic():
        order.mark_paid()

        if order.coupon:
            # F() یعنی افزایش در خود دیتابیس انجام شود؛ اگر دو پرداخت
            # هم‌زمان برسند، هیچ‌کدام شمارش دیگری را پاک نمی‌کند.
            from django.db.models import F

            Coupon.objects.filter(pk=order.coupon_id).update(
                used_count=F("used_count") + 1
            )

    logger.info(
        "پرداخت سفارش تأیید شد. شماره=%s مبلغ=%s زمان=%s",
        order.order_number,
        order.total,
        timezone.now().isoformat(timespec="seconds"),
    )
