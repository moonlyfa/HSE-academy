"""
تقویم آموزشی ماهانه.

قاعده‌ها:

- جدول یک ماه شمسی است، از شنبه شروع می‌شود و جمعه ستون آخر است.
- هر دوره روی روز شروعش می‌نشیند و لینک مستقیم به صفحه خودش است.
- دوره پیش‌نویس، دوره بدون تاریخ و دوره آنلاینِ پنهان در تقویم نمی‌آیند.
- سال و ماه از آدرس خوانده می‌شود؛ ورودی نامعتبر به ماه جاری برمی‌گردد.
"""

from datetime import UTC, date, datetime, timedelta
from unittest.mock import patch

from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from apps.core.jalali import (
    gregorian_to_jalali,
    jalali_month_days,
    jalali_to_gregorian,
)

from .calendar import build_month, parse_year_month, saturday_index
from .models import Course, CourseCategory, CourseType

# ۱ مهر ۱۴۰۵ = چهارشنبه ۲۳ سپتامبر ۲۰۲۶ (همان چیزی که تقویم رسمی نشان می‌دهد)
MEHR_1 = date(2026, 9, 23)
FAKE_TODAY = date(2026, 10, 5)  # ۱۳ مهر ۱۴۰۵


def mehr(day: int) -> date:
    return MEHR_1 + timedelta(days=day - 1)


class JalaliConversionTests(SimpleTestCase):
    def test_known_dates(self):
        self.assertEqual(jalali_to_gregorian(1405, 1, 1), date(2026, 3, 21))
        self.assertEqual(jalali_to_gregorian(1405, 7, 1), MEHR_1)
        self.assertEqual(jalali_to_gregorian(1403, 12, 30), date(2025, 3, 20))

    def test_round_trip_over_many_years(self):
        current = date(2000, 1, 1)
        while current < date(2060, 1, 1):
            jy, jm, jd = gregorian_to_jalali(current.year, current.month, current.day)
            self.assertEqual(jalali_to_gregorian(jy, jm, jd), current)
            current += timedelta(days=1)

    def test_month_lengths(self):
        self.assertEqual(jalali_month_days(1405, 1), 31)
        self.assertEqual(jalali_month_days(1405, 6), 31)
        self.assertEqual(jalali_month_days(1405, 7), 30)
        self.assertEqual(jalali_month_days(1405, 11), 30)
        self.assertEqual(jalali_month_days(1403, 12), 30)  # کبیسه
        self.assertEqual(jalali_month_days(1404, 12), 29)


class MonthGridTests(TestCase):
    def test_week_starts_on_saturday(self):
        self.assertEqual(saturday_index(date(2026, 9, 26)), 0)  # شنبه
        self.assertEqual(saturday_index(date(2026, 10, 2)), 6)  # جمعه

    def test_mehr_1405_layout(self):
        calendar = build_month(1405, 7)
        first_week = calendar.weeks[0]

        # ۱ مهر چهارشنبه است: شنبه تا سه‌شنبه خالی
        self.assertEqual(first_week[:4], [None, None, None, None])
        self.assertEqual(first_week[4].day, 1)

        days = [cell for week in calendar.weeks for cell in week if cell]
        self.assertEqual(len(days), 30)
        self.assertTrue(all(len(week) == 7 for week in calendar.weeks))
        self.assertEqual(
            [cell.day for cell in days if cell.is_friday], [3, 10, 17, 24]
        )

    def test_today_and_past_days_are_marked(self):
        with patch("apps.courses.calendar.timezone.localdate", return_value=FAKE_TODAY):
            calendar = build_month(1405, 7)
        days = {cell.day: cell for week in calendar.weeks for cell in week if cell}
        self.assertTrue(days[13].is_today)
        self.assertTrue(days[12].is_past)
        self.assertFalse(days[14].is_past)


class ParamsTests(SimpleTestCase):
    def setUp(self):
        patcher = patch("apps.courses.calendar.timezone.localdate", return_value=FAKE_TODAY)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_defaults_to_the_current_month(self):
        self.assertEqual(parse_year_month(None, None), (1405, 7))

    def test_reads_year_and_month(self):
        self.assertEqual(parse_year_month("1406", "2"), (1406, 2))

    def test_other_year_without_month_starts_at_farvardin(self):
        self.assertEqual(parse_year_month("1406", None), (1406, 1))

    def test_nonsense_falls_back_to_now(self):
        for year, month in [("abc", "x"), ("99999", "7"), ("1405", "13"), ("1405", "0")]:
            with self.subTest(year=year, month=month):
                self.assertEqual(parse_year_month(year, month), (1405, 7))


class CalendarPageTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        category = CourseCategory.objects.create(name="ایمنی", slug="safety")
        common = {"category": category, "price": 1_000_000, "is_published": True}

        cls.height = Course.objects.create(
            title="ایمنی کار در ارتفاع", slug="height", start_date=mehr(18),
            end_date=mehr(20), location="تهران", **common,
        )
        cls.fire = Course.objects.create(
            title="آتش‌نشانی و اطفای حریق", slug="fire", start_date=mehr(21), **common
        )
        cls.next_month = Course.objects.create(
            title="ممیزی داخلی ISO 45001", slug="iso-audit",
            start_date=jalali_to_gregorian(1405, 8, 5), **common,
        )
        cls.draft = Course.objects.create(
            title="دوره پیش‌نویس", slug="draft", start_date=mehr(18),
            category=category, is_published=False,
        )
        cls.online = Course.objects.create(
            title="دوره آنلاین پنهان", slug="hidden-online", start_date=mehr(18),
            course_type=CourseType.ONLINE_LIVE, **common,
        )
        cls.undated = Course.objects.create(title="دوره بی‌تاریخ", slug="undated", **common)

    def get(self, **params):
        with patch("apps.courses.calendar.timezone.localdate", return_value=FAKE_TODAY):
            return self.client.get(reverse("core:calendar"), params)

    def test_course_sits_on_its_start_day_and_links_to_its_page(self):
        response = self.get(year=1405, month=7)
        self.assertEqual(response.status_code, 200)

        days = {
            cell.day: cell
            for week in response.context["calendar"].weeks
            for cell in week
            if cell
        }
        self.assertEqual(days[18].courses, [self.height])
        self.assertEqual(days[21].courses, [self.fire])
        # فقط روز شروع؛ روزهای بعدی دوره چندروزه خالی‌اند
        self.assertEqual(days[19].courses, [])

        self.assertContains(response, f'href="{self.height.get_absolute_url()}" class="tcal__event"')
        self.assertContains(response, f'href="{self.fire.get_absolute_url()}" class="tcal__event"')

    def test_other_months_courses_are_not_in_this_month(self):
        response = self.get(year=1405, month=7)
        self.assertNotContains(response, self.next_month.title)

        response = self.get(year=1405, month=8)
        self.assertContains(response, self.next_month.title)
        self.assertNotContains(response, self.height.title)

    def test_drafts_hidden_online_and_undated_courses_stay_out(self):
        response = self.get(year=1405, month=7)
        for course in (self.draft, self.online, self.undated):
            with self.subTest(course=course.slug):
                self.assertNotContains(response, course.slug)

    def test_default_is_the_current_month(self):
        response = self.get()
        self.assertEqual(response.context["calendar"].year, 1405)
        self.assertEqual(response.context["calendar"].month, 7)
        self.assertContains(response, self.height.title)

    def test_month_buttons_show_how_many_courses_each_month_has(self):
        response = self.get(year=1405, month=7)
        counts = response.context["calendar"].month_counts
        self.assertEqual(counts[6], 2)  # مهر
        self.assertEqual(counts[7], 1)  # آبان
        self.assertEqual(sum(counts), 3)

    def test_month_list_shows_date_range_and_location(self):
        response = self.get(year=1405, month=7)
        self.assertContains(response, "۱۸ مهر ۱۴۰۵")
        self.assertContains(response, "تا ۲۰ مهر ۱۴۰۵")
        self.assertContains(response, "تهران")

    def test_empty_month_points_to_the_next_month_with_courses(self):
        response = self.get(year=1405, month=1)
        self.assertContains(response, "در فروردین ۱۴۰۵ دوره‌ای برگزار نمی‌شود")
        self.assertContains(response, "?year=1405&amp;month=7")

    def test_year_arrows_keep_the_month(self):
        response = self.get(year=1405, month=7)
        self.assertContains(response, "?year=1404&amp;month=7")
        self.assertContains(response, "?year=1406&amp;month=7")

    def test_past_days_are_dimmed_but_still_link(self):
        Course.objects.filter(pk=self.height.pk).update(start_date=mehr(2))
        response = self.get(year=1405, month=7)
        self.assertContains(response, "is-past")
        self.assertContains(response, self.height.get_absolute_url())

    def test_bad_params_do_not_break_the_page(self):
        response = self.get(year="abc", month="99")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["calendar"].month, 7)

    def test_menu_highlights_the_calendar(self):
        self.assertEqual(self.get().context["nav_active"], "calendar")


class TodayIsLocalTests(TestCase):
    def test_calendar_uses_tehran_date_not_utc(self):
        # ساعت ۲۲ UTC روز ۴ اکتبر در تهران بامداد ۵ اکتبر (۱۳ مهر) است
        late_utc = datetime(2026, 10, 4, 22, 0, tzinfo=UTC)
        with patch("django.utils.timezone.now", return_value=late_utc):
            response = self.client.get(reverse("core:calendar"))
        days = {
            cell.day: cell
            for week in response.context["calendar"].weeks
            for cell in week
            if cell
        }
        self.assertTrue(days[13].is_today)
