"""
تست‌های فاز ۱۴ — ثبت‌نام و مدیریت دسترسی.

ثبت‌نام تنها منبع حقیقت برای دسترسی است. اگر این تست‌ها بشکنند، یا کسی
به محتوایی می‌رسد که نباید، یا کسی که پول داده پشت در می‌ماند.
"""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.courses.access import check_lesson_access
from apps.courses.enrollment import (
    active_enrollment,
    enroll,
    enroll_from_order,
    expiry_for,
    has_access,
    revoke,
)
from apps.courses.models import (
    Course,
    CourseCategory,
    Enrollment,
    EnrollmentSource,
    EnrollmentStatus,
    Lesson,
    Section,
)
from apps.orders.models import OrderItem, OrderStatus
from apps.orders.services import create_order, mark_order_paid

User = get_user_model()


class EnrollmentTestMixin:
    @classmethod
    def setUpTestData(cls):
        cls.category = CourseCategory.objects.create(name="ایمنی", slug="safety")

        cls.lifetime_course = Course.objects.create(
            title="دوره دائمی",
            slug="lifetime",
            category=cls.category,
            price=1_000_000,
            is_published=True,
        )
        cls.timed_course = Course.objects.create(
            title="دوره مدت‌دار",
            slug="timed",
            category=cls.category,
            price=2_000_000,
            access_duration_days=30,
            is_published=True,
        )
        cls.free_course = Course.objects.create(
            title="دوره رایگان",
            slug="free",
            category=cls.category,
            price=0,
            is_published=True,
        )

        for course in (cls.lifetime_course, cls.timed_course, cls.free_course):
            section = Section.objects.create(course=course, title="فصل اول")
            Lesson.objects.create(section=section, title=f"درس {course.slug}")

        cls.lesson = Lesson.objects.get(section__course=cls.lifetime_course)
        cls.timed_lesson = Lesson.objects.get(section__course=cls.timed_course)
        cls.free_lesson = Lesson.objects.get(section__course=cls.free_course)

        cls.user = User.objects.create_user(mobile="09121234567", password="HseTech!2026")
        cls.other = User.objects.create_user(mobile="09127654321", password="HseTech!2026")


class EnrollmentBasicsTests(EnrollmentTestMixin, TestCase):
    def test_enrolling_creates_an_active_record(self):
        enrollment = enroll(self.user, self.lifetime_course)

        self.assertTrue(enrollment.is_active)
        self.assertEqual(enrollment.status, EnrollmentStatus.ACTIVE)
        self.assertIsNone(enrollment.expires_at)

    def test_a_timed_course_gets_an_expiry_date(self):
        enrollment = enroll(self.user, self.timed_course)

        self.assertIsNotNone(enrollment.expires_at)
        self.assertEqual(enrollment.days_remaining, 29)  # امروز روز اول است

    def test_a_course_without_a_duration_never_expires(self):
        self.assertIsNone(expiry_for(self.lifetime_course))

    def test_enrolling_twice_does_not_create_two_records(self):
        """
        یک کاربر در یک دوره یک دسترسی دارد. دو ردیف موازی یعنی معلوم
        نیست کدامشان ملاک است.
        """
        enroll(self.user, self.lifetime_course)
        enroll(self.user, self.lifetime_course)

        self.assertEqual(
            Enrollment.objects.filter(user=self.user, course=self.lifetime_course).count(),
            1,
        )

    def test_renewing_early_adds_to_the_remaining_time(self):
        """
        کاربری که زودتر تمدید می‌کند نباید روزهای باقی‌مانده‌اش را از
        دست بدهد؛ مدت تازه به انتهای دوره فعلی اضافه می‌شود.
        """
        first = enroll(self.user, self.timed_course)
        first_expiry = first.expires_at

        second = enroll(self.user, self.timed_course)

        self.assertGreater(second.expires_at, first_expiry)
        self.assertAlmostEqual(
            (second.expires_at - first_expiry).days, 30, delta=1
        )

    def test_renewing_after_expiry_starts_from_today(self):
        enrollment = enroll(self.user, self.timed_course)
        enrollment.expires_at = timezone.now() - timedelta(days=100)
        enrollment.save()

        renewed = enroll(self.user, self.timed_course)

        self.assertGreater(renewed.expires_at, timezone.now())
        self.assertEqual(renewed.days_remaining, 29)

    def test_the_source_is_recorded(self):
        enrollment = enroll(self.user, self.free_course, source=EnrollmentSource.FREE)
        self.assertEqual(enrollment.source, EnrollmentSource.FREE)


