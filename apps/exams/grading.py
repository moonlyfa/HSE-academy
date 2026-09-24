"""
اجرا و تصحیح آزمون.

تمام تصمیم‌های «چه چیزی ثبت شود و چطور نمره داده شود» در همین فایل جمع
شده است تا Viewها کوتاه بمانند و همین منطق بعداً از جای دیگری هم (مثلاً
صدور گواهی در فاز ۱۷) قابل صدا زدن باشد.

مهم‌ترین قاعده: **تصحیح فقط از روی چیزی انجام می‌شود که در دیتابیس ثبت
شده.** پاسخی که بعد از پایان مهلت برسد، پذیرفته نمی‌شود.
"""

from __future__ import annotations

import logging
import random
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from .models import AttemptStatus, ExamAttempt, QuestionOption, UserAnswer

logger = logging.getLogger("hse.exam")


def pick_questions(exam) -> list:
    """
    سؤال‌های یک برگه امتحان.

    فقط سؤال‌هایی که گزینه درست دارند وارد آزمون می‌شوند؛ سؤالی که مدرس
    یادش رفته پاسخ درستش را علامت بزند، نباید نمره دانشجو را خراب کند.
    """
    questions = [q for q in exam.active_questions.prefetch_related("options") if q.is_answerable]

    if exam.shuffle_questions:
        random.shuffle(questions)

    if exam.question_count:
        questions = questions[: exam.question_count]

    return questions


@transaction.atomic
def start_attempt(user, exam) -> ExamAttempt:
    """
    شروع یک تلاش تازه.

    برگه امتحان همین‌جا ساخته و قفل می‌شود: ردیف‌های `UserAnswer` با
    ترتیب مشخص ساخته می‌شوند تا تازه‌کردن صفحه، سؤال‌ها را عوض نکند.
    """
    questions = pick_questions(exam)
    now = timezone.now()

    attempt = ExamAttempt.objects.create(
        exam=exam,
        user=user,
        started_at=now,
        expires_at=(
            now + timedelta(minutes=exam.time_limit_minutes)
            if exam.has_time_limit
            else None
        ),
        pass_score=exam.pass_score,
        total_points=sum(q.points for q in questions),
    )

    UserAnswer.objects.bulk_create(
        [
            UserAnswer(
                attempt=attempt,
                question=question,
                order=index,
                points=question.points,
            )
            for index, question in enumerate(questions)
        ]
    )

    logger.info(
        "آزمون شروع شد. دوره=%s کاربر=%s سؤال=%s",
        exam.course.slug,
        user.masked_mobile,
        len(questions),
    )
    return attempt


def attempt_sheet(attempt) -> list[UserAnswer]:
    """برگه امتحان این تلاش، به همان ترتیبی که در لحظه شروع قفل شد."""
    return list(
        attempt.answers.select_related("question", "selected_option")
        .prefetch_related("question__options")
        .order_by("order", "id")
    )


def options_for(answer: UserAnswer, shuffle: bool) -> list[QuestionOption]:
    """
    گزینه‌های یک سؤال، با ترتیب پایدار.

    ترتیب تصادفی گزینه‌ها از روی شناسه پاسخ ساخته می‌شود، نه با
    `random` خام؛ وگرنه با هر بار تازه‌کردن صفحه، جای گزینه‌ها عوض
    می‌شود و دانشجو فکر می‌کند پاسخش پاک شده است.
    """
    options = list(answer.question.options.all())
    if shuffle:
        random.Random(answer.pk).shuffle(options)
    return options


