"""
تصمیم‌گیری درباره اینکه چه کسی اجازه دیدن محتوای یک دوره را دارد.

چرا این منطق در یک فایل جدا و نه داخل Viewها؟
چون همین یک تصمیم در چند جای مختلف لازم می‌شود: صفحه درس، تحویل فایل ویدیو،
دانلود جزوه، ورود به کلاس آنلاین و بعداً صفحه آزمون. اگر این شرط را در هر جا
دوباره بنویسیم، روزی یکی از آن‌ها یادمان می‌رود و همان یک نقطه، در پولی‌بودن
کل دوره‌ها رخنه می‌اندازد. با یک تابع مرکزی، اصلاح در یک جا همه‌جا اعمال
می‌شود.

سه تابع بیرونی دارد و هر سه به یک جا می‌رسند:

    check_course_access   ← قاعده اصلی: این شخص به این دوره دسترسی دارد؟
    check_lesson_access   ← همان، به‌علاوه شرط‌های خاص درس (انتشار، پیش‌نمایش)
    check_session_access  ← همان، به‌علاوه شرط‌های خاص کلاس آنلاین (لغو، زمان)
"""

from __future__ import annotations

from dataclasses import dataclass

from django.urls import reverse

from .models import Enrollment


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

    return check_course_access(
        user,
        course,
        purpose="دسترسی به این درس",
        next_url=lesson.get_absolute_url(),
    )


def check_course_access(
    user,
    course,
    *,
    purpose: str = "دسترسی به این درس",
    next_url: str = "",
) -> LessonAccess:
    """
    آیا این کاربر به محتوای این دوره دسترسی دارد؟

    این همان تصمیم مرکزی پروژه است و درس، فایل و کلاس آنلاین همگی از
    همین‌جا می‌پرسند. `purpose` فقط متن پیام را طبیعی می‌کند («دسترسی به
    این درس» در برابر «ورود به کلاس آنلاین»)؛ خودِ قاعده یکی است.
    """
    if _is_course_staff(user, course):
        return LessonAccess(True, "staff")

    # --- ثبت‌نام: تنها منبع حقیقت برای دسترسی ---
    #
    # ثبت‌نام می‌تواند از خرید بیاید، از دوره رایگان، از افزودن دستی
    # پشتیبانی، یا از اشتراک ویژه. هر کدام که باشد، پاسخ از یک جا می‌آید.
    # ثبت‌نام منقضی‌شده یا تعلیق‌شده هم دسترسی نمی‌دهد.
    from .enrollment import active_enrollment

    if user.is_authenticated:
        enrollment = active_enrollment(user, course)
        if enrollment is not None:
            return LessonAccess(True, "enrolled")

        if course.vip_access and user.has_active_vip:
            return LessonAccess(True, "vip")

        # ثبت‌نامی هست ولی دیگر معتبر نیست — کاربر باید بداند چرا.
        expired = Enrollment.objects.filter(user=user, course=course).first()
        if expired is not None:
            if expired.is_expired:
                return LessonAccess(
                    False,
                    "enrollment_expired",
                    "مهلت دسترسی شما به این دوره به پایان رسیده است.",
                    "تمدید دسترسی",
                    course.get_absolute_url(),
                )
            return LessonAccess(
                False,
                "enrollment_suspended",
                "دسترسی شما به این دوره موقتاً بسته شده است. با پشتیبانی تماس بگیرید.",
                "تماس با پشتیبانی",
                reverse("core:contact"),
            )

    # دوره رایگان: کاربر واردشده با یک کلیک ثبت‌نام می‌شود.
    if course.is_free:
        if user.is_authenticated:
            return LessonAccess(
                False,
                "free_enrollment_required",
                "این دوره رایگان است؛ فقط کافی است در آن ثبت‌نام کنید.",
                "ثبت‌نام رایگان",
                course.get_absolute_url(),
            )
        login_url = reverse("accounts:login")
        return LessonAccess(
            False,
            "login_required",
            f"این دوره رایگان است؛ برای {purpose} وارد حساب خود شوید.",
            "ورود یا ثبت‌نام",
            f"{login_url}?next={next_url}" if next_url else login_url,
        )

    # برای مهمان هم همین پیام درست است، نه «وارد شوید»: ورود به سایت به
    # تنهایی این درس را باز نمی‌کند و پیام «وارد شوید» انتظار اشتباه
    # می‌سازد. سبد خرید هم برای مهمان کار می‌کند.
    return LessonAccess(
        False,
        "purchase_required",
        f"برای {purpose} باید در دوره ثبت‌نام کنید.",
        "ثبت‌نام در دوره",
        course.get_absolute_url(),
    )


def check_session_access(user, session) -> LessonAccess:
    """
    آیا این کاربر می‌تواند همین حالا وارد این کلاس آنلاین شود؟

    سه سؤال پشت سر هم پرسیده می‌شود و ترتیبشان مهم است:

    ۱. آیا جلسه اصلاً برقرار است؟ (لغو نشده و لینک دارد)
    ۲. آیا این شخص در دوره ثبت‌نام دارد؟
    ۳. آیا الان زمانش است؟

    مدیر و مدرسِ دوره از شرط زمان مستثنا هستند؛ آن‌ها باید بتوانند پیش
    از دانشجوها کلاس را باز کنند و لینک را امتحان کنند.
    """
    course = session.course

    if session.is_cancelled:
        return LessonAccess(
            False,
            "session_cancelled",
            session.cancel_reason or "این جلسه لغو شده است.",
        )

    access = check_course_access(
        user,
        course,
        purpose="ورود به کلاس آنلاین",
        next_url=course.get_absolute_url(),
    )
    if not access.allowed:
        return access

    if not session.has_link:
        return LessonAccess(
            False,
            "session_no_link",
            "لینک ورود این جلسه هنوز ثبت نشده است. کمی پیش از شروع کلاس دوباره سر بزنید.",
        )

    if access.reason == "staff":
        return LessonAccess(True, "staff")

    if session.is_finished:
        return LessonAccess(
            False,
            "session_finished",
            "این جلسه برگزار شده است.",
        )

    if not session.is_running:
        return LessonAccess(
            False,
            "session_not_started",
            "لینک ورود، کمی پیش از شروع کلاس فعال می‌شود.",
        )

    return LessonAccess(True, access.reason)
