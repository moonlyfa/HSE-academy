"""
تست‌های فاز ۸ — صفحات عمومی دوره‌ها، دسته‌بندی‌ها و مدرسان.

این فایل جدا از tests.py نگه داشته شده تا هر فاز تست‌های خودش را داشته
باشد و پیدا کردن تست مربوط به یک قابلیت ساده بماند.
"""

import json
import re

from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import InstructorProfile
from apps.core.models import ContactMessage
from apps.courses.models import Course, CourseCategory
from apps.courses.tests import CourseTestMixin


def json_ld_blocks(html: str) -> list[dict]:
    """همه بلوک‌های داده ساختاریافته صفحه را می‌خواند و به دیکشنری تبدیل می‌کند."""
    pattern = r'<script type="application/ld\+json">(.*?)</script>'
    return [json.loads(block) for block in re.findall(pattern, html, re.DOTALL)]


class InstructorSlugTests(TestCase):
    """اسلاگ مدرس باید همیشه ساخته شود و یکتا بماند."""

    def test_slug_is_built_from_display_name(self):
        instructor = InstructorProfile.objects.create(display_name="مهندس علی رضایی")
        self.assertTrue(instructor.slug)
        self.assertIn("علی", instructor.slug)

    def test_duplicate_names_get_distinct_slugs(self):
        first = InstructorProfile.objects.create(display_name="علی رضایی")
        second = InstructorProfile.objects.create(display_name="علی رضایی")

        self.assertNotEqual(first.slug, second.slug)

    def test_manual_slug_is_respected(self):
        instructor = InstructorProfile.objects.create(
            display_name="مریم حسینی", slug="maryam-hosseini"
        )
        self.assertEqual(instructor.slug, "maryam-hosseini")

    def test_saving_again_does_not_change_the_slug(self):
        """
        اگر اسلاگ با هر ذخیره عوض شود، لینک‌هایی که قبلاً منتشر شده‌اند
        می‌شکنند و سئوی صفحه از بین می‌رود.
        """
        instructor = InstructorProfile.objects.create(display_name="سعید کاظمی")
        original = instructor.slug

        instructor.display_name = "دکتر سعید کاظمی"
        instructor.save()

        instructor.refresh_from_db()
        self.assertEqual(instructor.slug, original)

    def test_absolute_url_points_to_the_public_page(self):
        instructor = InstructorProfile.objects.create(
            display_name="سعید کاظمی", slug="saeed"
        )
        self.assertEqual(
            instructor.get_absolute_url(),
            reverse("core:instructor_detail", kwargs={"slug": "saeed"}),
        )


class InstructorPageTests(CourseTestMixin, TestCase):
    """صفحه فهرست مدرسان و صفحه هر مدرس."""

    def test_instructor_list_shows_active_instructors(self):
        response = self.client.get(reverse("core:instructors"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "مدرس تست")

    def test_inactive_instructor_is_hidden_from_the_list(self):
        self.instructor.is_active = False
        self.instructor.save()

        response = self.client.get(reverse("core:instructors"))
        self.assertNotContains(response, "مدرس تست")

    def test_instructor_detail_lists_only_published_courses(self):
        self.draft.instructor = self.instructor
        self.draft.save()

        response = self.client.get(self.instructor.get_absolute_url())

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "دوره آنلاین منتشرشده")
        self.assertNotContains(response, "دوره پیش‌نویس")

    def test_inactive_instructor_page_returns_404(self):
        self.instructor.is_active = False
        self.instructor.save()

        self.assertEqual(self.client.get(self.instructor.get_absolute_url()).status_code, 404)

    def test_unknown_instructor_returns_404(self):
        url = reverse("core:instructor_detail", kwargs={"slug": "no-such-person"})
        self.assertEqual(self.client.get(url).status_code, 404)

    def test_course_detail_links_to_the_instructor_page(self):
        response = self.client.get(self.published_online.get_absolute_url())
        self.assertContains(response, self.instructor.get_absolute_url())

    def test_homepage_shows_instructors_section(self):
        response = self.client.get(reverse("core:home"))
        self.assertContains(response, "مدرسان آکادمی")
        self.assertContains(response, "مدرس تست")

    def test_homepage_instructors_section_can_be_switched_off(self):
        from apps.core.models import SiteSetting

        site = SiteSetting.load()
        site.show_instructors_section = False
        site.save()

        response = self.client.get(reverse("core:home"))
        self.assertNotContains(response, "مدرسان آکادمی")


