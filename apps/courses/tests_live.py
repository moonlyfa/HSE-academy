"""
تست‌های فاز ۱۵ — کلاس آنلاین و لینک ورود.

جمله‌ای که این تست‌ها از آن محافظت می‌کنند:
**لینک کلاس فقط به کسی می‌رسد که در دوره ثبت‌نام فعال دارد.**

اگر یکی از این تست‌ها بشکند، یا کسی بدون خرید وارد کلاس زنده می‌شود، یا
دانشجویی که پول داده پشت در می‌ماند.
"""

from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.courses.access import check_session_access
from apps.courses.enrollment import enroll, revoke
from apps.courses.live import upcoming_session_rows, user_sessions
from apps.courses.models import (
    Course,
    CourseCategory,
    EnrollmentSource,
    Lesson,
    LessonType,
    OnlineSession,
    OnlineSessionStatus,
    Section,
)
from apps.courses.services import (
    JoinLink,
    ManualLinkProvider,
    SkyroomApiProvider,
    get_skyroom_service,
)

User = get_user_model()

MEETING_URL = "https://www.skyroom.online/ch/hse/class-1"


class LiveTestMixin:
    @classmethod
    def setUpTestData(cls):
        cls.category = CourseCategory.objects.create(name="ایمنی", slug="safety")
        cls.course = Course.objects.create(
            title="دوره آنلاین",
            slug="online-course",
            category=cls.category,
            price=2_000_000,
            is_published=True,
        )
        cls.student = User.objects.create_user(
            mobile="09121234567", password="HseTech!2026"
        )
        cls.stranger = User.objects.create_user(
            mobile="09127654321", password="HseTech!2026"
        )
        cls.staff = User.objects.create_user(
            mobile="09120000000", password="HseTech!2026", is_staff=True
        )

    def make_session(self, *, minutes_from_now=0, duration=90, **kwargs):
        """یک جلسه که به‌صورت پیش‌فرض همین حالا در جریان است."""
        defaults = {
            "course": self.course,
            "title": "جلسه نمونه",
            "starts_at": timezone.now() + timedelta(minutes=minutes_from_now),
            "duration_minutes": duration,
            "meeting_url": MEETING_URL,
        }
        defaults.update(kwargs)
        return OnlineSession.objects.create(**defaults)


class OnlineSessionModelTests(LiveTestMixin, TestCase):
    """زمان‌بندی جلسه: کِی باز است، کِی تمام شده، کِی هنوز نرسیده."""

    def test_ends_at_is_derived_from_start_and_duration(self):
        session = self.make_session(minutes_from_now=60, duration=45)
        self.assertEqual(session.ends_at, session.starts_at + timedelta(minutes=45))

    def test_ends_at_follows_a_changed_start_time(self):
        session = self.make_session(minutes_from_now=60, duration=45)
        session.starts_at = session.starts_at + timedelta(days=1)
        session.save()
        session.refresh_from_db()
        self.assertEqual(session.ends_at, session.starts_at + timedelta(minutes=45))

    def test_running_session_is_joinable(self):
        session = self.make_session(minutes_from_now=-10)
        self.assertTrue(session.is_running)
        self.assertTrue(session.is_joinable)
        self.assertEqual(session.state, "live")

    def test_link_opens_shortly_before_the_class(self):
        # ۲۰ دقیقه مانده به شروع، یعنی داخل پنجره ۳۰ دقیقه‌ای ورود.
        self.assertTrue(self.make_session(minutes_from_now=20).is_running)
        # دو ساعت مانده، هنوز زود است.
        early = self.make_session(minutes_from_now=120)
        self.assertTrue(early.is_upcoming)
        self.assertFalse(early.is_running)

    def test_finished_session_is_not_joinable(self):
        session = self.make_session(minutes_from_now=-300, duration=60)
        self.assertTrue(session.is_finished)
        self.assertFalse(session.is_joinable)
        self.assertEqual(session.state, "finished")

    def test_session_without_link_is_not_joinable(self):
        session = self.make_session(minutes_from_now=-10, meeting_url="")
        self.assertFalse(session.has_link)
        self.assertFalse(session.is_joinable)

    def test_cancelled_session_is_never_running(self):
        session = self.make_session(
            minutes_from_now=-10, status=OnlineSessionStatus.CANCELLED
        )
        self.assertFalse(session.is_running)
        self.assertEqual(session.state, "cancelled")

    def test_upcoming_and_past_querysets(self):
        running = self.make_session(minutes_from_now=-10)
        cancelled = self.make_session(
            minutes_from_now=60, status=OnlineSessionStatus.CANCELLED
        )
        future = self.make_session(minutes_from_now=1440)
        past = self.make_session(minutes_from_now=-600, duration=60)

        # جلسه لغوشده هم در فهرست پیش‌رو می‌ماند تا دانشجو دلیلش را ببیند.
        self.assertEqual(
            list(OnlineSession.objects.upcoming()), [running, cancelled, future]
        )
        self.assertIn(past, OnlineSession.objects.past())
        self.assertNotIn(cancelled, OnlineSession.objects.scheduled())

    def test_lesson_must_belong_to_the_same_course(self):
        from django.core.exceptions import ValidationError

        other_course = Course.objects.create(
            title="دوره دیگر", slug="other", category=self.category, is_published=True
        )
        section = Section.objects.create(course=other_course, title="فصل")
        lesson = Lesson.objects.create(
            section=section, title="درس", lesson_type=LessonType.LIVE
        )

        session = OnlineSession(
            course=self.course,
            title="جلسه",
            starts_at=timezone.now(),
            lesson=lesson,
        )
        with self.assertRaises(ValidationError):
            session.full_clean()