class EnrollmentExpiryTests(EnrollmentTestMixin, TestCase):
    def test_an_expired_enrollment_is_not_active(self):
        enrollment = enroll(self.user, self.timed_course)
        enrollment.expires_at = timezone.now() - timedelta(minutes=1)
        enrollment.save()

        self.assertFalse(enrollment.is_active)
        self.assertTrue(enrollment.is_expired)

    def test_expiry_is_computed_not_stored(self):
        """
        اگر انقضا در فیلد وضعیت ذخیره می‌شد، دسترسی تا اجرای بعدی یک
        دستور زمان‌بندی‌شده باز می‌ماند — یعنی ساعت‌ها بعد از پایان مهلت.
        """
        enrollment = enroll(self.user, self.timed_course)
        Enrollment.objects.filter(pk=enrollment.pk).update(
            expires_at=timezone.now() - timedelta(seconds=1)
        )
        enrollment.refresh_from_db()

        self.assertEqual(enrollment.status, EnrollmentStatus.ACTIVE)
        self.assertFalse(enrollment.is_active)
        self.assertIsNone(active_enrollment(self.user, self.timed_course))

    def test_days_remaining_is_none_for_lifetime_access(self):
        enrollment = enroll(self.user, self.lifetime_course)
        self.assertIsNone(enrollment.days_remaining)

    def test_expiring_soon_is_flagged_within_a_week(self):
        enrollment = enroll(self.user, self.timed_course)

        self.assertFalse(enrollment.is_expiring_soon)

        enrollment.expires_at = timezone.now() + timedelta(days=3)
        enrollment.save()
        self.assertTrue(enrollment.is_expiring_soon)

    def test_an_enrollment_that_has_not_started_gives_no_access(self):
        enrollment = enroll(self.user, self.lifetime_course)
        enrollment.starts_at = timezone.now() + timedelta(days=5)
        enrollment.save()

        self.assertFalse(enrollment.is_active)


class AccessThroughEnrollmentTests(EnrollmentTestMixin, TestCase):
    def test_without_an_enrollment_the_lesson_is_locked(self):
        access = check_lesson_access(self.user, self.lesson)

        self.assertFalse(access.allowed)
        self.assertEqual(access.reason, "purchase_required")

    def test_an_enrollment_opens_the_lesson(self):
        enroll(self.user, self.lifetime_course)

        access = check_lesson_access(self.user, self.lesson)
        self.assertTrue(access.allowed)
        self.assertEqual(access.reason, "enrolled")

    def test_one_users_enrollment_does_not_open_it_for_another(self):
        enroll(self.user, self.lifetime_course)

        self.assertFalse(check_lesson_access(self.other, self.lesson).allowed)

    def test_an_expired_enrollment_closes_the_lesson_again(self):
        enrollment = enroll(self.user, self.timed_course)
        self.assertTrue(check_lesson_access(self.user, self.timed_lesson).allowed)

        enrollment.expires_at = timezone.now() - timedelta(days=1)
        enrollment.save()

        access = check_lesson_access(self.user, self.timed_lesson)
        self.assertFalse(access.allowed)
        self.assertEqual(access.reason, "enrollment_expired")
        self.assertIn("مهلت دسترسی", access.message)

    def test_a_suspended_enrollment_says_so(self):
        enrollment = enroll(self.user, self.lifetime_course)
        revoke(enrollment)

        access = check_lesson_access(self.user, self.lesson)
        self.assertFalse(access.allowed)
        self.assertEqual(access.reason, "enrollment_suspended")

    def test_revoking_keeps_the_record(self):
        """حذف ثبت‌نام یعنی پاک کردن تاریخچه‌ای که ممکن است لازم شود."""
        enrollment = enroll(self.user, self.lifetime_course)
        revoke(enrollment, status=EnrollmentStatus.REFUNDED, note="بازگشت وجه")

        enrollment.refresh_from_db()
        self.assertEqual(enrollment.status, EnrollmentStatus.REFUNDED)
        self.assertEqual(Enrollment.objects.count(), 1)

    def test_free_previews_stay_open_without_an_enrollment(self):
        self.lesson.is_free_preview = True
        self.lesson.save()

        self.assertTrue(check_lesson_access(self.user, self.lesson).allowed)


