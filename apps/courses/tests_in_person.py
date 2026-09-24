"""
دوره‌های حضوری و پنهان ماندن بخش آنلاین.

آکادمی فعلاً فقط دوره حضوری برگزار می‌کند. قاعده‌ها:

1. دوره غیرحضوری (آنلاین زنده، آفلاین، ترکیبی) **حذف نمی‌شود**؛ تا وقتی
   ONLINE_COURSES_ENABLED خاموش است فقط در سایت دیده نمی‌شود — نه در
   فهرست‌ها، نه صفحه‌اش، نه سبد خرید، نه نقشه سایت.
2. درس، ویدیو، جزوه و کلاس اسکای‌روم هم با همان کلید بسته‌اند؛ حتی برای
   کسی که آدرس را از قبل دارد یا ثبت‌نام کرده است.
3. ثبت‌نام در دوره حضوری از همان مسیر همیشگی سایت است: سبد خرید و پرداخت.
4. گذراندن دوره حضوری را آکادمی تأیید می‌کند (Enrollment.completed_at)؛
   آزمون و گواهی بدون هیچ تغییری از روی همین تأیید باز می‌شوند.

تست‌های قدیمی بخش آنلاین با `ONLINE_COURSES_ENABLED=True` اجرا می‌شوند تا
ثابت کنند زیرساخت آنلاین سالم مانده و با روشن شدن کلید برمی‌گردد.
"""

from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.certificates.issue import check_eligibility
from apps.certificates.models import Certificate
# Module import, not the class: a TestCase imported by name would be
# discovered and run a second time from this module.
from apps.core import tests_journey
from apps.exams.access import check_can_start
from apps.exams.models import Exam, ExamAttempt, Question, QuestionOption
from apps.orders.models import OrderStatus

from .enrollment import enroll
from .models import (
    Course,
    CourseCategory,
    CourseType,
    Enrollment,
    EnrollmentStatus,
    Lesson,
    OnlineSession,
    Section,
    offered_course_types,
)
from .progress import course_progress, learner_courses

User = get_user_model()

OFFLINE = override_settings(ONLINE_COURSES_ENABLED=False)
ONLINE = override_settings(ONLINE_COURSES_ENABLED=True)


class InPersonMixin:
    @classmethod
    def setUpTestData(cls):
        cls.category = CourseCategory.objects.create(name="ایمنی صنعتی", slug="safety")
        start = timezone.now().date() + timedelta(days=10)

        cls.in_person = Course.objects.create(
            title="ایمنی کار در ارتفاع حضوری",
            slug="height-in-person",
            category=cls.category,
            price=2_000_000,
            start_date=start,
            location="تهران، سالن آموزش آکادمی",
            capacity=25,
            is_published=True,
        )
        cls.online_live = Course.objects.create(
            title="دوره آنلاین زنده نمونه",
            slug="live-course",
            category=cls.category,
            course_type=CourseType.ONLINE_LIVE,
            price=1_000_000,
            start_date=start,
            is_published=True,
        )
        cls.recorded = Course.objects.create(
            title="دوره ضبط‌شده نمونه",
            slug="recorded-course",
            category=cls.category,
            course_type=CourseType.OFFLINE_RECORDED,
            price=0,
            is_published=True,
        )
        cls.hybrid = Course.objects.create(
            title="دوره ترکیبی نمونه",
            slug="hybrid-course",
            category=cls.category,
            course_type=CourseType.HYBRID,
            price=900_000,
            start_date=start,
            is_published=True,
        )

        section = Section.objects.create(course=cls.recorded, title="فصل اول")
        cls.lesson = Lesson.objects.create(
            section=section, title="درس اول", is_free_preview=True
        )
        cls.session = OnlineSession.objects.create(
            course=cls.online_live,
            title="جلسه اول",
            starts_at=timezone.now() - timedelta(minutes=5),
            duration_minutes=90,
            meeting_url="https://www.skyroom.online/ch/example/demo",
        )

        cls.student = User.objects.create_user(
            mobile="09121112233",
            password="HseTech!2026",
            first_name="سارا",
            last_name="محمدی",
            is_mobile_verified=True,
            is_identity_verified=True,
        )

    @property
    def hidden_courses(self):
        return (self.online_live, self.recorded, self.hybrid)


