"""
ظرفیت دوره.

قاعده‌ها (توضیح کامل در apps/courses/capacity.py):

- ثبت‌نام فعال صندلی دارد؛ ثبت‌نام تعلیق‌شده یا بازپرداخت‌شده نه.
- کسی که به درگاه رفته، تا پایان مهلت پرداخت صندلی‌اش نگه داشته می‌شود؛
  و اگر پرداختش نامعلوم مانده، حتی بعد از مهلت.
- وقتی کلاس پر است: دکمه ثبت‌نام نیست، سبد و تسویه و درگاه و ثبت‌نام
  رایگان همه رد می‌کنند.
- اما پرداختی که درگاه تأیید کرده هرگز رد نمی‌شود.
"""

from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.orders.models import Order, OrderStatus, Payment, PaymentStatus
from apps.orders.services import mark_order_paid

from .capacity import has_seat, seats_left, seats_taken
from .enrollment import enroll
from .models import Course, CourseCategory, Enrollment, EnrollmentStatus

User = get_user_model()


class CapacityMixin:
    @classmethod
    def setUpTestData(cls):
        category = CourseCategory.objects.create(name="ایمنی", slug="safety")
        cls.course = Course.objects.create(
            title="ایمنی کار در ارتفاع (حضوری)",
            slug="height",
            category=category,
            price=2_000_000,
            capacity=2,
            start_date=timezone.now().date() + timedelta(days=10),
            is_published=True,
        )
        cls.free_course = Course.objects.create(
            title="کمک‌های اولیه",
            slug="first-aid",
            category=category,
            price=0,
            capacity=1,
            is_published=True,
        )
        cls.unlimited = Course.objects.create(
            title="دوره بدون سقف",
            slug="unlimited",
            category=category,
            price=1_000_000,
            is_published=True,
        )
        cls.users = [
            User.objects.create_user(mobile=f"0912000000{index}", password="HseTech!2026")
            for index in range(5)
        ]

    def setUp(self):
        cache.clear()

    def fill(self, course=None, count=None):
        course = course or self.course
        for user in self.users[: count if count is not None else course.capacity]:
            enroll(user, course)

    def start_paying(self, user, course=None):
        """سبد ← تسویه ← رفتن به درگاه (آزمایشی)."""
        course = course or self.course
        self.client.force_login(user)
        self.client.post(reverse("orders:cart_add", args=[course.slug]))
        self.client.post(reverse("orders:checkout"))
        order = Order.objects.filter(user=user).latest("created_at")
        self.client.post(reverse("orders:payment_start", args=[order.order_number]))
        return order


class SeatCountingTests(CapacityMixin, TestCase):
    def test_no_capacity_means_unlimited(self):
        self.assertIsNone(seats_left(self.unlimited))
        self.assertTrue(has_seat(self.unlimited, self.users[0]))

    def test_active_enrollments_take_seats(self):
        enroll(self.users[0], self.course)
        self.assertEqual(seats_taken(self.course), 1)
        self.assertEqual(seats_left(self.course), 1)

    def test_suspended_or_refunded_enrollments_free_their_seat(self):
        self.fill()
        Enrollment.objects.filter(user=self.users[0]).update(status=EnrollmentStatus.SUSPENDED)
        Enrollment.objects.filter(user=self.users[1]).update(status=EnrollmentStatus.REFUNDED)
        self.assertEqual(seats_left(self.course), 2)

    def test_a_student_already_holding_a_seat_is_never_full(self):
        self.fill()
        self.assertTrue(has_seat(self.course, self.users[0]))
        self.assertFalse(has_seat(self.course, self.users[4]))

    def test_payment_in_progress_holds_a_seat(self):
        self.start_paying(self.users[0])
        self.assertEqual(Payment.objects.count(), 1)
        self.assertEqual(seats_taken(self.course), 1)

    def test_expired_payment_releases_the_seat(self):
        self.start_paying(self.users[0])
        Payment.objects.update(created_at=timezone.now() - timedelta(hours=1))
        self.assertEqual(seats_taken(self.course), 0)

    def test_uncertain_payment_keeps_the_seat_after_expiry(self):
        # پاسخ تأیید درگاه گم شده؛ شاید پول کسر شده باشد.
        self.start_paying(self.users[0])
        Payment.objects.update(
            created_at=timezone.now() - timedelta(hours=1),
            raw_response={"verify_attempts": 1},
        )
        self.assertEqual(seats_taken(self.course), 1)

    def test_canceled_order_releases_the_seat(self):
        order = self.start_paying(self.users[0])
        Order.objects.filter(pk=order.pk).update(status=OrderStatus.CANCELED)
        self.assertEqual(seats_taken(self.course), 0)


