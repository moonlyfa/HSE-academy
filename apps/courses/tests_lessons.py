"""
تست‌های فاز ۹ — فصل‌ها، درس‌ها و کنترل دسترسی به محتوا.

مهم‌ترین بخش این فایل تست‌های دسترسی است: اگر این‌ها بشکنند، محتوای دوره
پولی برای همه باز می‌شود. پس هر مسیری که به فایل می‌رسد جداگانه تست شده
است، نه فقط صفحه درس.
"""

import shutil
import tempfile

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import InstructorProfile
from apps.courses.access import check_lesson_access
from apps.courses.models import (
    Course,
    CourseCategory,
    Lesson,
    LessonAttachment,
    LessonType,
    Section,
)

User = get_user_model()

# فایل‌های تست در پوشه موقت ساخته می‌شوند تا پوشه واقعی پروژه دست‌نخورده بماند.
TEMP_PROTECTED_ROOT = tempfile.mkdtemp(prefix="hse-test-protected-")


class LessonTestMixin:
    """یک دوره پولی و یک دوره رایگان، هرکدام با یک فصل و چند درس."""

    @classmethod
    def setUpTestData(cls):
        cls.category = CourseCategory.objects.create(name="ایمنی", slug="safety")

        cls.instructor_user = User.objects.create_user(
            mobile="09120000001", password="HseTech!2026"
        )
        cls.instructor = InstructorProfile.objects.create(
            display_name="مدرس دوره", slug="teacher", user=cls.instructor_user
        )

        cls.paid_course = Course.objects.create(
            title="دوره پولی",
            slug="paid-course",
            category=cls.category,
            instructor=cls.instructor,
            price=1_500_000,
            is_published=True,
        )
        cls.free_course = Course.objects.create(
            title="دوره رایگان",
            slug="free-course",
            category=cls.category,
            price=0,
            is_published=True,
        )

        cls.section = Section.objects.create(
            course=cls.paid_course, title="فصل اول", order=0
        )
        cls.preview_lesson = Lesson.objects.create(
            section=cls.section,
            title="درس پیش‌نمایش",
            order=0,
            duration_minutes=10,
            is_free_preview=True,
        )
        cls.paid_lesson = Lesson.objects.create(
            section=cls.section,
            title="درس پولی",
            order=1,
            duration_minutes=25,
        )
        cls.draft_lesson = Lesson.objects.create(
            section=cls.section,
            title="درس منتشرنشده",
            order=2,
            is_published=False,
        )

        cls.free_section = Section.objects.create(
            course=cls.free_course, title="فصل دوره رایگان"
        )
        cls.free_lesson = Lesson.objects.create(
            section=cls.free_section, title="درس دوره رایگان"
        )

        cls.student = User.objects.create_user(
            mobile="09121234567", password="HseTech!2026"
        )
        cls.admin = User.objects.create_user(
            mobile="09129999999", password="HseTech!2026", is_staff=True
        )


class CurriculumModelTests(LessonTestMixin, TestCase):
    """محاسبه‌های ساختار دوره."""

    def test_course_knows_it_has_a_curriculum(self):
        self.assertTrue(self.paid_course.has_curriculum)

    def test_course_without_sections_has_no_curriculum(self):
        empty = Course.objects.create(
            title="بدون فصل", slug="no-sections", category=self.category, is_published=True
        )
        self.assertFalse(empty.has_curriculum)

    def test_lesson_count_ignores_unpublished_lessons(self):
        self.assertEqual(self.paid_course.lesson_count, 2)

    def test_lesson_count_ignores_lessons_of_unpublished_sections(self):
        self.section.is_published = False
        self.section.save()

        self.assertEqual(self.paid_course.lesson_count, 0)

    def test_curriculum_minutes_sums_published_lessons_only(self):
        self.assertEqual(self.paid_course.curriculum_minutes, 35)

    def test_preview_lesson_is_the_first_free_one(self):
        self.assertEqual(self.paid_course.preview_lesson, self.preview_lesson)

    def test_course_without_preview_returns_none(self):
        self.preview_lesson.is_free_preview = False
        self.preview_lesson.save()

        self.assertIsNone(self.paid_course.preview_lesson)

    def test_section_totals(self):
        self.assertEqual(self.section.lesson_count, 2)
        self.assertEqual(self.section.total_minutes, 35)

    def test_lesson_is_hidden_when_its_section_is_hidden(self):
        self.section.is_published = False
        self.section.save()

        self.paid_lesson.refresh_from_db()
        self.assertFalse(self.paid_lesson.is_visible)