# ---------------------------------------------------------------------------
# ۱. پنهان، نه حذف
# ---------------------------------------------------------------------------


@OFFLINE
class HiddenOnlineCoursesTests(InPersonMixin, TestCase):
    def test_new_courses_default_to_in_person(self):
        course = Course(title="دوره تازه", slug="new", category=self.category)
        self.assertEqual(course.course_type, CourseType.IN_PERSON)

    def test_only_in_person_is_offered(self):
        self.assertEqual(offered_course_types(), [CourseType.IN_PERSON])
        self.assertEqual(
            list(Course.objects.published().values_list("slug", flat=True)),
            [self.in_person.slug],
        )

    def test_hidden_courses_are_still_in_the_database(self):
        # قول اصلی: هیچ‌چیز پاک نمی‌شود.
        for course in self.hidden_courses:
            self.assertTrue(Course.objects.filter(pk=course.pk, is_published=True).exists())
        self.assertTrue(Lesson.objects.filter(pk=self.lesson.pk).exists())
        self.assertTrue(OnlineSession.objects.filter(pk=self.session.pk).exists())

    def test_course_list_shows_only_in_person(self):
        response = self.client.get(reverse("courses:list"))
        self.assertContains(response, self.in_person.title)
        for course in self.hidden_courses:
            self.assertNotContains(response, course.title)

    def test_asking_for_an_online_type_in_the_url_finds_nothing(self):
        response = self.client.get(reverse("courses:list"), {"type": "online_live"})
        self.assertEqual(response.context["total_count"], 0)

    def test_type_filter_is_not_shown_when_there_is_only_one_type(self):
        response = self.client.get(reverse("courses:list"))
        self.assertEqual(response.context["course_types"], [(CourseType.IN_PERSON, "حضوری")])
        self.assertNotContains(response, 'name="type"')

    def test_hidden_course_page_is_404(self):
        for course in self.hidden_courses:
            with self.subTest(course=course.slug):
                self.assertEqual(
                    self.client.get(course.get_absolute_url()).status_code, 404
                )

    def test_hidden_course_is_not_on_home_search_calendar_or_sitemap(self):
        pages = [
            reverse("core:home"),
            reverse("core:calendar"),
            reverse("core:search") + "?q=دوره",
            "/sitemap.xml",
        ]
        for url in pages:
            response = self.client.get(url)
            for course in self.hidden_courses:
                with self.subTest(url=url, course=course.slug):
                    self.assertNotContains(response, course.slug)

    def test_category_count_ignores_hidden_courses(self):
        self.assertEqual(self.category.published_course_count, 1)

    def test_hidden_course_cannot_be_added_to_the_cart(self):
        self.client.force_login(self.student)
        response = self.client.post(reverse("orders:cart_add", args=[self.online_live.slug]))
        self.assertEqual(response.status_code, 404)
        self.assertFalse(self.client.session.get("cart"))

    def test_hidden_course_already_in_the_cart_drops_out(self):
        session = self.client.session
        session["cart"] = [self.online_live.pk, self.in_person.pk]
        session.save()
        response = self.client.get(reverse("orders:cart"))
        self.assertContains(response, self.in_person.title)
        self.assertNotContains(response, self.online_live.title)

    def test_hidden_course_is_not_open_for_registration(self):
        self.assertFalse(self.online_live.registration_open)
        self.assertTrue(self.in_person.registration_open)