class FullCourseTests(CapacityMixin, TestCase):
    def test_course_page_says_full_and_offers_no_register_button(self):
        self.fill()
        self.client.force_login(self.users[4])
        response = self.client.get(self.course.get_absolute_url())

        self.assertContains(response, "ظرفیت این دوره تکمیل شده است")
        self.assertContains(response, "ظرفیت تکمیل است")
        self.assertNotContains(response, reverse("orders:cart_add", args=[self.course.slug]))

    def test_course_page_shows_remaining_seats(self):
        enroll(self.users[0], self.course)
        response = self.client.get(self.course.get_absolute_url())
        self.assertContains(response, "۱ جای خالی")

    def test_enrolled_student_still_sees_their_enrollment(self):
        self.fill()
        self.client.force_login(self.users[0])
        response = self.client.get(self.course.get_absolute_url())
        self.assertContains(response, "شما در این دوره ثبت‌نام کرده‌اید")
        self.assertNotContains(response, "ظرفیت این دوره تکمیل شده است")

    def test_cart_refuses_a_full_course(self):
        self.fill()
        self.client.force_login(self.users[4])
        self.client.post(reverse("orders:cart_add", args=[self.course.slug]))
        self.assertFalse(self.client.session.get("cart"))

    def test_checkout_drops_a_course_that_filled_up_meanwhile(self):
        self.client.force_login(self.users[4])
        self.client.post(reverse("orders:cart_add", args=[self.course.slug]))
        self.fill()

        response = self.client.post(reverse("orders:checkout"))
        self.assertRedirects(response, reverse("orders:cart"))
        self.assertFalse(Order.objects.filter(user=self.users[4]).exists())
        self.assertFalse(self.client.session.get("cart"))

    def test_gateway_is_not_opened_when_the_last_seat_is_taken(self):
        # دو نفر سفارش ساخته‌اند و فقط یک صندلی مانده. اولی به درگاه
        # می‌رود؛ دومی باید پیش از درگاه متوقف شود.
        self.fill(count=1)
        first, second = self.users[3], self.users[4]

        self.client.force_login(first)
        self.client.post(reverse("orders:cart_add", args=[self.course.slug]))
        self.client.post(reverse("orders:checkout"))
        self.client.force_login(second)
        self.client.post(reverse("orders:cart_add", args=[self.course.slug]))
        self.client.post(reverse("orders:checkout"))

        first_order = Order.objects.get(user=first)
        second_order = Order.objects.get(user=second)

        self.client.force_login(first)
        self.client.post(reverse("orders:payment_start", args=[first_order.order_number]))
        self.assertTrue(Payment.objects.filter(order=first_order).exists())

        self.client.force_login(second)
        response = self.client.post(
            reverse("orders:payment_start", args=[second_order.order_number]), follow=True
        )
        self.assertFalse(Payment.objects.filter(order=second_order).exists())
        self.assertContains(response, "ظرفیت دوره")
        self.assertContains(response, "مبلغی از حساب شما کسر نشده است")

    def test_a_student_can_retry_their_own_payment_when_the_class_is_full(self):
        self.fill(count=1)
        order = self.start_paying(self.users[4])
        # کلاس با صندلیِ نگه‌داشته‌شده برای همین کاربر پر است.
        self.assertEqual(seats_left(self.course), 0)

        self.client.post(reverse("orders:payment_start", args=[order.order_number]))
        self.assertEqual(Payment.objects.filter(order=order).count(), 2)

    def test_free_enrollment_refuses_a_full_course(self):
        self.fill(course=self.free_course)
        self.client.force_login(self.users[4])
        self.client.post(reverse("courses:enroll_free", args=[self.free_course.slug]))
        self.assertFalse(
            Enrollment.objects.filter(user=self.users[4], course=self.free_course).exists()
        )

    def test_zero_total_checkout_refuses_a_full_course(self):
        self.client.force_login(self.users[4])
        self.client.post(reverse("orders:cart_add", args=[self.free_course.slug]))
        self.fill(course=self.free_course)

        self.client.post(reverse("orders:checkout"))
        self.assertFalse(Order.objects.filter(user=self.users[4]).exists())
        self.assertFalse(
            Enrollment.objects.filter(user=self.users[4], course=self.free_course).exists()
        )

    def test_zero_total_checkout_rechecks_under_the_lock(self):
        # کلاس درست بین بررسی زودهنگام و ساخت سفارش پر می‌شود؛ بررسیِ زیر
        # قفل باید همین را بگیرد.
        self.client.force_login(self.users[4])
        self.client.post(reverse("orders:cart_add", args=[self.free_course.slug]))
        self.fill(course=self.free_course)

        with patch("apps.orders.views.full_courses", return_value=[]):
            self.client.post(reverse("orders:checkout"))

        self.assertFalse(Order.objects.filter(user=self.users[4]).exists())
        self.assertFalse(
            Enrollment.objects.filter(user=self.users[4], course=self.free_course).exists()
        )

    def test_unlimited_course_is_never_full(self):
        for user in self.users:
            enroll(user, self.unlimited)
        other = User.objects.create_user(mobile="09129999999")
        self.client.force_login(other)
        self.client.post(reverse("orders:cart_add", args=[self.unlimited.slug]))
        self.assertEqual(self.client.session.get("cart"), [self.unlimited.pk])


