"""
تست‌های فاز ۱۰ — پیشرفت دانشجو و داشبورد.

دو چیز اینجا حساس است:
۱. درصد پیشرفت باید در همه صفحه‌ها یک عدد باشد (پس همه از یک تابع می‌آید).
۲. پیشرفت هر کاربر فقط مال خودش است و نباید به کاربر دیگری نشت کند.
"""

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.courses.models import Course, CourseCategory, Lesson, LessonProgress, Section
from apps.courses.progress import (
    course_progress,
    learner_courses,
    learner_stats,
    record_view,
    save_position,
    set_completed,
)

User = get_user_model()


class ProgressTestMixin:
    """یک دوره رایگان با دو فصل و چهار درس."""

    @classmethod
    def setUpTestData(cls):
        cls.category = CourseCategory.objects.create(name="ایمنی", slug="safety")

        cls.course = Course.objects.create(
            title="دوره رایگان",
            slug="free-course",
            category=cls.category,
            price=0,
            is_published=True,
        )

        cls.section_one = Section.objects.create(
            course=cls.course, title="فصل اول", order=0
        )
        cls.section_two = Section.objects.create(
            course=cls.course, title="فصل دوم", order=1
        )

        cls.lesson_a = Lesson.objects.create(
            section=cls.section_one, title="درس ۱", order=0, duration_minutes=10
        )
        cls.lesson_b = Lesson.objects.create(
            section=cls.section_one, title="درس ۲", order=1, duration_minutes=20
        )
        cls.lesson_c = Lesson.objects.create(
            section=cls.section_two, title="درس ۳", order=0, duration_minutes=30
        )
        cls.lesson_d = Lesson.objects.create(
            section=cls.section_two, title="درس ۴", order=1, duration_minutes=40
        )

        cls.student = User.objects.create_user(
            mobile="09121234567", password="HseTech!2026"
        )
        cls.other = User.objects.create_user(
            mobile="09127654321", password="HseTech!2026"
        )


class CourseProgressCalculationTests(ProgressTestMixin, TestCase):
    def test_no_progress_means_zero_percent(self):
        progress = course_progress(self.student, self.course)

        self.assertEqual(progress.total, 4)
        self.assertEqual(progress.completed, 0)
        self.assertEqual(progress.percent, 0)
        self.assertFalse(progress.is_finished)

    def test_percent_is_rounded_to_a_whole_number(self):
        set_completed(self.student, self.lesson_a, True)

        self.assertEqual(course_progress(self.student, self.course).percent, 25)

    def test_finishing_every_lesson_reaches_a_hundred(self):
        for lesson in (self.lesson_a, self.lesson_b, self.lesson_c, self.lesson_d):
            set_completed(self.student, lesson, True)

        progress = course_progress(self.student, self.course)
        self.assertEqual(progress.percent, 100)
        self.assertTrue(progress.is_finished)

    def test_course_without_lessons_does_not_divide_by_zero(self):
        empty = Course.objects.create(
            title="بدون درس", slug="empty", category=self.category, is_published=True
        )

        progress = course_progress(self.student, empty)
        self.assertEqual(progress.percent, 0)
        self.assertFalse(progress.is_finished)

    def test_unpublished_lessons_are_not_counted(self):
        self.lesson_d.is_published = False
        self.lesson_d.save()

        self.assertEqual(course_progress(self.student, self.course).total, 3)

    def test_lessons_of_an_unpublished_section_are_not_counted(self):
        self.section_two.is_published = False
        self.section_two.save()

        self.assertEqual(course_progress(self.student, self.course).total, 2)

    def test_next_lesson_is_the_first_unfinished_one_in_order(self):
        set_completed(self.student, self.lesson_a, True)
        set_completed(self.student, self.lesson_b, True)

        self.assertEqual(course_progress(self.student, self.course).next_lesson, self.lesson_c)

    def test_next_lesson_follows_section_order_not_lesson_id(self):
        """
        اگر ترتیب فصل‌ها نادیده گرفته شود، «درس بعدی» می‌تواند از فصل
        اشتباه انتخاب شود.
        """
        self.section_one.order = 5  # فصل اول را عقب می‌بریم
        self.section_one.save()

        self.assertEqual(course_progress(self.student, self.course).next_lesson, self.lesson_c)

    def test_finished_course_has_no_next_lesson(self):
        for lesson in (self.lesson_a, self.lesson_b, self.lesson_c, self.lesson_d):
            set_completed(self.student, lesson, True)

        self.assertIsNone(course_progress(self.student, self.course).next_lesson)

    def test_anonymous_visitor_sees_zero_progress(self):
        from django.contrib.auth.models import AnonymousUser

        progress = course_progress(AnonymousUser(), self.course)
        self.assertEqual(progress.completed, 0)
        self.assertEqual(progress.total, 4)

    def test_progress_of_one_user_does_not_leak_to_another(self):
        set_completed(self.student, self.lesson_a, True)
        set_completed(self.student, self.lesson_b, True)

        self.assertEqual(course_progress(self.other, self.course).completed, 0)

    def test_resume_lesson_prefers_the_unfinished_one(self):
        record_view(self.student, self.lesson_c)
        set_completed(self.student, self.lesson_a, True)

        self.assertEqual(course_progress(self.student, self.course).resume_lesson, self.lesson_b)