def save_answer(attempt: ExamAttempt, answer: UserAnswer, option_id) -> bool:
    """
    ثبت پاسخ یک سؤال. اگر مهلت تمام شده باشد، چیزی ذخیره نمی‌شود.

    نتیجه True یعنی ذخیره شد.
    """
    if not attempt.accepts_answers:
        return False

    if not option_id:
        answer.selected_option = None
        answer.answered_at = None
        answer.save(update_fields=["selected_option", "answered_at"])
        return True

    option = QuestionOption.objects.filter(
        pk=option_id, question_id=answer.question_id
    ).first()
    if option is None:
        # گزینه‌ای که به این سؤال تعلق ندارد — یعنی یا خطای برنامه است یا
        # دستکاری فرم. در هر دو حالت ذخیره نمی‌شود.
        return False

    answer.selected_option = option
    answer.answered_at = timezone.now()
    answer.save(update_fields=["selected_option", "answered_at"])
    return True


@transaction.atomic
def finish_attempt(attempt: ExamAttempt, *, auto: bool = False) -> ExamAttempt:
    """
    تصحیح و بستن یک تلاش.

    نمره، امتیاز و نتیجه قبولی همین‌جا در ردیف تلاش نوشته می‌شوند و بعد
    از آن، تغییرِ سؤال‌ها یا نمره قبولی آزمون دیگر کارنامه را عوض نمی‌کند.
    """
    if attempt.is_finished:
        return attempt

    answers = list(attempt.answers.select_related("selected_option"))

    earned = 0
    for answer in answers:
        correct = bool(answer.selected_option and answer.selected_option.is_correct)
        answer.is_correct = correct
        answer.earned_points = answer.points if correct else 0
        earned += answer.earned_points

    UserAnswer.objects.bulk_update(answers, ["is_correct", "earned_points"])

    total = sum(answer.points for answer in answers)

    attempt.earned_points = earned
    attempt.total_points = total
    # آزمونی که سؤال ندارد صفر درصد است، نه خطای تقسیم بر صفر.
    attempt.score = round(earned * 100 / total) if total else 0
    attempt.is_passed = attempt.score >= attempt.pass_score
    attempt.status = AttemptStatus.FINISHED
    attempt.finished_at = timezone.now()
    attempt.auto_submitted = auto
    attempt.save(
        update_fields=[
            "earned_points",
            "total_points",
            "score",
            "is_passed",
            "status",
            "finished_at",
            "auto_submitted",
        ]
    )

    logger.info(
        "آزمون تصحیح شد. دوره=%s کاربر=%s نمره=%s نتیجه=%s خودکار=%s",
        attempt.exam.course.slug,
        attempt.user.masked_mobile,
        attempt.score,
        "قبول" if attempt.is_passed else "مردود",
        auto,
    )
    return attempt


def close_if_expired(attempt: ExamAttempt) -> bool:
    """
    اگر مهلت تلاش تمام شده، همان‌جا تصحیحش می‌کند.

    چرا با ورود کاربر بسته می‌شود و نه با یک زمان‌بند؟ چون تا وقتی کسی
    سراغ تلاش نیامده، بسته‌بودن یا نبودنش هیچ فرقی نمی‌کند — و یک
    زمان‌بندِ دائماً در حال اجرا برای کاری که خودش هنگام نیاز انجام
    می‌شود، هزینه بی‌دلیل است.
    """
    if attempt.is_expired:
        finish_attempt(attempt, auto=True)
        return True
    return False


def best_attempt(user, exam) -> ExamAttempt | None:
    """بهترین کارنامه کاربر در این آزمون — ملاک گواهی در فاز ۱۷."""
    if not user.is_authenticated:
        return None
    return (
        ExamAttempt.objects.filter(
            user=user, exam=exam, status=AttemptStatus.FINISHED
        )
        .order_by("-score", "-finished_at")
        .first()
    )


def has_passed(user, exam) -> bool:
    best = best_attempt(user, exam)
    return bool(best and best.is_passed)


def user_attempts(user, exam=None):
    """کارنامه‌های کاربر، از تازه‌ترین."""
    if not user.is_authenticated:
        return ExamAttempt.objects.none()

    queryset = ExamAttempt.objects.filter(user=user).select_related(
        "exam", "exam__course"
    )
    if exam is not None:
        queryset = queryset.filter(exam=exam)
    return queryset