class LessonAccessRuleTests(LessonTestMixin, TestCase):
    """
    قواعد دسترسی — حساس‌ترین بخش این فاز.

    هر شکستی در این تست‌ها یعنی محتوای دوره پولی برای کسی باز شده که
    نباید باز می‌شد.
    """

    def test_anonymous_visitor_can_see_a_free_preview(self):
        from django.contrib.auth.models import AnonymousUser

        access = check_lesson_access(AnonymousUser(), self.preview_lesson)
        self.assertTrue(access.allowed)
        self.assertEqual(access.reason, "free_preview")

    def test_anonymous_visitor_cannot_see_a_paid_lesson(self):
        from django.contrib.auth.models import AnonymousUser

        access = check_lesson_access(AnonymousUser(), self.paid_lesson)
        self.assertFalse(access.allowed)
        self.assertEqual(access.reason, "purchase_required")

    def test_logged_in_user_still_cannot_see_a_paid_lesson(self):
        """ورود به سایت با خرید دوره یکی نیست."""
        access = check_lesson_access(self.student, self.paid_lesson)
        self.assertFalse(access.allowed)

    def test_free_course_needs_only_an_account(self):
        from django.contrib.auth.models import AnonymousUser

        self.assertFalse(check_lesson_access(AnonymousUser(), self.free_lesson).allowed)
        self.assertTrue(check_lesson_access(self.student, self.free_lesson).allowed)

    def test_staff_can_see_everything(self):
        self.assertTrue(check_lesson_access(self.admin, self.paid_lesson).allowed)

    def test_course_instructor_can_see_their_own_course(self):
        self.assertTrue(
            check_lesson_access(self.instructor_user, self.paid_lesson).allowed
        )

    def test_instructor_of_another_course_has_no_special_access(self):
        """دسترسی مدرس فقط برای دوره خودش است، نه همه دوره‌ها."""
        other_user = User.objects.create_user(
            mobile="09120000002", password="HseTech!2026"
        )
        InstructorProfile.objects.create(
            display_name="مدرس دیگر", slug="other-teacher", user=other_user
        )

        self.assertFalse(check_lesson_access(other_user, self.paid_lesson).allowed)

    def test_unpublished_lesson_is_closed_even_for_free_preview(self):
        self.draft_lesson.is_free_preview = True
        self.draft_lesson.save()

        access = check_lesson_access(self.student, self.draft_lesson)
        self.assertFalse(access.allowed)
        self.assertEqual(access.reason, "unpublished")

    def test_staff_can_preview_an_unpublished_lesson(self):
        access = check_lesson_access(self.admin, self.draft_lesson)
        self.assertTrue(access.allowed)
        self.assertEqual(access.reason, "staff_preview")

    def test_access_object_is_usable_as_a_condition(self):
        """در Viewها به شکل `if not access:` استفاده می‌شود."""
        self.assertTrue(bool(check_lesson_access(self.admin, self.paid_lesson)))
        self.assertFalse(bool(check_lesson_access(self.student, self.paid_lesson)))


