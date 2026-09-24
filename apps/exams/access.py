"""
چه کسی اجازه شرکت در آزمون را دارد؟

پایه تصمیم همان `check_course_access` بخش دوره‌هاست — یعنی همان ثبت‌نامی
که درس، کلاس آنلاین یا کلاس حضوری را باز می‌کند، آزمون را هم باز می‌کند. اینجا فقط
شرط‌های خاص آزمون به آن اضافه می‌شود: آزمون منتشر شده باشد، سؤال داشته
باشد، سقف دفعات پر نشده باشد و — اگر مدرس خواسته — دوره تمام شده باشد.
"""

from __future__ import annotations

from django.urls import reverse

from apps.courses.access import LessonAccess, check_course_access
from apps.courses.progress import course_progress

from .models import AttemptStatus, ExamAttempt


def _is_exam_staff(user, exam) -> bool:
    """مدیر سایت و مدرس همان دوره، آزمون منتشرنشده را هم می‌بینند."""
    if not user.is_authenticated:
        return False
    if user.is_staff:
        return True

    instructor = exam.course.instructor
    return bool(instructor and instructor.user_id == user.pk)


def used_attempts(user, exam) -> int:
    """چند بار در این آزمون شرکت کرده است؟ (تلاش نیمه‌کاره هم حساب می‌شود)"""
    if not user.is_authenticated:
        return 0
    return ExamAttempt.objects.filter(user=user, exam=exam).count()


def attempts_left(user, exam) -> int | None:
    """چند بار دیگر می‌تواند شرکت کند؟ None یعنی بی‌نهایت."""
    if not exam.max_attempts:
        return None
    return max(exam.max_attempts - used_attempts(user, exam), 0)


def open_attempt(user, exam) -> ExamAttempt | None:
    """تلاش نیمه‌کاره‌ای که باید ادامه داده شود."""
    if not user.is_authenticated:
        return None
    return (
        ExamAttempt.objects.filter(
            user=user, exam=exam, status=AttemptStatus.IN_PROGRESS
        )
        .order_by("-started_at")
        .first()
    )


def check_exam_access(user, exam) -> LessonAccess:
    """
    آیا این کاربر می‌تواند صفحه آزمون را ببیند؟

    جواب «نه» همیشه با دلیل و دکمه بعدی همراه است؛ دانشجویی که پشت در
    آزمون می‌ماند باید بداند چه کاری باید بکند.
    """
    course = exam.course
    staff = _is_exam_staff(user, exam)

    if not exam.is_published and not staff:
        return LessonAccess(False, "exam_unpublished", "آزمون این دوره هنوز فعال نشده است.")

    access = check_course_access(
        user,
        course,
        purpose="شرکت در آزمون",
        next_url=exam.get_absolute_url(),
    )
    if not access.allowed:
        return access

    return LessonAccess(True, "staff" if staff else access.reason)


def check_can_start(user, exam) -> LessonAccess:
    """
    آیا همین حالا می‌تواند آزمون **تازه‌ای** شروع کند؟

    جدا از `check_exam_access` است چون دانشجویی که سقف دفعاتش پر شده،
    باید همچنان کارنامه‌هایش را ببیند — فقط دکمه «شروع» ندارد.
    """
    access = check_exam_access(user, exam)
    if not access.allowed:
        return access

    if not exam.is_ready:
        return LessonAccess(
            False, "exam_empty", "هنوز سؤالی برای این آزمون ثبت نشده است."
        )

    if exam.require_course_completion:
        progress = course_progress(user, exam.course)
        if not progress.is_finished and exam.course.is_in_person:
            return LessonAccess(
                False,
                "course_not_completed",
                "آزمون این دوره پس از برگزاری کلاس حضوری و تأیید گذراندن دوره "
                "توسط آکادمی باز می‌شود.",
            )
        if not progress.is_finished:
            return LessonAccess(
                False,
                "course_not_completed",
                "برای شرکت در آزمون، باید همه درس‌های دوره را تکمیل کنید.",
                "ادامه دوره",
                exam.course.get_absolute_url(),
            )

    remaining = attempts_left(user, exam)
    if remaining is not None and remaining <= 0:
        return LessonAccess(
            False,
            "attempts_exhausted",
            "شما از همه دفعات مجاز شرکت در این آزمون استفاده کرده‌اید.",
            "تماس با پشتیبانی",
            reverse("core:contact"),
        )

    return LessonAccess(True, access.reason)
