"""
کلاس‌های آنلاین از دید کاربر.

مدل `OnlineSession` می‌گوید یک جلسه چه زمانی برگزار می‌شود؛ این فایل
می‌گوید **این کاربر** کدام جلسه‌ها را می‌بیند و روی کدام‌یک دکمه ورود
دارد. جدا نگه داشتن این دو، همان قاعده‌ای است که برای درس‌ها هم رعایت
شده: تصمیم دسترسی در پایتون گرفته می‌شود، نه در قالب.
"""

from __future__ import annotations

from .access import check_session_access
from .enrollment import enrolled_courses
from .models import CourseType, OnlineSession, offered_courses_q, online_courses_enabled


def sessions_with_access(user, sessions) -> list[dict]:
    """هر جلسه را همراه نتیجه بررسی دسترسیِ همین کاربر برمی‌گرداند."""
    return [
        {"session": session, "access": check_session_access(user, session)}
        for session in sessions
    ]


def user_sessions(user):
    """
    همه جلسه‌های دوره‌هایی که کاربر در آن‌ها ثبت‌نام فعال دارد.

    ثبت‌نامِ فعال ملاک است، نه سفارش: کسی که دوره را هدیه گرفته یا
    پشتیبانی دستی اضافه‌اش کرده هم باید کلاس‌هایش را ببیند.
    """
    # کلاس آنلاین فقط وقتی معنا دارد که بخش آنلاین روشن باشد؛ جلسه‌های
    # ثبت‌شده در دیتابیس می‌مانند ولی به هیچ کاربری نشان داده نمی‌شوند.
    if not user.is_authenticated or not online_courses_enabled():
        return OnlineSession.objects.none()

    course_ids = enrolled_courses(user).values_list("course_id", flat=True)
    return (
        OnlineSession.objects.filter(course_id__in=course_ids)
        .filter(offered_courses_q("course__"))
        .exclude(course__course_type=CourseType.IN_PERSON)
        .select_related("course")
    )


def upcoming_session_rows(user, limit: int | None = None) -> list[dict]:
    """نزدیک‌ترین کلاس‌های پیش‌روی کاربر، آماده نمایش."""
    sessions = user_sessions(user).upcoming()
    if limit:
        sessions = sessions[:limit]
    return sessions_with_access(user, sessions)
