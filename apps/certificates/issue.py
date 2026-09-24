"""
شرایط و صدور گواهی.

«چه کسی گواهی می‌گیرد» یک تصمیم کسب‌وکاری است، نه یک جزئیات نمایشی؛ پس
مثل دسترسی دوره، در یک تابع مرکزی جمع شده تا صفحه دوره، داشبورد، صفحه
کارنامه و پنل مدیریت همگی یک جواب بدهند.

شرط‌ها به همین ترتیب بررسی می‌شوند و هر «نه» دلیل و قدم بعدی خودش را
همراه دارد؛ دانشجویی که گواهی نگرفته باید بداند دقیقاً چه چیزی کم است.
"""

from __future__ import annotations

import logging

from django.db import IntegrityError, transaction
from django.urls import reverse
from django.utils import timezone

from apps.courses.access import LessonAccess, check_course_access
from apps.courses.enrollment import active_enrollment
from apps.courses.progress import course_progress

from .models import (
    CERTIFICATE_CODE_PREFIX,
    Certificate,
    CertificateStatus,
    build_certificate_code,
)

logger = logging.getLogger("hse.certificate")

# اگر ساخت کد یکتا با تداخل روبه‌رو شد (دو صدور هم‌زمان)، چند بار دوباره
# تلاش می‌شود. بیشتر از این یعنی مشکل جای دیگری است.
CODE_RETRY_LIMIT = 5


def existing_certificate(user, course) -> Certificate | None:
    """گواهی قبلی همین دانشجو در همین دوره."""
    if not user.is_authenticated:
        return None
    return Certificate.objects.filter(user=user, course=course).first()


def check_eligibility(user, course) -> LessonAccess:
    """
    آیا این دانشجو شرایط دریافت گواهی این دوره را دارد؟

    ترتیب بررسی از «دورترین» شرط به «نزدیک‌ترین» است تا پیام، همان قدم
    بعدیِ واقعی کاربر باشد: اول ثبت‌نام، بعد احراز هویت، بعد گذراندن
    دوره و آخر قبولی در آزمون.
    """
    if not course.certificate_available:
        return LessonAccess(
            False, "certificate_not_offered", "این دوره گواهی پایان دوره ندارد."
        )

    access = check_course_access(
        user,
        course,
        purpose="دریافت گواهی",
        next_url=course.get_absolute_url(),
    )
    if not access.allowed:
        return access

    # مدیر و مدرس دوره هم برای خودشان گواهی نمی‌گیرند؛ گواهی مدرک
    # گذراندن دوره است، نه نشانه دسترسی.
    if active_enrollment(user, course) is None:
        return LessonAccess(
            False,
            "enrollment_required",
            "گواهی فقط برای دانشجوی ثبت‌نام‌شده در دوره صادر می‌شود.",
        )

    if not user.full_name:
        return LessonAccess(
            False,
            "name_missing",
            "نام و نام خانوادگی شما ثبت نشده است؛ این نام روی گواهی چاپ می‌شود.",
            "تکمیل پروفایل",
            reverse("accounts:profile"),
        )

    if not user.is_mobile_verified:
        return LessonAccess(
            False,
            "mobile_unverified",
            "برای صدور گواهی، تأیید شماره موبایل لازم است.",
            "تأیید شماره موبایل",
            reverse("accounts:verify_mobile"),
        )

    if not user.is_identity_verified:
        return LessonAccess(
            False,
            "identity_unverified",
            "گواهی فقط به نام فردی صادر می‌شود که هویتش تأیید شده باشد.",
            "احراز هویت",
            reverse("accounts:verify_identity"),
        )

    progress = course_progress(user, course)
    if not progress.is_finished:
        if course.is_in_person:
            return LessonAccess(
                False,
                "course_not_completed",
                "گواهی پس از برگزاری کلاس حضوری و تأیید گذراندن دوره توسط "
                "آکادمی صادر می‌شود. این تأیید هنوز ثبت نشده است.",
            )
        return LessonAccess(
            False,
            "course_not_completed",
            f"برای دریافت گواهی باید همه درس‌ها را تکمیل کنید "
            f"(تا اینجا {progress.percent}٪).",
            "ادامه دوره",
            course.get_absolute_url(),
        )

    exam_check = _exam_requirement(user, course)
    if exam_check is not None:
        return exam_check

    return LessonAccess(True, "eligible")


def _exam_requirement(user, course) -> LessonAccess | None:
    """
    اگر دوره آزمون فعال دارد، قبولی در آن شرط گواهی است.

    apps.certificates به apps.exams وابسته است و نه برعکس؛ این وارد کردن
    داخل تابع فقط برای کوتاه نگه داشتن زنجیره وارد کردن ماژول‌هاست.
    """
    from apps.exams.grading import has_passed
    from apps.exams.summary import course_exam

    if not course.exam_available:
        return None

    exam = course_exam(course)
    if exam is None or not exam.is_ready:
        return None

    if has_passed(user, exam):
        return None

    return LessonAccess(
        False,
        "exam_not_passed",
        f"برای دریافت گواهی باید در آزمون پایان دوره نمره {exam.pass_score} یا بالاتر بگیرید.",
        "صفحه آزمون",
        exam.get_absolute_url(),
    )