class SessionAccessTests(LiveTestMixin, TestCase):
    """قاعده اصلی فاز: چه کسی اجازه ورود دارد."""

    def test_enrolled_student_can_join_a_running_session(self):
        enroll(self.student, self.course, source=EnrollmentSource.PURCHASE)
        access = check_session_access(self.student, self.make_session(minutes_from_now=-5))
        self.assertTrue(access.allowed)

    def test_stranger_cannot_join(self):
        access = check_session_access(self.stranger, self.make_session(minutes_from_now=-5))
        self.assertFalse(access.allowed)
        self.assertEqual(access.reason, "purchase_required")

    def test_anonymous_cannot_join(self):
        from django.contrib.auth.models import AnonymousUser

        access = check_session_access(
            AnonymousUser(), self.make_session(minutes_from_now=-5)
        )
        self.assertFalse(access.allowed)

    def test_revoked_enrollment_cannot_join(self):
        enrollment = enroll(self.student, self.course)
        revoke(enrollment)
        access = check_session_access(self.student, self.make_session(minutes_from_now=-5))
        self.assertFalse(access.allowed)
        self.assertEqual(access.reason, "enrollment_suspended")

    def test_expired_enrollment_cannot_join(self):
        enrollment = enroll(self.student, self.course)
        enrollment.expires_at = timezone.now() - timedelta(days=1)
        enrollment.save(update_fields=["expires_at"])

        access = check_session_access(self.student, self.make_session(minutes_from_now=-5))
        self.assertFalse(access.allowed)
        self.assertEqual(access.reason, "enrollment_expired")

    def test_enrolled_student_cannot_join_too_early(self):
        enroll(self.student, self.course)
        access = check_session_access(
            self.student, self.make_session(minutes_from_now=300)
        )
        self.assertFalse(access.allowed)
        self.assertEqual(access.reason, "session_not_started")

    def test_enrolled_student_cannot_join_a_finished_session(self):
        enroll(self.student, self.course)
        access = check_session_access(
            self.student, self.make_session(minutes_from_now=-600, duration=60)
        )
        self.assertFalse(access.allowed)
        self.assertEqual(access.reason, "session_finished")

    def test_cancelled_session_reports_its_reason(self):
        enroll(self.student, self.course)
        session = self.make_session(
            minutes_from_now=-5,
            status=OnlineSessionStatus.CANCELLED,
            cancel_reason="به‌دلیل قطعی برق لغو شد.",
        )
        access = check_session_access(self.student, session)
        self.assertFalse(access.allowed)
        self.assertEqual(access.message, "به‌دلیل قطعی برق لغو شد.")

    def test_session_without_link_tells_the_student_why(self):
        enroll(self.student, self.course)
        access = check_session_access(
            self.student, self.make_session(minutes_from_now=-5, meeting_url="")
        )
        self.assertFalse(access.allowed)
        self.assertEqual(access.reason, "session_no_link")

    def test_staff_can_open_the_room_before_everyone_else(self):
        access = check_session_access(
            self.staff, self.make_session(minutes_from_now=600)
        )
        self.assertTrue(access.allowed)


