"""
ظرفیت دوره: چه کسانی صندلی دارند و آیا جای خالی مانده است؟

کلاس حضوری تعداد صندلی محدود دارد؛ فروختن صندلی سی‌ویکم یعنی دانشجویی که
پول داده و جایی در کلاس ندارد. پس «ظرفیت» فقط یک عدد نمایشی نیست.

**چه کسی صندلی دارد؟**

۱. هر ثبت‌نام فعال.
۲. کسی که **همین حالا در حال پرداخت** است: از لحظه‌ای که به درگاه فرستاده
   می‌شود تا پایان مهلت پرداخت (PAYMENT_EXPIRY_MINUTES)، صندلی برایش نگه
   داشته می‌شود. بدون این، دو نفر می‌توانستند هم‌زمان برای آخرین صندلی
   پرداخت کنند و هر دو موفق شوند.
۳. کسی که پرداختش **نامعلوم** مانده (پاسخ تأیید درگاه گم شده). شاید پولش
   کسر شده باشد؛ صندلی‌اش تا روشن شدن وضعیت آزاد نمی‌شود، حتی بعد از مهلت.

**چه چیزی هرگز رد نمی‌شود؟** پرداختی که درگاه تأییدش کرده است. پول گرفته
شده و ثبت‌نام باید انجام شود؛ اگر کلاس به هر دلیلی بیش از ظرفیت شد (مثلاً
مدیر دستی ثبت‌نام اضافه کرده)، فقط در لاگ هشدار ثبت می‌شود.

ثبت‌نام دستی مدیر در پنل هم عمداً کنترل نمی‌شود؛ مدیر گاهی آگاهانه یک
صندلی اضافه می‌گذارد.
"""

from __future__ import annotations

import logging
from datetime import timedelta

from django.conf import settings
from django.db.models import Q
from django.utils import timezone

from .models import Course, Enrollment, EnrollmentStatus

logger = logging.getLogger("hse.capacity")


def seat_holder_ids(course: Course) -> set[int]:
    """شناسه کاربرانی که همین حالا در این دوره صندلی دارند."""
    from apps.orders.models import OrderStatus, Payment, PaymentStatus

    enrolled = Enrollment.objects.filter(
        course=course, status=EnrollmentStatus.ACTIVE
    ).values_list("user_id", flat=True)

    hold_from = timezone.now() - timedelta(minutes=settings.PAYMENT_EXPIRY_MINUTES)
    paying = (
        Payment.objects.filter(status=PaymentStatus.PENDING, order__items__course=course)
        .exclude(order__status__in=[OrderStatus.CANCELED, OrderStatus.REFUNDED])
        .filter(Q(created_at__gte=hold_from) | Q(raw_response__has_key="verify_attempts"))
        .values_list("order__user_id", flat=True)
    )

    return set(enrolled) | set(paying)


def seats_taken(course: Course) -> int:
    return len(seat_holder_ids(course))


def seats_left(course: Course) -> int | None:
    """تعداد صندلی خالی. None یعنی دوره ظرفیت محدود ندارد."""
    if course.capacity is None:
        return None
    return max(course.capacity - seats_taken(course), 0)


def has_seat(course: Course, user) -> bool:
    """
    آیا این کاربر می‌تواند در این دوره جا داشته باشد؟

    کسی که خودش صندلی دارد (ثبت‌نام‌شده، یا پرداختش در جریان است) همیشه
    بله می‌گیرد؛ وگرنه کاربری که پرداختش ناموفق شد و دوباره تلاش می‌کند،
    با صندلیِ خودش رقابت می‌کرد و پشت در می‌ماند.
    """
    if course.capacity is None:
        return True

    holders = seat_holder_ids(course)
    if user is not None and user.is_authenticated and user.pk in holders:
        return True
    return len(holders) < course.capacity


def full_courses(courses, user) -> list[Course]:
    """از میان این دوره‌ها، کدام‌ها برای این کاربر جای خالی ندارند؟"""
    return [course for course in courses if not has_seat(course, user)]


def lock_and_find_full(course_ids, user) -> list[Course]:
    """
    دوره‌ها را قفل می‌کند و پرشده‌ها را برمی‌گرداند.

    باید داخل transaction صدا زده شود، و صندلی (ثبت‌نام یا تراکنش پرداخت)
    در **همان** transaction ساخته شود. قفل ردیف دوره باعث می‌شود دو
    درخواست هم‌زمان برای آخرین صندلی پشت هم اجرا شوند، نه با هم؛ دومی
    صندلیِ ساخته‌شده توسط اولی را می‌بیند.
    """
    courses = list(
        Course.objects.select_for_update()
        .filter(pk__in=list(course_ids), capacity__isnull=False)
        .order_by("pk")
    )
    return full_courses(courses, user)


def full_message(courses) -> str:
    titles = "، ".join(f"«{course.title}»" for course in courses)
    return f"ظرفیت دوره {titles} تکمیل شده است."


def warn_if_over_capacity(course: Course) -> None:
    """بعد از ثبت‌نامی که نباید رد می‌شد (پرداخت تأییدشده)، اگر کلاس پر شد."""
    if course.capacity is None:
        return
    taken = seats_taken(course)
    if taken > course.capacity:
        logger.warning(
            "دوره بیش از ظرفیت ثبت‌نام دارد. دوره=%s ظرفیت=%s ثبت‌نام=%s",
            course.slug,
            course.capacity,
            taken,
        )