class ProgressRecordingTests(ProgressTestMixin, TestCase):
    def test_opening_a_lesson_creates_one_record(self):
        record_view(self.student, self.lesson_a)
        record_view(self.student, self.lesson_a)

        self.assertEqual(LessonProgress.objects.filter(user=self.student).count(), 1)

    def test_viewing_is_not_the_same_as_completing(self):
        record_view(self.student, self.lesson_a)

        self.assertFalse(LessonProgress.objects.get().is_completed)
        self.assertEqual(course_progress(self.student, self.course).percent, 0)

    def test_nothing_is_recorded_for_a_guest(self):
        from django.contrib.auth.models import AnonymousUser

        self.assertIsNone(record_view(AnonymousUser(), self.lesson_a))
        self.assertEqual(LessonProgress.objects.count(), 0)

    def test_completing_stores_the_time(self):
        progress = set_completed(self.student, self.lesson_a, True)
        self.assertIsNotNone(progress.completed_at)

    def test_undoing_completion_clears_the_time(self):
        set_completed(self.student, self.lesson_a, True)
        progress = set_completed(self.student, self.lesson_a, False)

        self.assertFalse(progress.is_completed)
        self.assertIsNone(progress.completed_at)

    def test_video_position_is_saved(self):
        save_position(self.student, self.lesson_a, 125)

        self.assertEqual(LessonProgress.objects.get().last_position_seconds, 125)

    def test_negative_position_is_stored_as_zero(self):
        save_position(self.student, self.lesson_a, -10)

        self.assertEqual(LessonProgress.objects.get().last_position_seconds, 0)


class LearnerOverviewTests(ProgressTestMixin, TestCase):
    def test_my_courses_lists_only_started_courses(self):
        other_course = Course.objects.create(
            title="دوره دست‌نخورده", slug="untouched", category=self.category, is_published=True
        )
        Section.objects.create(course=other_course, title="فصل")

        record_view(self.student, self.lesson_a)

        titles = [p.course.title for p in learner_courses(self.student)]
        self.assertEqual(titles, ["دوره رایگان"])

    def test_my_courses_are_sorted_by_most_recent_activity(self):
        second = Course.objects.create(
            title="دوره دوم", slug="second", category=self.category, price=0, is_published=True
        )
        second_lesson = Lesson.objects.create(
            section=Section.objects.create(course=second, title="فصل"), title="درس"
        )

        record_view(self.student, self.lesson_a)
        record_view(self.student, second_lesson)

        titles = [p.course.title for p in learner_courses(self.student)]
        self.assertEqual(titles[0], "دوره دوم")

    def test_stats_count_completed_lessons_and_minutes(self):
        set_completed(self.student, self.lesson_a, True)  # ۱۰ دقیقه
        set_completed(self.student, self.lesson_c, True)  # ۳۰ دقیقه

        stats = learner_stats(self.student)
        self.assertEqual(stats["completed_lessons"], 2)
        self.assertEqual(stats["minutes"], 40)
        self.assertEqual(stats["courses"], 1)

    def test_stats_are_zero_for_a_guest(self):
        from django.contrib.auth.models import AnonymousUser

        self.assertEqual(learner_stats(AnonymousUser())["completed_lessons"], 0)

    def test_an_unpublished_course_disappears_from_my_courses(self):
        """
        اگر ادمین دوره‌ای را از انتشار خارج کند، نباید در فهرست کاربر
        بماند؛ وگرنه کاربر روی دوره‌ای کلیک می‌کند که صفحه‌اش ۴۰۴ می‌دهد.
        """
        record_view(self.student, self.lesson_a)
        self.assertEqual(len(learner_courses(self.student)), 1)

        self.course.is_published = False
        self.course.save()

        self.assertEqual(learner_courses(self.student), [])

    def test_my_courses_is_empty_without_any_activity(self):
        self.assertEqual(learner_courses(self.student), [])


