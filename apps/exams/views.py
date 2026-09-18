"""
Viewهای آزمون.

چهار صفحه دارد و هر کدام یک کار می‌کند:

    exam_detail   ← قوانین آزمون و دکمه شروع
    attempt_take  ← برگه امتحان (نمایش سؤال‌ها و ثبت نهایی)
    attempt_result← کارنامه
    my_exams      ← فهرست آزمون‌های کاربر در داشبورد

قاعده مشترک همه: مهلت آزمون در سرور بررسی می‌شود، نه در مرورگر. زمان‌سنجِ
صفحه فقط برای راحتی دانشجوست؛ اگر کسی آن را دستکاری کند یا جاوااسکریپت را
خاموش کند، باز هم پاسخ بعد از مهلت پذیرفته نمی‌شود.
"""

from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from apps.courses.models import Course

from .access import attempts_left, check_can_start, check_exam_access, open_attempt
from .grading import (
    attempt_sheet,
    best_attempt,
    close_if_expired,
    finish_attempt,
    options_for,
    save_answer,
    start_attempt,
    user_attempts,
)
from .models import Exam, ExamAttempt


def _exam_or_404(slug: str) -> Exam:
    course = get_object_or_404(Course.objects.published(), slug=slug)
    exam = Exam.objects.filter(course=course).select_related("course").first()
    if exam is None:
        raise Http404("این دوره آزمون ندارد.")
    return exam


def _sheet_rows(attempt, exam) -> list[dict]:
    """
    برگه امتحان، آماده نمایش.

    گزینه‌ها همین‌جا مرتب می‌شوند تا قالب هیچ منطقی نداشته باشد.
    """
    return [
        {
            "answer": answer,
            "question": answer.question,
            "options": options_for(answer, exam.shuffle_options),
            "number": index + 1,
        }
        for index, answer in enumerate(attempt_sheet(attempt))
    ]


def exam_detail(request: HttpRequest, slug: str) -> HttpResponse:
    """صفحه معرفی آزمون: قوانین، دفعات باقی‌مانده و کارنامه‌های قبلی."""
    exam = _exam_or_404(slug)
    access = check_exam_access(request.user, exam)

    if not access.allowed and access.reason == "exam_unpublished":
        raise Http404("آزمون این دوره هنوز فعال نشده است.")

    running = open_attempt(request.user, exam)
    if running is not None:
        close_if_expired(running)
        running = open_attempt(request.user, exam)

    return render(
        request,
        "exams/exam_detail.html",
        {
            "exam": exam,
            "course": exam.course,
            "access": access,
            "can_start": check_can_start(request.user, exam),
            "attempts_left": attempts_left(request.user, exam),
            "attempts": user_attempts(request.user, exam),
            "best": best_attempt(request.user, exam),
            "running_attempt": running,
            "breadcrumb_items": [
                {"label": "دوره‌ها", "url": reverse("courses:list")},
                {"label": exam.course.title, "url": exam.course.get_absolute_url()},
            ],
            "nav_active": "courses",
        },
    )


@login_required
@require_POST
def attempt_start(request: HttpRequest, slug: str) -> HttpResponse:
    """
    شروع آزمون.

    چرا فقط POST؟ چون شروع آزمون یعنی سوختن یکی از دفعات مجاز و راه
    افتادن زمان‌سنج. اگر با GET کار می‌کرد، یک لینک اشتباهی یا حتی
    پیش‌بارگذاری مرورگر می‌توانست آزمون کسی را شروع کند.
    """
    exam = _exam_or_404(slug)

    # اگر تلاش نیمه‌کاره‌ای هست، تلاش تازه ساخته نمی‌شود؛ همان ادامه پیدا
    # می‌کند. وگرنه با هر بار زدن دکمه، یکی از دفعات مجاز می‌سوخت.
    running = open_attempt(request.user, exam)
    if running is not None and not close_if_expired(running):
        return redirect("exams:take", pk=running.pk)

    allowed = check_can_start(request.user, exam)
    if not allowed.allowed:
        messages.error(request, allowed.message or "امکان شرکت در این آزمون نیست.")
        return redirect(exam.get_absolute_url())

    attempt = start_attempt(request.user, exam)
    return redirect("exams:take", pk=attempt.pk)