class CategoryLandingTests(CourseTestMixin, TestCase):
    """صفحه دوره‌ها وقتی روی یک دسته‌بندی فیلتر شده است."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.cat_safety.description = "ایمنی در محیط‌های صنعتی و کارگاهی."
        cls.cat_safety.save()

        cls.child = CourseCategory.objects.create(
            name="کار در ارتفاع",
            slug="working-at-height",
            parent=cls.cat_safety,
        )
        cls.child_course = Course.objects.create(
            title="دوره زیردسته",
            slug="child-course",
            category=cls.child,
            price=100_000,
            is_published=True,
        )

    def test_category_description_is_shown(self):
        response = self.client.get(reverse("courses:list"), {"category": "industrial-safety"})
        self.assertContains(response, "ایمنی در محیط‌های صنعتی و کارگاهی.")

    def test_subcategories_are_listed(self):
        response = self.client.get(reverse("courses:list"), {"category": "industrial-safety"})
        self.assertContains(response, "کار در ارتفاع")

    def test_parent_category_includes_courses_of_its_children(self):
        """
        انتخاب یک دسته اصلی نباید نتیجه خالی بدهد فقط به این دلیل که
        دوره‌ها زیرِ زیردسته ثبت شده‌اند.
        """
        response = self.client.get(reverse("courses:list"), {"category": "industrial-safety"})
        self.assertContains(response, "دوره زیردسته")

    def test_filter_sidebar_lists_only_top_level_categories(self):
        response = self.client.get(reverse("courses:list"))
        sidebar_slugs = [c.slug for c in response.context["categories"]]

        self.assertIn("industrial-safety", sidebar_slugs)
        self.assertNotIn("working-at-height", sidebar_slugs)

    def test_unknown_category_does_not_crash(self):
        response = self.client.get(reverse("courses:list"), {"category": "no-such-category"})

        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.context["active_category"])
        self.assertEqual(response.context["total_count"], 0)


class BreadcrumbTests(CourseTestMixin, TestCase):
    """مسیر راهنما هم برای کاربر و هم برای موتور جست‌وجو."""

    def test_course_detail_breadcrumb_contains_category(self):
        response = self.client.get(self.published_online.get_absolute_url())

        self.assertContains(response, "ایمنی صنعتی")
        self.assertContains(response, self.cat_safety.get_absolute_url())

    def test_breadcrumb_structured_data_is_valid_json(self):
        response = self.client.get(self.published_online.get_absolute_url())
        blocks = json_ld_blocks(response.content.decode())

        crumbs = [b for b in blocks if b.get("@type") == "BreadcrumbList"]
        self.assertEqual(len(crumbs), 1)

        names = [item["name"] for item in crumbs[0]["itemListElement"]]
        self.assertEqual(names[0], "صفحه اصلی")
        self.assertEqual(names[-1], self.published_online.title)

    def test_breadcrumb_positions_are_sequential(self):
        response = self.client.get(self.published_online.get_absolute_url())
        crumb = [b for b in json_ld_blocks(response.content.decode())
                 if b["@type"] == "BreadcrumbList"][0]

        positions = [item["position"] for item in crumb["itemListElement"]]
        self.assertEqual(positions, list(range(1, len(positions) + 1)))

    def test_category_page_breadcrumb_shows_the_category_as_current(self):
        response = self.client.get(reverse("courses:list"), {"category": "industrial-safety"})
        self.assertEqual(response.context["breadcrumb_current"], "ایمنی صنعتی")


class CourseStructuredDataTests(CourseTestMixin, TestCase):
    """داده ساختاریافته دوره باید معتبر و صادق باشد."""

    def _course_block(self, course) -> dict:
        response = self.client.get(course.get_absolute_url())
        blocks = json_ld_blocks(response.content.decode())
        return [b for b in blocks if b.get("@type") == "Course"][0]

    def test_course_block_has_the_essentials(self):
        block = self._course_block(self.published_online)

        self.assertEqual(block["name"], "دوره آنلاین منتشرشده")
        self.assertEqual(block["inLanguage"], "fa-IR")
        self.assertTrue(block["url"].endswith(self.published_online.get_absolute_url()))

    def test_price_matches_the_price_shown_on_the_page(self):
        self.published_online.discount_price = 700_000
        self.published_online.save()

        block = self._course_block(self.published_online)
        self.assertEqual(block["offers"]["price"], "700000")

    def test_closed_course_is_marked_sold_out(self):
        block = self._course_block(self.published_free)
        self.assertEqual(block["offers"]["availability"], "https://schema.org/InStock")

        self.published_online.start_date = self.today.replace(year=self.today.year - 1)
        self.published_online.save()

        block = self._course_block(self.published_online)
        self.assertEqual(block["offers"]["availability"], "https://schema.org/SoldOut")

    def test_instructor_is_included_when_set(self):
        block = self._course_block(self.published_online)
        self.assertEqual(block["instructor"]["name"], "مدرس تست")

    def test_quotes_in_the_title_do_not_break_the_json(self):
        """
        اگر عنوان دوره کوتیشن داشته باشد و JSON را دستی می‌ساختیم، ساختار
        صفحه خراب می‌شد. این تست همان حالت را می‌سنجد.
        """
        self.published_free.title = 'دوره «ایمنی» با "نقل قول"'
        self.published_free.save()

        block = self._course_block(self.published_free)
        self.assertEqual(block["name"], 'دوره «ایمنی» با "نقل قول"')

    def test_script_tag_in_the_title_cannot_escape_the_json_block(self):
        """جلوگیری از تزریق اسکریپت از راه فیلدهای متنی دوره."""
        self.published_free.title = "<script>alert(1)</script>"
        self.published_free.save()

        response = self.client.get(self.published_free.get_absolute_url())
        html = response.content.decode()

        self.assertNotIn("<script>alert(1)</script>", html)
        self.assertEqual(self._course_block(self.published_free)["name"],
                         "<script>alert(1)</script>")


class CourseDetailContentTests(CourseTestMixin, TestCase):
    """محتوای صفحه دوره: وضعیت ثبت‌نام، اشتراک‌گذاری و دکمه ثبت‌نام."""

    def test_open_course_shows_the_enroll_button(self):
        response = self.client.get(self.published_online.get_absolute_url())

        self.assertContains(response, "ثبت‌نام این دوره باز است")
        self.assertContains(response, "ثبت‌نام در دوره")

    def test_closed_course_shows_a_closed_notice_instead(self):
        self.published_online.start_date = self.today.replace(year=self.today.year - 1)
        self.published_online.save()

        response = self.client.get(self.published_online.get_absolute_url())

        self.assertContains(response, "مهلت ثبت‌نام این دوره به پایان رسیده است")
        self.assertNotContains(response, "ثبت‌نام این دوره باز است")

    def test_enroll_button_carries_the_course_slug(self):
        response = self.client.get(self.published_online.get_absolute_url())
        self.assertEqual(
            response.context["enroll_url"],
            f"{reverse('core:contact')}?course={self.published_online.slug}",
        )

    def test_share_links_use_the_full_address(self):
        response = self.client.get(self.published_online.get_absolute_url())
        share = response.context["share"]

        self.assertTrue(share["url"].startswith("http"))
        self.assertIn(self.published_online.slug, share["url"])

    def test_specs_show_the_course_capacity(self):
        self.published_online.capacity = 25
        self.published_online.save()

        response = self.client.get(self.published_online.get_absolute_url())
        self.assertContains(response, "ظرفیت")
        self.assertContains(response, "۲۵")


class EnrollmentRequestTests(CourseTestMixin, TestCase):
    """
    تا زمانی که سبد خرید و درگاه پرداخت ساخته نشده (فاز ۱۱ و ۱۲)، دکمه
    ثبت‌نام کاربر را به فرم تماس با موضوعِ از پیش پرشده می‌برد.
    """

    def test_contact_page_prefills_the_subject_with_the_course_title(self):
        response = self.client.get(
            reverse("core:contact"), {"course": self.published_online.slug}
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "درخواست ثبت‌نام در دوره")
        self.assertContains(response, self.published_online.title)

    def test_unpublished_course_is_not_advertised_on_the_contact_page(self):
        response = self.client.get(reverse("core:contact"), {"course": self.draft.slug})

        self.assertIsNone(response.context["requested_course"])
        self.assertNotContains(response, "دوره پیش‌نویس")

    def test_unknown_course_slug_does_not_crash_the_page(self):
        response = self.client.get(reverse("core:contact"), {"course": "no-such-course"})
        self.assertEqual(response.status_code, 200)

    def test_the_request_is_saved_as_a_contact_message(self):
        self.client.post(
            reverse("core:contact"),
            {
                "full_name": "نگین هوشنگی",
                "mobile": "09121234567",
                "subject": f"درخواست ثبت‌نام در دوره «{self.published_online.title}»",
                "message": "لطفاً برای ثبت‌نام راهنمایی کنید.",
            },
        )

        message = ContactMessage.objects.get()
        self.assertIn(self.published_online.title, message.subject)


class NavigationHighlightTests(CourseTestMixin, TestCase):
    """لینک فعال در منوی بالا باید مشخص باشد تا کاربر بداند کجاست."""

    def test_each_section_marks_its_own_menu_item(self):
        cases = {
            reverse("core:home"): "home",
            reverse("courses:list"): "courses",
            reverse("core:calendar"): "calendar",
            reverse("core:instructors"): "instructors",
            reverse("core:about"): "about",
            reverse("core:contact"): "contact",
            reverse("core:certificate_verify"): "verify",
        }

        for url, expected in cases.items():
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.context["nav_active"], expected)
