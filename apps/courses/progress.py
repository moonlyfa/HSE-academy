"""
محاسبه و ثبت پیشرفت دانشجو.

چرا جدا از Viewها؟
همین محاسبه‌ها در چند جا لازم می‌شوند: داشبورد، صفحه «دوره‌های من»، صفحه
دوره و صفحه درس. اگر فرمول درصد پیشرفت در چهار قالب مختلف تکرار شود، روزی
یکی از آن‌ها با بقیه فرق می‌کند و کاربر در دو صفحه دو عدد متفاوت می‌بیند.
"""

from __future__ import annotations

from dataclasses import dataclass

from django.db.models import Max, Sum
from django.utils import timezone

from .models import Course, Lesson, LessonProgress

# ترتیب طبیعی درس‌های یک دوره: اول بر اساس فصل، بعد بر اساس خود درس.
LESSON_ORDER = ("section__order", "section__id", "order", "id")


def visible_lessons(course: Course):
    """درس‌هایی که در سایت دیده می‌شوند — مبنای همه محاسبه‌های پیشرفت."""
    return (
        Lesson.objects.filter(
            section__course=course, section__is_published=True, is_published=True
        )
        .select_related("section")
        .order_by(*LESSON_ORDER)
    )


@dataclass
class CourseProgress:
    """خلاصه وضعیت یک کاربر در یک دوره."""

    course: Course
    total: int
    completed: int
    last_lesson: Lesson | None = None
    next_lesson: Lesson | None = None

    @property
    def percent(self) -> int:
        """
        درصد پیشرفت، گرد شده به عدد صحیح.

        دوره‌ای که هنوز درسی ندارد صفر درصد است، نه خطای تقسیم بر صفر.
        """
        if not self.total:
            return 0
        return round(self.completed * 100 / self.total)

    @property
    def is_finished(self) -> bool:
        return bool(self.total) and self.completed >= self.total

    @property
    def is_started(self) -> bool:
        return self.completed > 0 or self.last_lesson is not None

    @property
    def remaining(self) -> int:
        return max(self.total - self.completed, 0)

    @property
    def resume_lesson(self) -> Lesson | None:
        """
        درسی که دکمه «ادامه یادگیری» باید به آن برود.

        منطقش این است: اگر درس ناتمامی هست، همان؛ وگرنه آخرین درسی که
        کاربر باز کرده؛ و اگر هیچ‌کدام، از اولین درس دوره شروع می‌کنیم.
        """
        return self.next_lesson or self.last_lesson


def course_progress(user, course: Course) -> CourseProgress:
    """وضعیت کاربر در یک دوره."""
    lessons = list(visible_lessons(course))
    total = len(lessons)

    if not user.is_authenticated or not total:
        return CourseProgress(
            course=course,
            total=total,
            completed=0,
            next_lesson=lessons[0] if lessons else None,
        )

    records = {
        record.lesson_id: record
        for record in LessonProgress.objects.filter(
            user=user, lesson__in=lessons
        )
    }

    completed_ids = {pk for pk, record in records.items() if record.is_completed}

    # آخرین درسی که کاربر باز کرده است
    last_lesson = None
    if records:
        latest = max(records.values(), key=lambda record: record.last_viewed_at)
        last_lesson = next((l for l in lessons if l.pk == latest.lesson_id), None)

    # اولین درسی که هنوز تکمیل نشده — همان جایی که باید ادامه بدهد
    next_lesson = next((l for l in lessons if l.pk not in completed_ids), None)

    return CourseProgress(
        course=course,
        total=total,
        completed=len(completed_ids),
        last_lesson=last_lesson,
        next_lesson=next_lesson,
    )


def record_view(user, lesson: Lesson) -> LessonProgress | None:
    """
    ثبت اینکه کاربر این درس را باز کرده است.

    برای مهمان چیزی ثبت نمی‌شود؛ پیشرفت فقط برای کاربرِ وارد شده معنا دارد.
    """
    if not user.is_authenticated:
        return None

    progress, created = LessonProgress.objects.get_or_create(user=user, lesson=lesson)
    if not created:
        # فقط زمان آخرین بازدید بروز می‌شود؛ auto_now خودش این کار را می‌کند.
        progress.save(update_fields=["last_viewed_at"])
    return progress


def set_completed(user, lesson: Lesson, completed: bool) -> LessonProgress:
    """
    علامت‌گذاری درس به‌عنوان تکمیل‌شده یا برگرداندن آن.

    زمان تکمیل را نگه می‌داریم چون بعداً برای صدور گواهی لازم می‌شود:
    باید بشود گفت دانشجو دقیقاً چه زمانی دوره را تمام کرده است.
    """
    progress, _ = LessonProgress.objects.get_or_create(user=user, lesson=lesson)

    progress.is_completed = completed
    progress.completed_at = timezone.now() if completed else None
    progress.save(update_fields=["is_completed", "completed_at", "last_viewed_at"])
    return progress


def save_position(user, lesson: Lesson, seconds: int) -> LessonProgress | None:
    """ذخیره ثانیه‌ای که کاربر ویدیو را در آن رها کرده است."""
    if not user.is_authenticated:
        return None

    progress, _ = LessonProgress.objects.get_or_create(user=user, lesson=lesson)
    progress.last_position_seconds = max(0, int(seconds))
    progress.save(update_fields=["last_position_seconds", "last_viewed_at"])
    return progress


def learner_courses(user) -> list[CourseProgress]:
    """
    دوره‌هایی که کاربر شروع کرده است، از تازه‌ترین به قدیمی‌ترین.

    امروز «دوره من» یعنی دوره‌ای که کاربر حداقل یک درسش را باز کرده باشد.
    در فاز ۱۴ که ثبت‌نام ساخته شود، دوره‌های خریداری‌شده هم — حتی اگر هنوز
    باز نشده باشند — از همین‌جا به فهرست اضافه می‌شوند.
    """
    if not user.is_authenticated:
        return []

    course_ids = (
        LessonProgress.objects.filter(user=user)
        .values("lesson__section__course")
        .annotate(last_seen=Max("last_viewed_at"))
        .order_by("-last_seen")
    )

    ordered_ids = [row["lesson__section__course"] for row in course_ids]
    if not ordered_ids:
        return []

    # دوره‌ای که ادمین از انتشار خارج کرده نباید در فهرست کاربر بماند؛
    # وگرنه کاربر روی دوره‌ای کلیک می‌کند که صفحه‌اش ۴۰۴ می‌دهد.
    courses = {
        course.pk: course
        for course in Course.objects.filter(
            pk__in=ordered_ids, is_published=True
        ).select_related("category", "instructor")
    }

    return [
        course_progress(user, courses[pk]) for pk in ordered_ids if pk in courses
    ]


def learner_stats(user) -> dict:
    """اعداد بالای داشبورد."""
    if not user.is_authenticated:
        return {"courses": 0, "completed_lessons": 0, "minutes": 0, "finished_courses": 0}

    completed = LessonProgress.objects.filter(user=user, is_completed=True)

    minutes = completed.aggregate(total=Sum("lesson__duration_minutes"))["total"] or 0

    progresses = learner_courses(user)

    return {
        "courses": len(progresses),
        "completed_lessons": completed.count(),
        "minutes": minutes,
        "finished_courses": sum(1 for p in progresses if p.is_finished),
    }