class VipAccessTests(EnrollmentTestMixin, TestCase):
    def test_a_vip_user_reaches_courses_marked_for_vip(self):
        self.user.is_vip = True
        self.user.save()

        access = check_lesson_access(self.user, self.lesson)
        self.assertTrue(access.allowed)
        self.assertEqual(access.reason, "vip")

    def test_a_course_can_be_excluded_from_vip(self):
        self.user.is_vip = True
        self.user.save()
        self.lifetime_course.vip_access = False
        self.lifetime_course.save()

        self.assertFalse(check_lesson_access(self.user, self.lesson).allowed)

    def test_an_expired_vip_subscription_gives_nothing(self):
        self.user.is_vip = True
        self.user.vip_expires_at = timezone.now() - timedelta(days=1)
        self.user.save()

        self.assertFalse(has_access(self.user, self.lifetime_course))


class EnrollmentFromPaymentTests(EnrollmentTestMixin, TestCase):
    def _paid_order(self, course):
        order = create_order(user=self.user, lines=[])
        OrderItem.objects.create(
            order=order,
            course=course,
            title=course.title,
            unit_price=course.price,
            final_price=course.final_price,
        )
        order.recalculate()
        mark_order_paid(order)
        return order

    def test_paying_creates_the_enrollment(self):
        order = self._paid_order(self.lifetime_course)

        enrollment = Enrollment.objects.get(user=self.user, course=self.lifetime_course)
        self.assertEqual(enrollment.source, EnrollmentSource.PURCHASE)
        self.assertEqual(enrollment.order, order)
        self.assertTrue(enrollment.is_active)

    def test_the_courses_duration_is_applied_at_purchase(self):
        self._paid_order(self.timed_course)

        enrollment = Enrollment.objects.get(course=self.timed_course)
        self.assertIsNotNone(enrollment.expires_at)

    def test_an_unpaid_order_creates_nothing(self):
        order = create_order(user=self.user, lines=[])
        OrderItem.objects.create(
            order=order,
            course=self.lifetime_course,
            title=self.lifetime_course.title,
            unit_price=self.lifetime_course.price,
            final_price=self.lifetime_course.final_price,
        )

        self.assertEqual(enroll_from_order(order), [])
        self.assertEqual(Enrollment.objects.count(), 0)

    def test_an_order_with_several_courses_enrolls_in_all_of_them(self):
        order = create_order(user=self.user, lines=[])
        for course in (self.lifetime_course, self.timed_course):
            OrderItem.objects.create(
                order=order,
                course=course,
                title=course.title,
                unit_price=course.price,
                final_price=course.final_price,
            )
        order.recalculate()
        mark_order_paid(order)

        self.assertEqual(Enrollment.objects.filter(user=self.user).count(), 2)

    def test_paying_twice_does_not_duplicate_the_enrollment(self):
        self._paid_order(self.lifetime_course)
        self._paid_order(self.lifetime_course)

        self.assertEqual(
            Enrollment.objects.filter(user=self.user, course=self.lifetime_course).count(),
            1,
        )


