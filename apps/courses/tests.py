"""تست‌های دوره‌ها، فیلترها و جست‌وجو."""

from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import InstructorProfile
from apps.courses.models import Course, CourseCategory, CourseLevel, CourseType


class CourseTestMixin:
    """داده مشترک تست‌ها."""

    @classmethod
    def setUpTestData(cls):
        cls.today = timezone.now().date()

        cls.cat_safety = CourseCategory.objects.create(
            name="ایمنی صنعتی", slug="industrial-safety", order=1
        )
        cls.cat_risk = CourseCategory.objects.create(
            name="ارزیابی ریسک", slug="risk-assessment", order=2
        )
        cls.instructor = InstructorProfile.objects.create(display_name="مدرس تست")

        cls.published_online = Course.objects.create(
            title="دوره آنلاین منتشرشده",
            slug="online-published",
            category=cls.cat_safety,
            instructor=cls.instructor,
            course_type=CourseType.ONLINE_LIVE,
            level=CourseLevel.BEGINNER,
            price=1_000_000,
            start_date=cls.today + timedelta(days=10),
            is_published=True,
            is_featured=True,
        )
        cls.published_free = Course.objects.create(
            title="دوره رایگان",
            slug="free-course",
            category=cls.cat_risk,
            course_type=CourseType.OFFLINE_RECORDED,
            level=CourseLevel.ADVANCED,
            price=0,
            is_published=True,
        )
        cls.draft = Course.objects.create(
            title="دوره پیش‌نویس",
            slug="draft-course",
            category=cls.cat_safety,
            price=500_000,
            is_published=False,
        )


class CourseModelTests(CourseTestMixin, TestCase):
    def test_published_queryset_excludes_drafts(self):
        slugs = set(Course.objects.published().values_list("slug", flat=True))
        self.assertEqual(slugs, {"online-published", "free-course"})

    def test_upcoming_only_returns_future_courses(self):
        past = Course.objects.create(
            title="دوره گذشته",
            slug="past-course",
            category=self.cat_safety,
            start_date=self.today - timedelta(days=5),
            is_published=True,
        )
        upcoming_slugs = set(Course.objects.upcoming().values_list("slug", flat=True))
        self.assertIn("online-published", upcoming_slugs)
        self.assertNotIn(past.slug, upcoming_slugs)

    def test_final_price_uses_discount_when_lower(self):
        self.published_online.discount_price = 700_000
        self.assertEqual(self.published_online.final_price, 700_000)
        self.assertTrue(self.published_online.has_discount)
        self.assertEqual(self.published_online.discount_percent, 30)

    def test_discount_ignored_when_not_lower_than_price(self):
        """تخفیف بالاتر از قیمت اصلی نباید اعمال شود."""
        self.published_online.discount_price = 2_000_000
        self.assertEqual(self.published_online.final_price, 1_000_000)
        self.assertFalse(self.published_online.has_discount)
        self.assertEqual(self.published_online.discount_percent, 0)

    def test_free_course_detection(self):
        self.assertTrue(self.published_free.is_free)
        self.assertFalse(self.published_online.is_free)

    def test_syllabus_items_splits_lines_and_ignores_blanks(self):
        self.published_online.syllabus = "بخش اول\n\n  بخش دوم  \n\nبخش سوم"
        self.assertEqual(
            self.published_online.syllabus_items, ["بخش اول", "بخش دوم", "بخش سوم"]
        )

    def test_category_url_points_to_filtered_course_list(self):
        """دکمه دسته‌بندی باید به همان صفحه دوره‌ها با فیلتر برود."""
        self.assertEqual(
            self.cat_risk.get_absolute_url(),
            f"{reverse('courses:list')}?category=risk-assessment",
        )

    def test_registration_closed_for_unpublished_course(self):
        self.assertFalse(self.draft.registration_open)

    def test_offline_course_without_start_date_stays_open(self):
        self.assertTrue(self.published_free.registration_open)


class CourseListViewTests(CourseTestMixin, TestCase):
    def setUp(self):
        self.url = reverse("courses:list")

    def test_list_shows_only_published_courses(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "دوره آنلاین منتشرشده")
        self.assertNotContains(response, "دوره پیش‌نویس")

    def test_filter_by_category(self):
        response = self.client.get(self.url, {"category": "risk-assessment"})
        self.assertContains(response, "دوره رایگان")
        self.assertNotContains(response, "دوره آنلاین منتشرشده")

    def test_filter_by_course_type(self):
        response = self.client.get(self.url, {"type": "online_live"})
        self.assertContains(response, "دوره آنلاین منتشرشده")
        self.assertNotContains(response, "دوره رایگان")

    def test_filter_by_level(self):
        response = self.client.get(self.url, {"level": "advanced"})
        self.assertContains(response, "دوره رایگان")
        self.assertNotContains(response, "دوره آنلاین منتشرشده")

    def test_filter_by_free_price(self):
        response = self.client.get(self.url, {"price": "free"})
        self.assertContains(response, "دوره رایگان")
        self.assertNotContains(response, "دوره آنلاین منتشرشده")

    def test_invalid_filter_value_is_ignored_not_crashing(self):
        """مقدار نامعتبر در آدرس نباید سایت را بشکند."""
        response = self.client.get(self.url, {"type": "not-a-real-type", "level": "xyz"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "دوره آنلاین منتشرشده")

    def test_sort_by_cheapest(self):
        response = self.client.get(self.url, {"sort": "cheapest"})
        titles = [c.title for c in response.context["courses"]]
        self.assertEqual(titles[0], "دوره رایگان")

    def test_invalid_sort_falls_back_to_default(self):
        response = self.client.get(self.url, {"sort": "; DROP TABLE"})
        self.assertEqual(response.status_code, 200)


class CourseDetailViewTests(CourseTestMixin, TestCase):
    def test_published_course_detail_loads(self):
        response = self.client.get(self.published_online.get_absolute_url())
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "دوره آنلاین منتشرشده")

    def test_draft_course_returns_404(self):
        """دوره منتشرنشده نباید از طریق آدرس مستقیم قابل دیدن باشد."""
        url = reverse("courses:detail", kwargs={"slug": "draft-course"})
        self.assertEqual(self.client.get(url).status_code, 404)


class SearchViewTests(CourseTestMixin, TestCase):
    def setUp(self):
        self.url = reverse("core:search")

    def test_search_finds_course_by_title(self):
        response = self.client.get(self.url, {"q": "رایگان"})
        self.assertContains(response, "دوره رایگان")
        self.assertNotContains(response, "دوره آنلاین منتشرشده")

    def test_search_does_not_return_drafts(self):
        response = self.client.get(self.url, {"q": "پیش‌نویس"})
        self.assertNotContains(response, "دوره پیش‌نویس")

    def test_empty_query_returns_no_results_without_error(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["total_count"], 0)


class CalendarViewTests(CourseTestMixin, TestCase):
    def test_calendar_lists_only_upcoming_courses(self):
        response = self.client.get(reverse("core:calendar"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "دوره آنلاین منتشرشده")
        # دوره آفلاین بدون تاریخ شروع در تقویم نمی‌آید
        self.assertNotContains(response, "دوره رایگان")