@ONLINE
class SwitchingOnlineBackOnTests(InPersonMixin, TestCase):
    """روشن کردن کلید، همه‌چیز را همان‌طور که بود برمی‌گرداند."""

    def test_every_course_is_visible_again(self):
        response = self.client.get(reverse("courses:list"))
        for course in (self.in_person, *self.hidden_courses):
            self.assertContains(response, course.title)

    def test_type_filter_is_back(self):
        response = self.client.get(reverse("courses:list"))
        self.assertContains(response, 'name="type"')

    def test_lessons_and_sessions_open_again(self):
        self.assertEqual(self.client.get(self.lesson.get_absolute_url()).status_code, 200)

        enroll(self.student, self.online_live)
        self.client.force_login(self.student)
        response = self.client.get(
            reverse("courses:session_join", args=[self.online_live.slug, self.session.pk])
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn("skyroom", response["Location"])

    def test_in_person_course_still_has_no_online_content(self):
        # حتی با بخش آنلاین روشن، فصل‌هایی که مدیر برای دوره حضوری ساخته
        # باشد به صفحه درس راه ندارند.
        section = Section.objects.create(course=self.in_person, title="فصل")
        lesson = Lesson.objects.create(section=section, title="درس", is_free_preview=True)

        self.assertEqual(self.client.get(lesson.get_absolute_url()).status_code, 404)
        response = self.client.get(self.in_person.get_absolute_url())
        self.assertEqual(response.context["curriculum"], [])


# ---------------------------------------------------------------------------
# ۲. درس، ویدیو و کلاس آنلاین بسته‌اند
# ---------------------------------------------------------------------------


@OFFLINE
class OnlineContentClosedTests(InPersonMixin, TestCase):
    def setUp(self):
        cache.clear()
        enroll(self.student, self.recorded)
        enroll(self.student, self.online_live)
        self.client.force_login(self.student)

    def test_lesson_pages_and_files_are_404_even_for_enrolled_students(self):
        slug, pk = self.recorded.slug, self.lesson.pk
        urls = [
            reverse("courses:lesson", args=[slug, pk]),
            reverse("courses:lesson_video", args=[slug, pk]),
        ]
        for url in urls:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 404)

        for name in ("courses:lesson_complete", "courses:lesson_position"):
            with self.subTest(url=name):
                response = self.client.post(reverse(name, args=[slug, pk]), {"completed": "1"})
                self.assertEqual(response.status_code, 404)

    def test_online_class_join_is_404(self):
        response = self.client.get(
            reverse("courses:session_join", args=[self.online_live.slug, self.session.pk])
        )
        self.assertEqual(response.status_code, 404)

    def test_my_online_classes_page_is_404(self):
        self.assertEqual(self.client.get(reverse("courses:my_sessions")).status_code, 404)

    def test_staff_cannot_reach_lessons_either(self):
        admin = User.objects.create_superuser(mobile="09120000000", password="HseTech!2026")
        self.client.force_login(admin)
        self.assertEqual(self.client.get(self.lesson.get_absolute_url()).status_code, 404)

    def test_dashboard_has_no_online_class_menu_or_list(self):
        response = self.client.get(reverse("accounts:dashboard"))
        self.assertNotContains(response, reverse("courses:my_sessions"))
        self.assertNotContains(response, "کلاس‌های آنلاین")
        self.assertEqual(response.context["session_rows"], [])

    def test_footer_has_no_online_links(self):
        response = self.client.get(reverse("core:home"))
        self.assertNotContains(response, "?type=online_live")
        self.assertNotContains(response, "?type=offline_recorded")
        self.assertContains(response, "دوره‌های حضوری")

    def test_my_courses_hides_enrollments_in_hidden_courses(self):
        self.assertEqual(learner_courses(self.student), [])


# ---------------------------------------------------------------------------
# ۳. صفحه دوره حضوری و ثبت‌نام
# ---------------------------------------------------------------------------