class SessionJoinViewTests(LiveTestMixin, TestCase):
    """آدرس ورود: تنها راه رسیدن به لینک کلاس."""

    def join_url(self, session):
        return reverse(
            "courses:session_join",
            kwargs={"slug": self.course.slug, "pk": session.pk},
        )

    def test_enrolled_student_is_redirected_to_the_meeting(self):
        enroll(self.student, self.course)
        session = self.make_session(minutes_from_now=-5)
        self.client.force_login(self.student)

        response = self.client.get(self.join_url(session))

        self.assertRedirects(response, MEETING_URL, fetch_redirect_response=False)

    def test_stranger_is_sent_back_to_the_course_page(self):
        session = self.make_session(minutes_from_now=-5)
        self.client.force_login(self.stranger)

        response = self.client.get(self.join_url(session))

        self.assertRedirects(response, self.course.get_absolute_url())

    def test_anonymous_visitor_is_sent_to_login(self):
        session = self.make_session(minutes_from_now=-5)
        response = self.client.get(self.join_url(session))
        self.assertIn(reverse("accounts:login"), response["Location"])

    def test_session_of_another_course_is_not_reachable_through_this_slug(self):
        """شناسه جلسه یک دوره، زیر آدرس دوره‌ای دیگر کار نمی‌کند."""
        other = Course.objects.create(
            title="دوره ارزان", slug="cheap", category=self.category, is_published=True
        )
        enroll(self.student, other)
        session = self.make_session(minutes_from_now=-5)
        self.client.force_login(self.student)

        response = self.client.get(
            reverse(
                "courses:session_join",
                kwargs={"slug": other.slug, "pk": session.pk},
            )
        )

        self.assertEqual(response.status_code, 404)

    def test_meeting_url_never_appears_in_the_course_page(self):
        """لینک کلاس نباید در HTML صفحه باشد — حتی برای دانشجوی مجاز."""
        enroll(self.student, self.course)
        self.make_session(minutes_from_now=-5)
        self.client.force_login(self.student)

        response = self.client.get(self.course.get_absolute_url())

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, MEETING_URL)
        self.assertContains(response, "ورود به کلاس")

    def test_course_page_shows_the_schedule_to_visitors_without_a_join_button(self):
        self.make_session(minutes_from_now=1440, title="جلسه دوم")

        response = self.client.get(self.course.get_absolute_url())

        self.assertContains(response, "جلسه دوم")
        self.assertNotContains(response, MEETING_URL)


class MySessionsPageTests(LiveTestMixin, TestCase):
    """صفحه «کلاس‌های آنلاین من» در داشبورد."""

    def test_page_requires_login(self):
        response = self.client.get(reverse("courses:my_sessions"))
        self.assertIn(reverse("accounts:login"), response["Location"])

    def test_only_sessions_of_enrolled_courses_are_listed(self):
        other = Course.objects.create(
            title="دوره دیگر", slug="other", category=self.category, is_published=True
        )
        OnlineSession.objects.create(
            course=other,
            title="کلاس دوره دیگر",
            starts_at=timezone.now() + timedelta(days=1),
            meeting_url=MEETING_URL,
        )
        self.make_session(minutes_from_now=1440, title="کلاس دوره من")
        enroll(self.student, self.course)
        self.client.force_login(self.student)

        response = self.client.get(reverse("courses:my_sessions"))

        self.assertContains(response, "کلاس دوره من")
        self.assertNotContains(response, "کلاس دوره دیگر")

    def test_upcoming_rows_are_limited_and_ordered(self):
        enroll(self.student, self.course)
        self.make_session(minutes_from_now=4320, title="سوم")
        self.make_session(minutes_from_now=1440, title="اول")
        self.make_session(minutes_from_now=2880, title="دوم")

        rows = upcoming_session_rows(self.student, limit=2)

        self.assertEqual([row["session"].title for row in rows], ["اول", "دوم"])

    def test_sessions_of_a_revoked_enrollment_disappear(self):
        enrollment = enroll(self.student, self.course)
        self.make_session(minutes_from_now=1440)
        revoke(enrollment)

        self.assertEqual(user_sessions(self.student).count(), 0)