class FreeCourseEnrollmentTests(EnrollmentTestMixin, TestCase):
    def setUp(self):
        self.client.force_login(self.user)
        self.url = reverse("courses:enroll_free", args=[self.free_course.slug])

    def test_enrolling_in_a_free_course(self):
        self.client.post(self.url)

        enrollment = Enrollment.objects.get(user=self.user, course=self.free_course)
        self.assertEqual(enrollment.source, EnrollmentSource.FREE)
        self.assertTrue(check_lesson_access(self.user, self.free_lesson).allowed)

    def test_it_sends_the_learner_straight_into_the_first_lesson(self):
        response = self.client.post(self.url)
        self.assertRedirects(response, self.free_lesson.get_absolute_url())

    def test_a_paid_course_cannot_be_taken_for_free(self):
        """مهم‌ترین تست این بخش: مسیر رایگان نباید در دوره پولی کار کند."""
        url = reverse("courses:enroll_free", args=[self.lifetime_course.slug])
        self.client.post(url)

        self.assertEqual(Enrollment.objects.count(), 0)
        self.assertFalse(check_lesson_access(self.user, self.lesson).allowed)

    def test_a_guest_cannot_enroll(self):
        self.client.logout()
        self.client.post(self.url)

        self.assertEqual(Enrollment.objects.count(), 0)

    def test_enrolling_needs_post(self):
        self.assertEqual(self.client.get(self.url).status_code, 405)

    def test_a_closed_course_cannot_be_joined(self):
        self.free_course.start_date = timezone.now().date() - timedelta(days=10)
        self.free_course.save()

        self.client.post(self.url)
        self.assertEqual(Enrollment.objects.count(), 0)


class FreeOrderTests(EnrollmentTestMixin, TestCase):
    """
    سفارشی که مبلغش صفر است نباید به درگاه برود.

    پیش از فاز ۱۴ چنین سفارشی برای همیشه در حالت «در انتظار پرداخت»
    می‌ماند، چون درگاه مبلغ صفر را نمی‌پذیرد و هیچ راه دیگری هم برای
    تکمیلش نبود.
    """

    def setUp(self):
        self.client.force_login(self.user)
        self.client.post(reverse("orders:cart_add", args=[self.free_course.slug]))

    def test_a_zero_total_order_completes_without_a_gateway(self):
        self.client.post(reverse("orders:checkout"))

        from apps.orders.models import Order

        order = Order.objects.get()
        self.assertEqual(order.status, OrderStatus.PAID)
        self.assertIsNotNone(order.paid_at)

    def test_it_also_creates_the_enrollment(self):
        self.client.post(reverse("orders:checkout"))

        self.assertTrue(
            Enrollment.objects.filter(user=self.user, course=self.free_course).exists()
        )
        self.assertTrue(check_lesson_access(self.user, self.free_lesson).allowed)


class CoursePageEnrollmentTests(EnrollmentTestMixin, TestCase):
    def test_a_free_course_offers_a_one_click_enrollment(self):
        self.client.force_login(self.user)

        response = self.client.get(self.free_course.get_absolute_url())
        self.assertContains(response, "ثبت‌نام رایگان و شروع دوره")

    def test_an_enrolled_learner_sees_a_continue_button(self):
        self.client.force_login(self.user)
        enroll(self.user, self.lifetime_course)

        response = self.client.get(self.lifetime_course.get_absolute_url())
        self.assertContains(response, "شما در این دوره ثبت‌نام کرده‌اید")
        self.assertNotContains(response, "افزودن به سبد خرید")

    def test_the_remaining_days_are_shown_for_timed_access(self):
        self.client.force_login(self.user)
        enroll(self.user, self.timed_course)

        response = self.client.get(self.timed_course.get_absolute_url())
        self.assertContains(response, "روز باقی مانده")

    def test_the_access_duration_is_shown_before_buying(self):
        response = self.client.get(self.timed_course.get_absolute_url())

        self.assertContains(response, "مدت دسترسی")
        self.assertContains(response, "۳۰ روز")

    def test_lifetime_access_is_stated_explicitly(self):
        response = self.client.get(self.lifetime_course.get_absolute_url())
        self.assertContains(response, "دائمی")