class LessonPageTests(LessonTestMixin, TestCase):
    """صفحه درس برای کاربران مختلف."""

    def test_preview_lesson_is_open_to_everyone(self):
        response = self.client.get(self.preview_lesson.get_absolute_url())

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "درس پیش‌نمایش")
        self.assertNotContains(response, "این درس قفل است")

    def test_paid_lesson_shows_a_locked_page_not_an_error(self):
        response = self.client.get(self.paid_lesson.get_absolute_url())

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "این درس قفل است")
        self.assertContains(response, "ثبت‌نام در دوره")

    def test_locked_lesson_does_not_leak_its_content(self):
        self.paid_lesson.content = "محتوای محرمانه دوره پولی"
        self.paid_lesson.save()

        response = self.client.get(self.paid_lesson.get_absolute_url())
        self.assertNotContains(response, "محتوای محرمانه دوره پولی")

    def test_locked_lesson_is_not_indexed_by_search_engines(self):
        response = self.client.get(self.paid_lesson.get_absolute_url())
        self.assertContains(response, 'name="robots"')

    def test_open_lesson_is_indexable(self):
        response = self.client.get(self.preview_lesson.get_absolute_url())
        self.assertNotContains(response, 'name="robots"')

    def test_unpublished_lesson_returns_404_for_visitors(self):
        url = reverse(
            "courses:lesson",
            kwargs={"slug": self.paid_course.slug, "pk": self.draft_lesson.pk},
        )
        self.assertEqual(self.client.get(url).status_code, 404)

    def test_lesson_of_another_course_cannot_be_opened_through_this_course_url(self):
        """
        اگر فقط شناسه درس را چک می‌کردیم، کسی می‌توانست آدرس دوره رایگان را
        با شناسه درسی از دوره پولی ترکیب کند.
        """
        url = reverse(
            "courses:lesson",
            kwargs={"slug": self.free_course.slug, "pk": self.paid_lesson.pk},
        )
        self.assertEqual(self.client.get(url).status_code, 404)

    def test_lesson_of_an_unpublished_course_is_not_reachable(self):
        self.paid_course.is_published = False
        self.paid_course.save()

        self.assertEqual(
            self.client.get(self.preview_lesson.get_absolute_url()).status_code, 404
        )

    def test_navigation_between_lessons(self):
        response = self.client.get(self.preview_lesson.get_absolute_url())

        self.assertIsNone(response.context["previous_lesson"])
        self.assertEqual(response.context["next_lesson"], self.paid_lesson)
        self.assertEqual(response.context["lesson_position"], 1)
        self.assertEqual(response.context["lesson_total"], 2)

    def test_the_section_of_the_current_lesson_is_the_one_opened(self):
        """
        اگر همیشه فصل اول باز شود، دانشجویی که درس فصل سوم را باز کرده
        باید هربار دستی فصل خودش را پیدا کند.
        """
        second_section = Section.objects.create(
            course=self.paid_course, title="فصل دوم", order=1
        )
        lesson = Lesson.objects.create(
            section=second_section, title="درس فصل دوم", is_free_preview=True
        )

        response = self.client.get(lesson.get_absolute_url())
        opened = [b["section"].pk for b in response.context["curriculum"] if b["is_open"]]

        self.assertEqual(opened, [second_section.pk])

    def test_course_page_opens_the_first_section(self):
        response = self.client.get(self.paid_course.get_absolute_url())
        opened = [b["section"].pk for b in response.context["curriculum"] if b["is_open"]]

        self.assertEqual(opened, [self.section.pk])

    def test_sidebar_shows_the_whole_curriculum(self):
        response = self.client.get(self.preview_lesson.get_absolute_url())

        self.assertContains(response, "فصل اول")
        # عنوان درس قفل‌شده دیده می‌شود (برای فروش)، اما محتوایش نه
        self.assertContains(response, "درس پولی")