@OFFLINE
class InPersonCoursePageTests(InPersonMixin, TestCase):
    def test_page_shows_in_person_details(self):
        response = self.client.get(self.in_person.get_absolute_url())
        self.assertContains(response, "حضوری")
        self.assertContains(response, self.in_person.location)
        self.assertContains(response, "ثبت‌نام شما در این دوره حضوری قطعی می‌شود")
        # «مدت دسترسی» مال محتوای آنلاین است.
        self.assertNotContains(response, "مدت دسترسی")
        self.assertEqual(response.context["curriculum"], [])
        self.assertEqual(response.context["session_rows"], [])

    def test_mobile_register_button_stays_on_the_page(self):
        response = self.client.get(self.in_person.get_absolute_url())
        self.assertContains(response, 'href="#purchase"')

    def test_structured_data_says_onsite_with_a_place(self):
        response = self.client.get(self.in_person.get_absolute_url())
        self.assertContains(response, '"courseMode": "onsite"')
        self.assertContains(response, '"@type": "Place"')

    def test_free_in_person_course_enrolls_without_a_lesson_redirect(self):
        free = Course.objects.create(
            title="کمک‌های اولیه",
            slug="first-aid",
            category=self.category,
            price=0,
            is_published=True,
        )
        self.client.force_login(self.student)
        response = self.client.post(reverse("courses:enroll_free", args=[free.slug]))
        self.assertRedirects(response, free.get_absolute_url())
        self.assertTrue(Enrollment.objects.filter(user=self.student, course=free).exists())

    def test_my_courses_row_shows_status_instead_of_a_progress_bar(self):
        enroll(self.student, self.in_person)
        self.client.force_login(self.student)
        response = self.client.get(reverse("accounts:my_courses"))
        self.assertContains(response, self.in_person.title)
        self.assertContains(response, "دوره حضوری")
        self.assertNotContains(response, "از ۱ درس")


# ---------------------------------------------------------------------------
# ۴. گذراندن دوره، آزمون و گواهی
# ---------------------------------------------------------------------------


@OFFLINE
class InPersonCompletionTests(InPersonMixin, TestCase):
    def setUp(self):
        self.enrollment = enroll(self.student, self.in_person)

    def confirm(self):
        self.enrollment.completed_at = timezone.now()
        self.enrollment.save(update_fields=["completed_at"])

    def test_progress_is_one_step_that_the_academy_confirms(self):
        progress = course_progress(self.student, self.in_person)
        self.assertEqual((progress.completed, progress.total), (0, 1))
        self.assertFalse(progress.is_finished)
        self.assertIsNone(progress.resume_lesson)

        self.confirm()
        self.assertTrue(course_progress(self.student, self.in_person).is_finished)

    def test_confirmation_on_a_suspended_enrollment_does_not_count(self):
        self.confirm()
        self.enrollment.status = EnrollmentStatus.SUSPENDED
        self.enrollment.save(update_fields=["status"])
        self.assertFalse(course_progress(self.student, self.in_person).is_finished)

    def test_certificate_waits_for_the_academy_confirmation(self):
        result = check_eligibility(self.student, self.in_person)
        self.assertEqual(result.reason, "course_not_completed")
        self.assertIn("کلاس حضوری", result.message)
        # قدم بعدی در دست دانشجو نیست؛ دکمه‌ای هم نشان داده نمی‌شود.
        self.assertEqual(result.action_url, "")

        self.confirm()
        self.assertTrue(check_eligibility(self.student, self.in_person).allowed)

    def test_exam_still_decides_the_certificate(self):
        exam = Exam.objects.create(course=self.in_person, pass_score=60, is_published=True)
        question = Question.objects.create(exam=exam, text="سؤال")
        QuestionOption.objects.create(question=question, text="درست", is_correct=True)
        self.confirm()

        self.assertEqual(
            check_eligibility(self.student, self.in_person).reason, "exam_not_passed"
        )

    def test_exam_requiring_completion_opens_after_confirmation(self):
        exam = Exam.objects.create(
            course=self.in_person,
            pass_score=60,
            is_published=True,
            require_course_completion=True,
        )
        question = Question.objects.create(exam=exam, text="سؤال")
        QuestionOption.objects.create(question=question, text="درست", is_correct=True)

        blocked = check_can_start(self.student, exam)
        self.assertFalse(blocked.allowed)
        self.assertIn("کلاس حضوری", blocked.message)

        self.confirm()
        self.assertTrue(check_can_start(self.student, exam).allowed)

    def test_dashboard_counts_certificates_instead_of_minutes(self):
        self.client.force_login(self.student)
        response = self.client.get(reverse("accounts:dashboard"))
        self.assertContains(response, "گواهی صادرشده")
        self.assertNotContains(response, "دقیقه آموزش")