def next_certificate_code() -> str:
    """
    کد بعدی گواهی در سال جاری شمسی.

    شماره ترتیبی در هر سال از یک شروع می‌شود (HSE-1404-00001). شمارنده از
    روی بیشترین کد همان سال ساخته می‌شود، نه از تعداد ردیف‌ها؛ چون گواهی
    باطل‌شده هم ردیفش می‌ماند و شمارش ردیف‌ها دیر یا زود کد تکراری
    می‌سازد.
    """
    from apps.core.jalali import gregorian_to_jalali

    today = timezone.localdate()
    year = gregorian_to_jalali(today.year, today.month, today.day)[0]
    prefix = f"{CERTIFICATE_CODE_PREFIX}-{year}-"

    last = (
        Certificate.objects.filter(certificate_code__startswith=prefix)
        .order_by("-certificate_code")
        .values_list("certificate_code", flat=True)
        .first()
    )

    serial = 1
    if last:
        try:
            serial = int(last.rsplit("-", 1)[1]) + 1
        except (IndexError, ValueError):  # کد دستی و خارج از قالب
            serial = Certificate.objects.filter(
                certificate_code__startswith=prefix
            ).count() + 1

    return build_certificate_code(year, serial)


@transaction.atomic
def _create_certificate(user, course) -> Certificate:
    """ساخت ردیف گواهی با اطلاعات عکس‌برداری‌شده."""
    from apps.exams.grading import best_attempt
    from apps.exams.summary import course_exam

    exam = course_exam(course) if course.exam_available else None
    attempt = best_attempt(user, exam) if exam else None

    instructor = course.instructor

    return Certificate.objects.create(
        user=user,
        course=course,
        enrollment=active_enrollment(user, course),
        exam_attempt=attempt,
        certificate_code=next_certificate_code(),
        holder_name=user.full_name,
        course_title=course.title,
        course_hours=course.duration_hours,
        instructor_name=instructor.display_name if instructor else "",
        score=attempt.score if attempt else None,
    )


def issue_certificate(user, course) -> Certificate | None:
    """
    صدور گواهی — یا برگرداندن گواهی‌ای که قبلاً صادر شده.

    دو بار زدن دکمه «دریافت گواهی» نباید دو کد گواهی بسازد؛ کد گواهی
    چیزی است که روی کاغذ چاپ و به کارفرما داده می‌شود.
    """
    existing = existing_certificate(user, course)
    if existing is not None:
        return existing

    if not check_eligibility(user, course).allowed:
        return None

    for attempt_number in range(CODE_RETRY_LIMIT):
        try:
            certificate = _create_certificate(user, course)
        except IntegrityError:
            # یا دو صدور هم‌زمان کد یکسان گرفته‌اند، یا گواهی همین لحظه
            # توسط درخواست دیگری ساخته شده است.
            existing = existing_certificate(user, course)
            if existing is not None:
                return existing
            if attempt_number == CODE_RETRY_LIMIT - 1:
                raise
            continue

        logger.info(
            "گواهی صادر شد. کد=%s کاربر=%s دوره=%s نمره=%s",
            certificate.certificate_code,
            user.masked_mobile,
            course.slug,
            certificate.score if certificate.score is not None else "بدون آزمون",
        )
        return certificate

    return None


def revoke_certificate(certificate: Certificate, reason: str = "") -> Certificate:
    """
    ابطال گواهی.

    ردیف پاک نمی‌شود: صفحه استعلام باید بتواند بگوید «این گواهی باطل شده
    است»، نه «چنین گواهی‌ای وجود ندارد».
    """
    certificate.status = CertificateStatus.REVOKED
    certificate.revoke_reason = reason
    certificate.save(update_fields=["status", "revoke_reason", "updated_at"])

    logger.info(
        "گواهی باطل شد. کد=%s علت=%s", certificate.certificate_code, reason or "—"
    )
    return certificate


def user_certificates(user):
    """گواهی‌های کاربر، از تازه‌ترین."""
    if not user.is_authenticated:
        return Certificate.objects.none()
    return Certificate.objects.filter(user=user).select_related("course")


def certificate_card(user, course) -> dict | None:
    """
    داده‌های بخش «گواهی» در صفحه دوره و کارنامه آزمون.

    None یعنی این بخش اصلاً نمایش داده نمی‌شود: یا دوره گواهی ندارد، یا
    بیننده دانشجوی ثبت‌نام‌شده نیست و نشان دادن شرط‌های گواهی به او فقط
    شلوغی است.
    """
    if not course.certificate_available or not user.is_authenticated:
        return None

    certificate = existing_certificate(user, course)
    if certificate is not None:
        return {"certificate": certificate, "eligibility": None}

    if active_enrollment(user, course) is None:
        return None

    return {"certificate": None, "eligibility": check_eligibility(user, course)}
