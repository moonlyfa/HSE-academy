"""
ثبت‌نام دانشجو در دوره.

«ثبت‌نام» یعنی این جمله: *این شخص به این دوره دسترسی دارد*. منبعش می‌تواند
خرید باشد، دوره رایگان، اشتراک ویژه، یا افزودن دستی توسط پشتیبانی — اما
پاسخ سؤال دسترسی همیشه از همین‌جا می‌آید.

چرا همه اینها در یک فایل جمع شده‌اند؟ چون ساختن ثبت‌نام از چند جا صدا زده
می‌شود (تأیید پرداخت، دوره رایگان، پنل مدیریت) و اگر هرکدام قاعده خودش را
داشته باشد، روزی یکی از آن‌ها مدت دسترسی را اشتباه حساب می‌کند.
"""

from __future__ import annotations

import logging
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from .models import Course, Enrollment, EnrollmentSource, EnrollmentStatus

logger = logging.getLogger("hse.enrollment")


def expiry_for(course: Course, start=None):
    """
    تاریخ پایان دسترسی یک دوره.

    None یعنی دسترسی دائمی — همان حالتی که بیشتر دوره‌های ضبط‌شده دارند.
    """
    if not course.access_duration_days:
        return None

    return (start or timezone.now()) + timedelta(days=course.access_duration_days)


@transaction.atomic
def enroll(
    user,
    course: Course,
    *,
    source: str = EnrollmentSource.PURCHASE,
    order=None,
    note: str = "",
) -> Enrollment:
    """
    ثبت‌نام کاربر در دوره.

    اگر کاربر قبلاً ثبت‌نام داشته باشد، ردیف تازه ساخته نمی‌شود؛ همان
    ردیف **تمدید** می‌شود. چرا؟ چون یک کاربر در یک دوره یک دسترسی دارد،
    نه چند تا. اگر کسی دوره‌ای را دوباره بخرد (مثلاً بعد از انقضا)، انتظار
    دارد دسترسی‌اش تمدید شود — نه اینکه دو ردیف موازی داشته باشد که
    معلوم نیست کدامشان ملاک است.
    """
    enrollment = Enrollment.objects.select_for_update().filter(
        user=user, course=course
    ).first()

    now = timezone.now()

    if enrollment is None:
        enrollment = Enrollment.objects.create(
            user=user,
            course=course,
            source=source,
            order=order,
            note=note,
            starts_at=now,
            expires_at=expiry_for(course, now),
        )
        logger.info(
            "ثبت‌نام جدید. کاربر=%s دوره=%s منبع=%s",
            user.masked_mobile,
            course.slug,
            source,
        )
        return enrollment

    # --- تمدید ثبت‌نام موجود ---
    #
    # اگر دسترسی هنوز اعتبار دارد، مدت جدید به انتهای همان اضافه می‌شود
    # (نه از امروز) تا کاربری که زودتر تمدید کرده، روزهای باقی‌مانده‌اش
    # را از دست ندهد.
    if course.access_duration_days:
        base = (
            enrollment.expires_at
            if enrollment.expires_at and enrollment.expires_at > now
            else now
        )
        enrollment.expires_at = base + timedelta(days=course.access_duration_days)
    else:
        enrollment.expires_at = None

    enrollment.status = EnrollmentStatus.ACTIVE
    enrollment.source = source
    if order is not None:
        enrollment.order = order
    if note:
        enrollment.note = note

    enrollment.save(
        update_fields=["status", "source", "order", "note", "expires_at", "updated_at"]
    )

    logger.info(
        "ثبت‌نام تمدید شد. کاربر=%s دوره=%s تا=%s",
        user.masked_mobile,
        course.slug,
        enrollment.expires_at.date() if enrollment.expires_at else "دائمی",
    )
    return enrollment


def enroll_from_order(order) -> list[Enrollment]:
    """
    ساخت ثبت‌نام برای همه دوره‌های یک سفارش پرداخت‌شده.

    فقط برای سفارش پرداخت‌شده اجرا می‌شود. این شرط اینجا هم بررسی می‌شود
    — نه فقط در جایی که صدا زده می‌شود — چون همین یک تابع، مرزِ بین
    «پول داده» و «دسترسی دارد» است.
    """
    from apps.orders.models import OrderStatus

    if order.status != OrderStatus.PAID:
        logger.warning(
            "تلاش برای ثبت‌نام از سفارش پرداخت‌نشده. شماره=%s وضعیت=%s",
            order.order_number,
            order.status,
        )
        return []

    return [
        enroll(
            order.user,
            item.course,
            source=EnrollmentSource.PURCHASE,
            order=order,
        )
        for item in order.items.select_related("course")
    ]


def active_enrollment(user, course: Course) -> Enrollment | None:
    """ثبت‌نام فعال کاربر در این دوره، اگر وجود داشته باشد."""
    if not user.is_authenticated:
        return None

    enrollment = Enrollment.objects.filter(user=user, course=course).first()
    return enrollment if enrollment and enrollment.is_active else None


def has_access(user, course: Course) -> bool:
    """
    آیا این کاربر به محتوای این دوره دسترسی دارد؟

    دو راه وجود دارد: ثبت‌نام مستقیم، یا اشتراک ویژه فعال. اشتراک ویژه
    فقط دوره‌هایی را باز می‌کند که مدیر آن‌ها را در دسترس کاربران ویژه
    گذاشته باشد.
    """
    if not user.is_authenticated:
        return False

    if active_enrollment(user, course) is not None:
        return True

    return bool(course.vip_access and user.has_active_vip)


def revoke(enrollment: Enrollment, *, status: str = EnrollmentStatus.SUSPENDED, note: str = "") -> None:
    """
    بستن دسترسی — مثلاً بعد از بازگشت وجه.

    ردیف ثبت‌نام حذف نمی‌شود، فقط وضعیتش عوض می‌شود. حذف کردنش یعنی
    پاک کردن تاریخچه‌ای که ممکن است بعداً لازم شود.
    """
    enrollment.status = status
    if note:
        enrollment.note = note
    enrollment.save(update_fields=["status", "note", "updated_at"])

    logger.info(
        "دسترسی بسته شد. کاربر=%s دوره=%s وضعیت=%s",
        enrollment.user.masked_mobile,
        enrollment.course.slug,
        status,
    )


def enrolled_courses(user):
    """دوره‌هایی که کاربر در آن‌ها ثبت‌نام فعال دارد، از تازه‌ترین."""
    if not user.is_authenticated:
        return Enrollment.objects.none()

    return (
        Enrollment.objects.filter(user=user, status=EnrollmentStatus.ACTIVE)
        .select_related("course", "course__category", "course__instructor")
        .order_by("-created_at")
    )