# ---------------------------------------------------------------------------
# ۵. پنل مدیریت
# ---------------------------------------------------------------------------


class AdminTests(InPersonMixin, TestCase):
    def setUp(self):
        cache.clear()
        self.admin = User.objects.create_superuser(
            mobile="09120000000", password="HseTech!2026"
        )
        self.client.force_login(self.admin)

    @OFFLINE
    def test_confirm_completion_action(self):
        first = enroll(self.student, self.in_person)
        other = User.objects.create_user(mobile="09129998877")
        earlier = timezone.now() - timedelta(days=3)
        second = enroll(other, self.in_person)
        second.completed_at = earlier
        second.save(update_fields=["completed_at"])

        self.client.post(
            reverse("admin:courses_enrollment_changelist"),
            {"action": "mark_completed", "_selected_action": [first.pk, second.pk]},
        )
        first.refresh_from_db()
        second.refresh_from_db()
        self.assertIsNotNone(first.completed_at)
        # تأیید قبلی و تاریخش دست نمی‌خورد.
        self.assertEqual(second.completed_at, earlier)

        self.client.post(
            reverse("admin:courses_enrollment_changelist"),
            {"action": "unmark_completed", "_selected_action": [first.pk]},
        )
        first.refresh_from_db()
        self.assertIsNone(first.completed_at)

    @OFFLINE
    def test_online_only_sections_are_hidden_from_the_admin_index(self):
        response = self.client.get(reverse("admin:index"))
        for name in ("onlinesession", "lesson", "section", "lessonprogress"):
            with self.subTest(model=name):
                self.assertNotContains(response, f"/courses/{name}/")
        self.assertContains(response, "/courses/course/")
        self.assertContains(response, "/courses/enrollment/")

    @ONLINE
    def test_online_sections_come_back_with_the_switch(self):
        response = self.client.get(reverse("admin:index"))
        self.assertContains(response, "/courses/onlinesession/")
        self.assertContains(response, "/courses/lesson/")

    @OFFLINE
    def test_course_list_says_which_courses_are_hidden(self):
        response = self.client.get(reverse("admin:courses_course_changelist"))
        self.assertContains(response, "پنهان (غیرحضوری)")
        self.assertContains(response, "دیده می‌شود")

    @OFFLINE
    def test_hidden_online_course_is_still_editable(self):
        response = self.client.get(
            reverse("admin:courses_course_change", args=[self.online_live.pk])
        )
        self.assertEqual(response.status_code, 200)


# ---------------------------------------------------------------------------
# ۶. مسیر کامل: از ثبت‌نام در سایت تا گواهی دوره حضوری
# ---------------------------------------------------------------------------