class LessonCompletionViewTests(ProgressTestMixin, TestCase):
    def setUp(self):
        self.client.force_login(self.student)
        self.url = reverse(
            "courses:lesson_complete",
            kwargs={"slug": self.course.slug, "pk": self.lesson_a.pk},
        )

    def test_marking_a_lesson_complete(self):
        self.client.post(self.url, {"completed": "1"})

        self.assertTrue(LessonProgress.objects.get(lesson=self.lesson_a).is_completed)

    def test_undoing_completion(self):
        self.client.post(self.url, {"completed": "1"})
        self.client.post(self.url, {"completed": "0"})

        self.assertFalse(LessonProgress.objects.get(lesson=self.lesson_a).is_completed)

    def test_completing_can_jump_to_the_next_lesson(self):
        response = self.client.post(self.url, {"completed": "1", "go_next": "1"})

        self.assertRedirects(response, self.lesson_b.get_absolute_url())

    def test_get_requests_are_rejected(self):
        """
        تغییر وضعیت با GET خطرناک است: یک لینک ساده یا پیش‌بارگذاری
        مرورگر می‌توانست درس‌ها را بی‌اجازه تکمیل کند.
        """
        self.assertEqual(self.client.get(self.url).status_code, 405)

    def test_a_guest_is_sent_to_the_login_page(self):
        self.client.logout()
        response = self.client.post(self.url, {"completed": "1"})

        self.assertEqual(response.status_code, 302)
        self.assertEqual(LessonProgress.objects.count(), 0)

    def test_a_locked_lesson_cannot_be_marked_complete(self):
        paid = Course.objects.create(
            title="دوره پولی",
            slug="paid",
            category=self.category,
            price=900_000,
            is_published=True,
        )
        locked = Lesson.objects.create(
            section=Section.objects.create(course=paid, title="فصل"), title="درس قفل"
        )

        url = reverse(
            "courses:lesson_complete", kwargs={"slug": paid.slug, "pk": locked.pk}
        )
        self.assertEqual(self.client.post(url, {"completed": "1"}).status_code, 404)
        self.assertEqual(LessonProgress.objects.count(), 0)