class ConfirmedPaymentTests(CapacityMixin, TestCase):
    def test_a_confirmed_payment_is_never_refused_for_capacity(self):
        # صندلی نگه داشته شده بود، اما مدیر در این فاصله دستی دو نفر اضافه
        # کرد. پول گرفته شده؛ ثبت‌نام باید انجام شود و فقط هشدار بماند.
        order = self.start_paying(self.users[4])
        self.fill()

        with self.assertLogs("hse.capacity", level="WARNING") as logs:
            mark_order_paid(order)

        self.assertTrue(
            Enrollment.objects.filter(
                user=self.users[4], course=self.course, status=EnrollmentStatus.ACTIVE
            ).exists()
        )
        self.assertIn("بیش از ظرفیت", logs.output[0])

    def test_paying_for_a_held_seat_completes_normally(self):
        order = self.start_paying(self.users[0])
        payment = Payment.objects.get(order=order)
        self.client.post(
            reverse("orders:mock_gateway", args=[payment.authority]), {"decision": "success"}
        )
        self.client.get(reverse("orders:payment_callback"), {"Authority": payment.authority})

        payment.refresh_from_db()
        self.assertEqual(payment.status, PaymentStatus.SUCCESS)
        # صندلیِ نگه‌داشته‌شده به ثبت‌نام تبدیل شد، نه اینکه دو بار شمرده شود.
        self.assertEqual(seats_taken(self.course), 1)


class AdminSeatsColumnTests(CapacityMixin, TestCase):
    def test_course_list_shows_seats(self):
        self.fill(count=1)
        admin = User.objects.create_superuser(mobile="09120000009", password="HseTech!2026")
        self.client.force_login(admin)
        response = self.client.get(reverse("admin:courses_course_changelist"))
        self.assertContains(response, "1 / 2")
        self.assertContains(response, "0 / نامحدود")
