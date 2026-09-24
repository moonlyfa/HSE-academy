"""
خلاصه وضعیت آزمون یک دوره — برای صفحه دوره و فازهای بعدی.

چرا جدا از Viewهای آزمون؟ چون صفحه دوره متعلق به اپ `courses` است و
نباید برای ساختن یک کارت کوچک، منطق آزمون را از نو بنویسد. فاز ۱۷
(گواهی) هم از همین‌جا می‌پرسد «این دانشجو آزمون را قبول شده؟».
"""

from __future__ import annotations

from .access import check_can_start
from .grading import best_attempt, has_passed
from .models import Exam


def course_exam(course) -> Exam | None:
    """آزمون این دوره، اگر ساخته و منتشر شده باشد."""
    return Exam.objects.filter(course=course, is_published=True).first()


def exam_card(user, course) -> dict | None:
    """
    داده‌های کارت «آزمون پایان دوره» در صفحه دوره.

    None یعنی این دوره آزمون فعالی ندارد و اصلاً کارتی نمایش داده
    نمی‌شود — بهتر از نشان دادن یک کارت خالی «به‌زودی».
    """
    exam = course_exam(course)
    if exam is None:
        return None

    return {
        "exam": exam,
        "can_start": check_can_start(user, exam),
        "best": best_attempt(user, exam),
        "passed": has_passed(user, exam),
    }
