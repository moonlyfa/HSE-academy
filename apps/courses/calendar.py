"""
تقویم آموزشی ماهانه — ساختن جدول یک ماه شمسی و چیدن دوره‌ها روی روزها.

هر دوره روی **روز شروعش** نشسته است. دوره‌های حضوری چندروزه را روی همه
روزهایش تکرار نمی‌کنیم: تاریخ پایان در پنل فقط بازه کلی را می‌گوید، نه
روزهای واقعی کلاس، و تکرار دوره ده‌روزه روی ده خانه تقویم را شلوغ و
گمراه‌کننده می‌کرد. بازه کامل در فهرست زیر جدول و صفحه خود دوره آمده است.

جدول از شنبه شروع می‌شود و جمعه (تعطیل) ستون آخر است؛ همان چیزی که
مخاطب ایرانی از تقویم انتظار دارد.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

from django.utils import timezone

from apps.core.jalali import (
    PERSIAN_MONTHS,
    gregorian_to_jalali,
    jalali_month_days,
    jalali_to_gregorian,
)

from .models import Course

WEEKDAY_NAMES = ["شنبه", "یکشنبه", "دوشنبه", "سه‌شنبه", "چهارشنبه", "پنجشنبه", "جمعه"]

# بازه سال‌هایی که از آدرس پذیرفته می‌شود؛ بیرون از آن، سال جاری نمایش
# داده می‌شود. فقط جلوی عددهای بی‌معنا (مثلاً ?year=99999) را می‌گیرد.
MIN_YEAR = 1390
MAX_YEAR = 1500


def saturday_index(value: date) -> int:
    """شماره ستون روز در هفته‌ای که از شنبه شروع می‌شود: شنبه ۰ … جمعه ۶."""
    # weekday() پایتون: دوشنبه ۰ … شنبه ۵، یکشنبه ۶
    return (value.weekday() + 2) % 7


@dataclass
class DayCell:
    day: int
    date: date
    is_friday: bool
    is_today: bool
    is_past: bool
    courses: list = field(default_factory=list)


@dataclass
class MonthCalendar:
    year: int
    month: int
    weeks: list  # هر هفته: لیست ۷تایی از DayCell یا None (خانه خالی)
    courses: list  # دوره‌های همین ماه، به ترتیب تاریخ
    month_counts: list  # تعداد دوره‌های هر ۱۲ ماه سال، برای دکمه‌های ماه

    @property
    def month_name(self) -> str:
        return PERSIAN_MONTHS[self.month - 1]

    @property
    def months(self) -> list[dict]:
        return [
            {"number": number, "name": name, "count": self.month_counts[number - 1]}
            for number, name in enumerate(PERSIAN_MONTHS, start=1)
        ]

    @property
    def next_busy_month(self) -> dict | None:
        """اولین ماهِ بعد از این ماه (در همین سال) که دوره دارد."""
        for month in self.months[self.month :]:
            if month["count"]:
                return month
        return None


def today_jalali() -> tuple[int, int, int]:
    today = timezone.localdate()
    return gregorian_to_jalali(today.year, today.month, today.day)


def parse_year_month(year_param, month_param) -> tuple[int, int]:
    """
    سال و ماه را از آدرس می‌خواند؛ ورودی نامعتبر به ماه جاری برمی‌گردد.

    اگر فقط سال داده شده باشد: برای سال جاری ماه جاری، برای سال‌های دیگر
    فروردین.
    """
    current_year, current_month, _ = today_jalali()

    try:
        year = int(year_param)
    except (TypeError, ValueError):
        year = current_year
    if not MIN_YEAR <= year <= MAX_YEAR:
        year = current_year

    try:
        month = int(month_param)
    except (TypeError, ValueError):
        month = current_month if year == current_year else 1
    if not 1 <= month <= 12:
        month = current_month if year == current_year else 1

    return year, month


def build_month(year: int, month: int) -> MonthCalendar:
    """جدول یک ماه شمسی به‌همراه دوره‌هایی که در آن شروع می‌شوند."""
    # همه دوره‌های سال با یک کوئری؛ شمارش ماه‌ها هم از همین درمی‌آید.
    year_start = jalali_to_gregorian(year, 1, 1)
    year_end = jalali_to_gregorian(year + 1, 1, 1) - timedelta(days=1)
    year_courses = (
        Course.objects.published()
        .filter(start_date__range=(year_start, year_end))
        .select_related("category")
        .order_by("start_date", "title")
    )

    month_counts = [0] * 12
    by_day: dict[int, list] = {}
    month_courses = []
    for course in year_courses:
        _, course_month, course_day = gregorian_to_jalali(
            course.start_date.year, course.start_date.month, course.start_date.day
        )
        month_counts[course_month - 1] += 1
        if course_month == month:
            by_day.setdefault(course_day, []).append(course)
            month_courses.append(course)

    today = timezone.localdate()
    first_day = jalali_to_gregorian(year, month, 1)

    cells: list[DayCell | None] = [None] * saturday_index(first_day)
    for day in range(1, jalali_month_days(year, month) + 1):
        current = first_day + timedelta(days=day - 1)
        cells.append(
            DayCell(
                day=day,
                date=current,
                is_friday=saturday_index(current) == 6,
                is_today=current == today,
                is_past=current < today,
                courses=by_day.get(day, []),
            )
        )
    cells += [None] * (-len(cells) % 7)

    weeks = [cells[i : i + 7] for i in range(0, len(cells), 7)]

    return MonthCalendar(
        year=year,
        month=month,
        weeks=weeks,
        courses=month_courses,
        month_counts=month_counts,
    )
