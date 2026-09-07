"""
تصمیم‌گیری درباره اینکه چه کسی اجازه دیدن یک درس را دارد.

چرا این منطق در یک فایل جدا و نه داخل Viewها؟
چون همین یک تصمیم در چند جای مختلف لازم می‌شود: صفحه درس، تحویل فایل ویدیو،
دانلود جزوه و بعداً صفحه آزمون. اگر این شرط را در هر جا دوباره بنویسیم، روزی
یکی از آن‌ها یادمان می‌رود و همان یک نقطه، در پولی‌بودن کل دوره‌ها رخنه
می‌اندازد. با یک تابع مرکزی، اصلاح در یک جا همه‌جا اعمال می‌شود.

در فاز ۱۴ (ثبت‌نام و دسترسی) شرط «کاربر این دوره را خریده است» دقیقاً در
همین تابع اضافه می‌شود و هیچ جای دیگری از پروژه لازم نیست عوض شود.
"""

from __future__ import annotations

from dataclasses import dataclass

from django.urls import reverse


@dataclass(frozen=True)
class LessonAccess:
    """
    نتیجه بررسی دسترسی.

    فقط True/False برنمی‌گردانیم چون صفحه باید بتواند به کاربر بگوید
    «چرا» بسته است: باید وارد شود؟ باید بخرد؟ درس هنوز منتشر نشده؟
    """

    allowed: bool
    reason: str
    message: str = ""
    action_label: str = ""
    action_url: str = ""

    def __bool__(self) -> bool:
        return self.allowed


def _is_course_staff(user, course) -> bool:
    """مدیر سایت و مدرسِ خودِ دوره همیشه به محتوا دسترسی دارند."""
    if not user.is_authenticated:
        return False
    if user.is_staff:
        return True

    instructor = course.instructor
    return bool(instructor and instructor.user_id == user.pk)


def check_lesson_access(user, lesson) -> LessonAccess:
    """آیا این کاربر می‌تواند محتوای این درس را ببیند؟"""
    course = lesson.section.course
    staff = _is_course_staff(user, course)

    # درس منتشرنشده فقط برای مدیر و مدرس دوره قابل دیدن است تا بتوانند
    # پیش از انتشار، محتوا را بازبینی کنند.
    if not lesson.is_visible:
        if staff:
            return LessonAccess(True, "staff_preview", "این درس هنوز منتشر نشده است.")
        return LessonAccess(False, "unpublished", "این درس هنوز منتشر نشده است.")

    if lesson.is_free_preview:
        return LessonAccess(True, "free_preview")

    if staff:
        return LessonAccess(True, "staff")

    # دوره رایگان: فقط لازم است کاربر حساب داشته باشد تا بدانیم چه کسی
    # دوره را می‌گذراند. در فاز ۱۴ همین‌جا رکورد ثبت‌نام هم ساخته می‌شود.
    if course.is_free:
        if user.is_authenticated:
            return LessonAccess(True, "free_course")
        return LessonAccess(
            False,
            "login_required",
            "این دوره رایگان است؛ برای مشاهده درس‌ها فقط کافی است وارد حساب خود شوید.",
            "ورود یا ثبت‌نام",
            f"{reverse('accounts:login')}?next={lesson.get_absolute_url()}",
        )

    # کاربری که دوره را خریده است.
    #
    # «خریده» یعنی این دوره در یک سفارش با وضعیت «پرداخت شده» وجود دارد،
    # و آن وضعیت فقط بعد از تأیید سرور به سرورِ درگاه ثبت می‌شود. یعنی
    # کسی که فقط سفارش ثبت کرده — یا از آدرس بازگشتی درگاه دستکاری‌شده
    # برگشته — از این در رد نمی‌شود.
    #
    # در فاز ۱۴ این بررسی به مدل Enrollment منتقل می‌شود تا بشود مدت
    # دسترسی و تاریخ انقضا را هم مدیریت کرد. تا آن موقع، سفارش پرداخت‌شده
    # همان نقش را بازی می‌کند.
    if user.is_authenticated and _has_paid_for(user, course):
        return LessonAccess(True, "purchased")

    # برای مهمان هم همین پیام درست است، نه «وارد شوید»: ورود به سایت به
    # تنهایی این درس را باز نمی‌کند و پیام «وارد شوید» انتظار اشتباه
    # می‌سازد. سبد خرید هم برای مهمان کار می‌کند.
    return LessonAccess(
        False,
        "purchase_required",
        "برای دسترسی به این درس باید در دوره ثبت‌نام کنید.",
        "ثبت‌نام در دوره",
        course.get_absolute_url(),
    )


def _has_paid_for(user, course) -> bool:
    """آیا این دوره در سفارشی پرداخت‌شده از این کاربر هست؟"""
    # اینجا وارد می‌شود نه در بالای فایل: اپ سفارش‌ها به اپ دوره‌ها وابسته
    # است و وارد کردن دوطرفه در بالای فایل، حلقه import می‌سازد.
    from apps.orders.models import OrderStatus

    return course.order_items.filter(
        order__user=user, order__status=OrderStatus.PAID
    ).exists()