@override_settings(PROTECTED_MEDIA_ROOT=TEMP_PROTECTED_ROOT)
class ProtectedFileTests(LessonTestMixin, TestCase):
    """
    فایل ویدیو و جزوه باید دقیقاً همان قواعد صفحه درس را داشته باشند.

    این تست‌ها جدا نوشته شده‌اند چون یک اشتباه رایج این است که فقط صفحه
    درس محافظت شود و آدرس مستقیم فایل باز بماند.
    """

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(TEMP_PROTECTED_ROOT, ignore_errors=True)
        super().tearDownClass()

    def setUp(self):
        self.paid_lesson.video_file.save(
            "paid.mp4", ContentFile(b"video-bytes"), save=True
        )
        self.preview_lesson.video_file.save(
            "preview.mp4", ContentFile(b"preview-bytes"), save=True
        )
        self.attachment = LessonAttachment.objects.create(
            lesson=self.paid_lesson,
            title="جزوه دوره",
            file=ContentFile(b"pdf-bytes", name="handout.pdf"),
        )

    def _video_url(self, lesson) -> str:
        return reverse(
            "courses:lesson_video",
            kwargs={"slug": lesson.section.course.slug, "pk": lesson.pk},
        )

    def test_preview_video_is_served_to_anyone(self):
        response = self.client.get(self._video_url(self.preview_lesson))
        self.assertEqual(response.status_code, 200)

    def test_paid_video_is_not_served_to_a_visitor(self):
        response = self.client.get(self._video_url(self.paid_lesson))
        self.assertEqual(response.status_code, 404)

    def test_paid_video_is_not_served_to_a_logged_in_non_buyer(self):
        self.client.force_login(self.student)
        self.assertEqual(
            self.client.get(self._video_url(self.paid_lesson)).status_code, 404
        )

    def test_paid_video_is_served_to_staff(self):
        self.client.force_login(self.admin)
        self.assertEqual(
            self.client.get(self._video_url(self.paid_lesson)).status_code, 200
        )

    def test_attachment_follows_the_same_rule_as_the_lesson(self):
        self.assertEqual(
            self.client.get(self.attachment.get_absolute_url()).status_code, 404
        )

        self.client.force_login(self.admin)
        self.assertEqual(
            self.client.get(self.attachment.get_absolute_url()).status_code, 200
        )

    def test_attachment_of_another_lesson_cannot_be_downloaded(self):
        url = reverse(
            "courses:lesson_attachment",
            kwargs={
                "slug": self.paid_course.slug,
                "pk": self.preview_lesson.pk,
                "attachment_pk": self.attachment.pk,
            },
        )
        self.assertEqual(self.client.get(url).status_code, 404)

    def test_video_files_are_stored_outside_the_public_media_folder(self):
        """
        اگر ویدیو در media/ ذخیره شود، با یک آدرس ثابت برای همه باز است.
        این تست دقیقاً همان اشتباه را می‌گیرد.
        """
        from django.conf import settings

        stored_path = self.paid_lesson.video_file.path
        self.assertNotIn(str(settings.MEDIA_ROOT), stored_path)
        self.assertIn(TEMP_PROTECTED_ROOT, stored_path)

    def test_raw_protected_path_is_closed_to_visitors(self):
        url = f"/protected-media/{self.paid_lesson.video_file.name}"
        response = self.client.get(url)

        # کاربر عادی به صفحه ورود پنل مدیریت هدایت می‌شود، نه به فایل
        self.assertIn(response.status_code, (302, 403))

    def test_raw_protected_path_works_for_staff(self):
        self.client.force_login(self.admin)
        url = f"/protected-media/{self.paid_lesson.video_file.name}"

        self.assertEqual(self.client.get(url).status_code, 200)

    def test_missing_file_gives_404_not_a_server_error(self):
        self.paid_lesson.video_file.name = "lessons/1/videos/gone.mp4"
        self.paid_lesson.save()
        self.client.force_login(self.admin)

        self.assertEqual(
            self.client.get(self._video_url(self.paid_lesson)).status_code, 404
        )

    @override_settings(USE_X_ACCEL_REDIRECT=True, X_ACCEL_REDIRECT_PREFIX="/internal/")
    def test_production_mode_hands_the_file_to_the_web_server(self):
        response = self.client.get(self._video_url(self.preview_lesson))

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response["X-Accel-Redirect"].startswith("/internal/"))
        self.assertEqual(response.content, b"")  # فایل را Nginx می‌فرستد، نه پایتون


class CourseCurriculumDisplayTests(LessonTestMixin, TestCase):
    """نمایش سرفصل‌ها در صفحه دوره."""

    def test_course_page_lists_sections_and_lessons(self):
        response = self.client.get(self.paid_course.get_absolute_url())

        self.assertContains(response, "فصل اول")
        self.assertContains(response, "درس پیش‌نمایش")
        self.assertContains(response, "پیش‌نمایش رایگان")

    def test_unpublished_lesson_is_not_listed(self):
        response = self.client.get(self.paid_course.get_absolute_url())
        self.assertNotContains(response, "درس منتشرنشده")

    def test_preview_button_links_to_the_free_lesson(self):
        response = self.client.get(self.paid_course.get_absolute_url())
        self.assertContains(response, self.preview_lesson.get_absolute_url())

    def test_text_syllabus_is_used_when_there_are_no_sections(self):
        """دوره‌های قدیمی که فصل‌بندی نشده‌اند نباید سرفصل خالی نشان دهند."""
        course = Course.objects.create(
            title="دوره متنی",
            slug="text-syllabus",
            category=self.category,
            syllabus="سرفصل یک\nسرفصل دو",
            is_published=True,
        )

        response = self.client.get(course.get_absolute_url())
        self.assertContains(response, "سرفصل یک")

    def test_lesson_count_is_shown_in_the_specs(self):
        response = self.client.get(self.paid_course.get_absolute_url())
        self.assertContains(response, "تعداد درس")