def _attempt_or_404(request: HttpRequest, pk: int):
    """
    تلاش را فقط برای صاحب همان تلاش برمی‌گرداند.

    ۴۰۴ می‌دهیم نه ۴۰۳: کاربر نباید بفهمد تلاشی با این شناسه اصلاً وجود
    دارد یا نه.
    """
    return get_object_or_404(
        ExamAttempt.objects.select_related("exam", "exam__course", "user"),
        pk=pk,
        user=request.user,
    )


@login_required
def attempt_take(request: HttpRequest, pk: int) -> HttpResponse:
    """
    برگه امتحان.

    GET سؤال‌ها را نشان می‌دهد، POST همه پاسخ‌ها را ذخیره و آزمون را
    تصحیح می‌کند. بدون جاوااسکریپت هم کامل کار می‌کند؛ زمان‌سنج و ذخیره
    خودکار فقط راحتی اضافه می‌کنند.
    """
    attempt = _attempt_or_404(request, pk)

    if attempt.is_finished:
        return redirect(attempt.get_absolute_url())

    # ورود به صفحه‌ای که مهلتش تمام شده = تصحیح خودکار همان لحظه.
    if close_if_expired(attempt):
        messages.warning(request, "مهلت آزمون به پایان رسید و پاسخ‌های ثبت‌شده تصحیح شد.")
        return redirect(attempt.get_absolute_url())

    exam = attempt.exam

    if request.method == "POST":
        accepted = attempt.accepts_answers

        if accepted:
            for answer in attempt_sheet(attempt):
                save_answer(attempt, answer, request.POST.get(f"question_{answer.pk}"))
        else:
            messages.warning(
                request, "مهلت آزمون تمام شده بود؛ فقط پاسخ‌های ذخیره‌شده تصحیح شدند."
            )

        finish_attempt(attempt, auto=not accepted)
        return redirect(attempt.get_absolute_url())

    return render(
        request,
        "exams/attempt.html",
        {
            "attempt": attempt,
            "exam": exam,
            "course": exam.course,
            "rows": _sheet_rows(attempt, exam),
            "remaining_seconds": attempt.remaining_seconds,
        },
    )


@login_required
@require_POST
def attempt_answer(request: HttpRequest, pk: int) -> JsonResponse:
    """
    ذخیره یک پاسخ، همان لحظه‌ای که دانشجو گزینه را می‌زند.

    این تنها بخش وابسته به جاوااسکریپت است و عمداً اختیاری است: اگر کار
    نکند، پاسخ‌ها موقع «ثبت نهایی» ذخیره می‌شوند. فایده‌اش وقتی معلوم
    می‌شود که مرورگر بسته شود یا مهلت تمام شود — آن‌وقت هرچه انتخاب شده
    بود، ثبت شده است.
    """
    attempt = _attempt_or_404(request, pk)

    if attempt.is_finished or not attempt.accepts_answers:
        return JsonResponse({"ok": False, "error": "مهلت آزمون تمام شده است."}, status=400)

    answer = attempt.answers.filter(pk=request.POST.get("answer")).first()
    if answer is None:
        return JsonResponse({"ok": False, "error": "سؤال نامعتبر"}, status=400)

    if not save_answer(attempt, answer, request.POST.get("option")):
        return JsonResponse({"ok": False, "error": "گزینه نامعتبر"}, status=400)

    return JsonResponse({"ok": True, "answered": attempt.answered_count})


@login_required
def attempt_result(request: HttpRequest, pk: int) -> HttpResponse:
    """کارنامه یک تلاش."""
    attempt = _attempt_or_404(request, pk)

    if not attempt.is_finished:
        close_if_expired(attempt)

    if not attempt.is_finished:
        return redirect("exams:take", pk=attempt.pk)

    exam = attempt.exam
    review = _sheet_rows(attempt, exam) if exam.show_correct_answers else []

    return render(
        request,
        "exams/result.html",
        {
            "attempt": attempt,
            "exam": exam,
            "course": exam.course,
            "review": review,
            "attempts_left": attempts_left(request.user, exam),
            "can_start": check_can_start(request.user, exam),
        },
    )


@login_required
def my_exams(request: HttpRequest) -> HttpResponse:
    """فهرست آزمون‌های کاربر در داشبورد."""
    attempts = user_attempts(request.user)

    return render(
        request,
        "exams/my_exams.html",
        {
            "attempts": attempts,
            "passed_count": attempts.filter(is_passed=True).count(),
        },
    )