class SkyroomServiceTests(LiveTestMixin, TestCase):
    """لایه سرویس: تعویض حالت دستی و API نباید به بقیه پروژه دست بزند."""

    def test_manual_provider_is_the_default(self):
        self.assertIsInstance(get_skyroom_service(), ManualLinkProvider)

    def test_manual_provider_returns_the_stored_link(self):
        link = ManualLinkProvider().join_link(
            self.make_session(minutes_from_now=-5), self.student
        )
        self.assertTrue(link.success)
        self.assertEqual(link.url, MEETING_URL)

    def test_manual_provider_fails_clearly_without_a_link(self):
        link = ManualLinkProvider().join_link(
            self.make_session(minutes_from_now=-5, meeting_url=""), self.student
        )
        self.assertFalse(link.success)
        self.assertIn("ثبت نشده", link.message)

    def test_unknown_provider_falls_back_to_manual(self):
        with self.settings(SKYROOM_PROVIDER="something-else"):
            self.assertIsInstance(get_skyroom_service(), ManualLinkProvider)

    def test_api_provider_without_a_key_falls_back_to_manual(self):
        with self.settings(SKYROOM_PROVIDER="skyroom", SKYROOM_API_KEY=""):
            self.assertIsInstance(get_skyroom_service(), ManualLinkProvider)

    def test_api_provider_builds_a_personal_link(self):
        session = self.make_session(minutes_from_now=-5, room_id="4242")

        with self.settings(SKYROOM_PROVIDER="skyroom", SKYROOM_API_KEY="key"):
            provider = get_skyroom_service()
            self.assertIsInstance(provider, SkyroomApiProvider)

            with patch("apps.courses.services.skyroom.requests.post") as post:
                post.return_value.json.return_value = {
                    "ok": True,
                    "result": "https://www.skyroom.online/login/abc123",
                }
                link = provider.join_link(session, self.student)

        self.assertTrue(link.success)
        self.assertEqual(link.url, "https://www.skyroom.online/login/abc123")

    def test_api_failure_falls_back_to_the_manual_link(self):
        """قطعی سرویس نباید کلاس را از دست دانشجو بگیرد."""
        session = self.make_session(minutes_from_now=-5, room_id="4242")

        with self.settings(SKYROOM_PROVIDER="skyroom", SKYROOM_API_KEY="key"):
            provider = get_skyroom_service()
            with patch("apps.courses.services.skyroom.requests.post") as post:
                post.return_value.json.return_value = {"ok": False, "error_code": 12}
                link = provider.join_link(session, self.student)

        self.assertTrue(link.success)
        self.assertEqual(link.url, MEETING_URL)

    def test_join_view_reports_a_service_failure_instead_of_a_broken_redirect(self):
        enroll(self.student, self.course)
        session = self.make_session(minutes_from_now=-5)
        self.client.force_login(self.student)

        with patch("apps.courses.views.get_skyroom_service") as service:
            service.return_value.join_link.return_value = JoinLink(
                False, message="سامانه کلاس در دسترس نیست."
            )
            response = self.client.get(
                reverse(
                    "courses:session_join",
                    kwargs={"slug": self.course.slug, "pk": session.pk},
                ),
                follow=True,
            )

        self.assertContains(response, "سامانه کلاس در دسترس نیست.")