class LessonPositionViewTests(ProgressTestMixin, TestCase):
    def setUp(self):
        self.client.force_login(self.student)
        self.url = reverse(
            "courses:lesson_position",
            kwargs={"slug": self.course.slug, "pk": self.lesson_a.pk},
        )

    def test_position_is_saved(self):
        response = self.client.post(self.url, {"seconds": "90"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(LessonProgress.objects.get().last_position_seconds, 90)

    def test_a_broken_value_returns_an_error_not_a_crash(self):
        response = self.client.post(self.url, {"seconds": "abc"})
        self.assertEqual(response.status_code, 400)

    def test_a_guest_cannot_write_progress(self):
        self.client.logout()
        self.client.post(self.url, {"seconds": "90"})

        self.assertEqual(LessonProgress.objects.count(), 0)


class DashboardTests(ProgressTestMixin, TestCase):
    def setUp(self):
        self.client.force_login(self.student)

    def test_dashboard_shows_the_empty_state_at_first(self):
        response = self.client.get(reverse("accounts:dashboard"))

        self.assertContains(response, "هنوز دوره‌ای را شروع نکرده‌اید")

    def test_dashboard_shows_a_continue_card_after_activity(self):
        record_view(self.student, self.lesson_b)

        response = self.client.get(reverse("accounts:dashboard"))
        self.assertContains(response, "ادامه یادگیری")

    def test_the_continue_button_points_at_the_first_unfinished_lesson(self):
        """
        دکمه باید به جایی ببرد که کاربر باید *ادامه* بدهد، نه به آخرین
        درسی که باز کرده. در غیر این صورت، کاربری که همین حالا درسی را
        تمام کرده دوباره به همان درس برمی‌گردد.
        """
        set_completed(self.student, self.lesson_a, True)
        record_view(self.student, self.lesson_a)

        response = self.client.get(reverse("accounts:dashboard"))
        self.assertEqual(response.context["resume_lesson"], self.lesson_b)

    def test_a_finished_course_offers_a_review_instead(self):
        for lesson in (self.lesson_a, self.lesson_b, self.lesson_c, self.lesson_d):
            set_completed(self.student, lesson, True)

        response = self.client.get(reverse("accounts:dashboard"))
        self.assertContains(response, "مرور دوباره")

    def test_dashboard_stats_reflect_real_activity(self):
        set_completed(self.student, self.lesson_a, True)

        response = self.client.get(reverse("accounts:dashboard"))
        self.assertEqual(response.context["stats"]["completed_lessons"], 1)

    def test_my_courses_page_lists_the_course_with_its_percent(self):
        set_completed(self.student, self.lesson_a, True)

        response = self.client.get(reverse("accounts:my_courses"))
        self.assertContains(response, "دوره رایگان")
        self.assertContains(response, "۲۵٪")

    def test_finished_courses_are_listed_separately(self):
        for lesson in (self.lesson_a, self.lesson_b, self.lesson_c, self.lesson_d):
            set_completed(self.student, lesson, True)

        response = self.client.get(reverse("accounts:my_courses"))
        self.assertEqual(len(response.context["finished"]), 1)
        self.assertEqual(len(response.context["in_progress"]), 0)

    def test_my_courses_requires_login(self):
        self.client.logout()
        response = self.client.get(reverse("accounts:my_courses"))

        self.assertEqual(response.status_code, 302)

    def test_dashboard_pages_are_not_indexed(self):
        for name in ("accounts:dashboard", "accounts:my_courses"):
            with self.subTest(page=name):
                response = self.client.get(reverse(name))
                self.assertContains(response, 'name="robots"')


class LessonPageProgressTests(ProgressTestMixin, TestCase):
    def test_opening_a_lesson_records_it(self):
        self.client.force_login(self.student)
        self.client.get(self.lesson_a.get_absolute_url())

        self.assertTrue(
            LessonProgress.objects.filter(user=self.student, lesson=self.lesson_a).exists()
        )

    def test_a_locked_lesson_is_not_recorded_as_viewed(self):
        paid = Course.objects.create(
            title="دوره پولی",
            slug="paid",
            category=self.category,
            price=900_000,
            is_published=True,
        )
        locked = Lesson.objects.create(
            section=Section.objects.create(course=paid, title="فصل"), title="درس قفل"
        )

        self.client.force_login(self.student)
        self.client.get(locked.get_absolute_url())

        self.assertEqual(LessonProgress.objects.count(), 0)

    def test_completed_lessons_are_ticked_in_the_curriculum(self):
        set_completed(self.student, self.lesson_a, True)
        self.client.force_login(self.student)

        response = self.client.get(self.course.get_absolute_url())
        rows = [
            row
            for block in response.context["curriculum"]
            for row in block["lessons"]
        ]
        completed = [row["lesson"].pk for row in rows if row["is_completed"]]

        self.assertEqual(completed, [self.lesson_a.pk])

    def test_the_course_page_shows_a_resume_button_once_started(self):
        record_view(self.student, self.lesson_a)
        self.client.force_login(self.student)

        response = self.client.get(self.course.get_absolute_url())
        self.assertContains(response, "ادامه یادگیری")

    def test_a_guest_sees_no_progress_box_on_the_course_page(self):
        response = self.client.get(self.course.get_absolute_url())
        self.assertNotContains(response, "ادامه یادگیری")

    def test_the_video_resumes_from_the_saved_position(self):
        self.lesson_a.video_external_url = "https://cdn.example.test/a.mp4"
        self.lesson_a.save()
        save_position(self.student, self.lesson_a, 150)
        self.client.force_login(self.student)

        response = self.client.get(self.lesson_a.get_absolute_url())
        self.assertContains(response, 'data-resume-at="150"')