@OFFLINE
class InPersonJourneyTests(TestCase):
    """
    همان مسیر واقعی FullJourneyTests، برای دوره حضوری:

        ثبت‌نام در سایت → خرید و پرداخت → کلاس حضوری
        → تأیید آکادمی در پنل → آزمون → گواهی قابل استعلام
    """

    register = tests_journey.FullJourneyTests.register
    last_code = tests_journey.FullJourneyTests.last_code
    buy_course = tests_journey.FullJourneyTests.buy_course
    pass_exam = tests_journey.FullJourneyTests.pass_exam

    @classmethod
    def setUpTestData(cls):
        category = CourseCategory.objects.create(name="ایمنی صنعتی", slug="safety")
        cls.course = Course.objects.create(
            title="ایمنی کار در ارتفاع (حضوری)",
            slug="height-in-person",
            category=category,
            price=2_000_000,
            start_date=timezone.now().date() + timedelta(days=7),
            location="تهران",
            is_published=True,
        )
        cls.exam = Exam.objects.create(
            course=cls.course,
            pass_score=60,
            shuffle_questions=False,
            shuffle_options=False,
            is_published=True,
        )
        cls.question = Question.objects.create(exam=cls.exam, text="سؤال نمونه")
        QuestionOption.objects.create(
            question=cls.question, text="پاسخ درست", is_correct=True, order=0
        )
        QuestionOption.objects.create(question=cls.question, text="پاسخ نادرست", order=1)
        cls.admin = User.objects.create_superuser(
            mobile="09120000000", password="HseTech!2026"
        )

    def setUp(self):
        tests_journey.FullJourneyTests.setUp(self)

    def test_register_pay_attend_and_get_a_verifiable_certificate(self):
        from apps.certificates.issue import check_eligibility as eligibility

        user = self.register()

        # ثبت‌نام در دوره حضوری، از خود سایت.
        order = self.buy_course()
        self.assertEqual(order.status, OrderStatus.PAID)
        enrollment = Enrollment.objects.get(user=user, course=self.course)

        # پیش از برگزاری کلاس، گواهی صادر نمی‌شود.
        self.client.post(reverse("certificates:issue", args=[self.course.slug]))
        self.assertFalse(Certificate.objects.exists())
        self.assertEqual(eligibility(user, self.course).reason, "course_not_completed")

        # کلاس برگزار شد؛ مدیر گذراندن دوره را در پنل تأیید می‌کند.
        self.client.force_login(self.admin)
        self.client.post(
            reverse("admin:courses_enrollment_changelist"),
            {"action": "mark_completed", "_selected_action": [enrollment.pk]},
        )
        enrollment.refresh_from_db()
        self.assertIsNotNone(enrollment.completed_at)

        # دانشجو دوباره وارد می‌شود، آزمون می‌دهد و گواهی می‌گیرد.
        self.client.force_login(user)
        attempt = self.pass_exam()
        self.assertTrue(attempt.is_passed)

        self.client.post(reverse("certificates:issue", args=[self.course.slug]))
        certificate = Certificate.objects.get(user=user)
        self.assertEqual(certificate.holder_name, "سارا محمدی")

        self.client.logout()
        verification = self.client.get(
            reverse("core:certificate_verify"), {"code": certificate.certificate_code}
        )
        self.assertContains(verification, "این گواهی معتبر است")
        self.assertContains(verification, self.course.title)
        self.assertEqual(ExamAttempt.objects.filter(user__mobile=tests_journey.MOBILE).count(), 1)


class SeedDemoTests(TestCase):
    """داده نمونه: دوره‌های حضوری ساخته می‌شوند و دوره‌های آنلاین پاک نمی‌شوند."""

    @OFFLINE
    @override_settings(DEBUG=True)
    def test_seed_creates_in_person_courses_and_keeps_online_ones_hidden(self):
        from io import StringIO

        from django.core.management import call_command

        from apps.core.models import FAQ, Feature, HeroSlide

        with patch("apps.core.management.commands.seed_demo.Command._make_gradient_image") as img:
            from django.core.files.base import ContentFile

            img.return_value = ContentFile(b"x")
            call_command("seed_demo", stdout=StringIO())

        self.assertTrue(Course.objects.filter(course_type=CourseType.IN_PERSON).exists())
        self.assertTrue(Course.objects.exclude(course_type=CourseType.IN_PERSON).exists())
        self.assertFalse(
            Course.objects.published().exclude(course_type=CourseType.IN_PERSON).exists()
        )
        # محتوای تبلیغاتی آنلاین پاک نمی‌شود، فقط غیرفعال است.
        self.assertFalse(Feature.objects.get(title="کلاس آنلاین زنده").is_active)
        self.assertFalse(FAQ.objects.get(question="تفاوت دوره آنلاین و آفلاین چیست؟").is_active)
        self.assertFalse(HeroSlide.objects.get(title="کلاس‌های آنلاین زنده").is_active)
        # دوره حضوری درس آنلاین ندارد.
        self.assertFalse(
            Lesson.objects.filter(section__course__course_type=CourseType.IN_PERSON).exists()
        )
