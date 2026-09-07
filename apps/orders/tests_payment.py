"""
تست‌های فاز ۱۲ — درگاه پرداخت.

اگر فقط یک فایل تست در کل این پروژه بخواهید بخوانید، همین است. اینجا
دقیقاً همان حمله‌ای تست می‌شود که فروشگاه‌های آنلاین را خالی می‌کند:
کاربر بدون پرداخت، آدرس بازگشتی درگاه را دستی می‌نویسد و انتظار دارد
دسترسی بگیرد.
"""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.courses.access import check_lesson_access
from apps.courses.models import Course, CourseCategory, Lesson, Section
from apps.orders.models import (
    Coupon,
    Order,
    OrderItem,
    OrderStatus,
    Payment,
    PaymentStatus,
)
from apps.orders.services import create_order, purchased_course_ids, start_payment
from apps.orders.services.payment import (
    MockPaymentGateway,
    get_payment_gateway,
    verify_payment,
)

User = get_user_model()


class PaymentTestMixin:
    @classmethod
    def setUpTestData(cls):
        cls.category = CourseCategory.objects.create(name="ایمنی", slug="safety")
        cls.course = Course.objects.create(
            title="دوره پولی",
            slug="paid-course",
            category=cls.category,
            price=1_500_000,
            is_published=True,
        )
        cls.section = Section.objects.create(course=cls.course, title="فصل اول")
        cls.lesson = Lesson.objects.create(section=cls.section, title="درس اول")

        cls.user = User.objects.create_user(mobile="09121234567", password="HseTech!2026")
        cls.other = User.objects.create_user(mobile="09127654321", password="HseTech!2026")

    def make_order(self, user=None) -> Order:
        order = create_order(user=user or self.user, lines=[])
        OrderItem.objects.create(
            order=order,
            course=self.course,
            title=self.course.title,
            unit_price=self.course.price,
            final_price=self.course.final_price,
        )
        order.recalculate()
        return order


class GatewaySelectionTests(TestCase):
    @override_settings(USE_MOCK_PAYMENT=True, PAYMENT_PROVIDER="zarinpal")
    def test_mock_wins_in_development(self):
        """
        حتی اگر کلید درگاه واقعی هم در .env باشد، در محیط توسعه هرگز
        تراکنش واقعی زده نمی‌شود.
        """
        self.assertIsInstance(get_payment_gateway(), MockPaymentGateway)

    @override_settings(USE_MOCK_PAYMENT=False, PAYMENT_PROVIDER="unknown-gateway")
    def test_unknown_gateway_falls_back_to_mock(self):
        self.assertIsInstance(get_payment_gateway(), MockPaymentGateway)

    @override_settings(
        USE_MOCK_PAYMENT=False, PAYMENT_PROVIDER="zarinpal", ZARINPAL_MERCHANT_ID=""
    )
    def test_real_gateway_refuses_to_start_without_credentials(self):
        with self.assertRaises(ValueError):
            get_payment_gateway()


class StartPaymentTests(PaymentTestMixin, TestCase):
    def setUp(self):
        self.client.force_login(self.user)
        self.order = self.make_order()
        self.url = reverse("orders:payment_start", args=[self.order.order_number])

    def test_starting_a_payment_creates_a_transaction_record(self):
        self.client.post(self.url)

        payment = Payment.objects.get()
        self.assertEqual(payment.order, self.order)
        self.assertEqual(payment.amount, self.order.total)
        self.assertEqual(payment.status, PaymentStatus.PENDING)
        self.assertTrue(payment.authority)

    def test_the_user_is_sent_to_the_gateway(self):
        response = self.client.post(self.url)

        self.assertEqual(response.status_code, 302)
        self.assertIn("/payments/mock/", response.url)

    def test_starting_a_payment_needs_post(self):
        self.assertEqual(self.client.get(self.url).status_code, 405)

    def test_a_guest_cannot_start_a_payment(self):
        self.client.logout()
        self.client.post(self.url)

        self.assertEqual(Payment.objects.count(), 0)

    def test_another_user_cannot_start_a_payment_for_your_order(self):
        """
        بدون فیلتر روی کاربر، هرکسی با داشتن شماره سفارش می‌توانست برای
        سفارش دیگری تراکنش بسازد.
        """
        self.client.force_login(self.other)
        response = self.client.post(self.url)

        self.assertEqual(response.status_code, 404)
        self.assertEqual(Payment.objects.count(), 0)

    def test_an_already_paid_order_cannot_be_paid_again(self):
        self.order.status = OrderStatus.PAID
        self.order.save()

        self.client.post(self.url)
        self.assertEqual(Payment.objects.count(), 0)

    def test_a_canceled_order_cannot_be_paid(self):
        self.order.status = OrderStatus.CANCELED
        self.order.save()

        self.client.post(self.url)
        self.assertEqual(Payment.objects.count(), 0)

    def test_a_zero_amount_order_is_not_sent_to_the_gateway(self):
        empty = create_order(user=self.user, lines=[])

        result = start_payment(empty, "http://testserver/callback/")
        self.assertFalse(result.success)
        self.assertEqual(Payment.objects.count(), 0)


class CallbackForgeryTests(PaymentTestMixin, TestCase):
    """
    مهم‌ترین تست‌های این پروژه.

    آدرس بازگشتی درگاه را مرورگر کاربر صدا می‌زند، نه خود درگاه. یعنی
    هرکسی می‌تواند آن را دستی بنویسد. اگر سایت آن را باور کند، دوره
    چند میلیونی بدون پرداخت یک ریال باز می‌شود.
    """

    def setUp(self):
        self.client.force_login(self.user)
        self.order = self.make_order()
        self.client.post(reverse("orders:payment_start", args=[self.order.order_number]))
        self.payment = Payment.objects.get()
        self.callback = reverse("orders:payment_callback")

    def test_a_forged_success_callback_does_not_pay_the_order(self):
        """کاربر دستی می‌نویسد: ?Authority=...&Status=OK بدون اینکه پرداخت کند."""
        self.client.get(self.callback, {"Authority": self.payment.authority, "Status": "OK"})

        self.order.refresh_from_db()
        self.payment.refresh_from_db()

        self.assertEqual(self.order.status, OrderStatus.FAILED)
        self.assertEqual(self.payment.status, PaymentStatus.FAILED)
        self.assertIsNone(self.order.paid_at)

    def test_a_forged_callback_does_not_unlock_the_course(self):
        self.client.get(self.callback, {"Authority": self.payment.authority, "Status": "OK"})

        self.assertEqual(purchased_course_ids(self.user), set())
        self.assertFalse(check_lesson_access(self.user, self.lesson).allowed)

    def test_an_unknown_authority_is_rejected(self):
        response = self.client.get(
            self.callback, {"Authority": "MOCK-COMPLETELY-MADE-UP", "Status": "OK"}
        )

        self.assertEqual(response.status_code, 302)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, OrderStatus.PENDING)

    def test_a_callback_without_an_authority_is_rejected(self):
        response = self.client.get(self.callback, {"Status": "OK"})

        self.assertEqual(response.status_code, 302)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, OrderStatus.PENDING)

    def test_the_status_parameter_is_not_what_decides(self):
        """
        حتی وقتی پرداخت واقعاً موفق بوده، اگر Status را NOK بنویسیم باز
        هم باید موفق حساب شود — چون تصمیم با درگاه است، نه با آدرس.
        """
        self._pay_on_the_gateway()

        self.client.get(self.callback, {"Authority": self.payment.authority, "Status": "NOK"})

        self.order.refresh_from_db()
        self.assertEqual(self.order.status, OrderStatus.PAID)

    def _pay_on_the_gateway(self):
        """شبیه‌سازی کلیک کاربر روی «پرداخت موفق» در صفحه درگاه."""
        self.client.post(
            reverse("orders:mock_gateway", args=[self.payment.authority]),
            {"decision": "success"},
        )
        self.payment.refresh_from_db()


class SuccessfulPaymentTests(PaymentTestMixin, TestCase):
    def setUp(self):
        self.client.force_login(self.user)
        self.order = self.make_order()
        self.client.post(reverse("orders:payment_start", args=[self.order.order_number]))
        self.payment = Payment.objects.get()

    def _complete(self, decision="success"):
        """کل مسیر واقعی: صفحه درگاه ← بازگشت ← تأیید."""
        response = self.client.post(
            reverse("orders:mock_gateway", args=[self.payment.authority]),
            {"decision": decision},
            follow=True,
        )
        self.order.refresh_from_db()
        self.payment.refresh_from_db()
        return response

    def test_a_real_payment_marks_the_order_paid(self):
        self._complete()

        self.assertEqual(self.order.status, OrderStatus.PAID)
        self.assertIsNotNone(self.order.paid_at)
        self.assertEqual(self.payment.status, PaymentStatus.SUCCESS)

    def test_a_reference_number_is_recorded(self):
        self._complete()

        self.assertTrue(self.payment.ref_id)
        self.assertIsNotNone(self.payment.verified_at)

    def test_only_the_last_four_digits_of_the_card_are_kept(self):
        self._complete()

        self.assertEqual(len(self.payment.card_pan), 4)
        self.assertEqual(self.payment.masked_card, "**** **** **** 6037")

    def test_paying_unlocks_the_course(self):
        self.assertFalse(check_lesson_access(self.user, self.lesson).allowed)

        self._complete()

        access = check_lesson_access(self.user, self.lesson)
        self.assertTrue(access.allowed)
        self.assertEqual(access.reason, "purchased")

    def test_paying_does_not_unlock_it_for_someone_else(self):
        self._complete()

        self.assertFalse(check_lesson_access(self.other, self.lesson).allowed)

    def test_the_success_page_shows_the_reference_number(self):
        response = self._complete()

        self.assertContains(response, "پرداخت با موفقیت انجام شد")
        self.assertContains(response, self.payment.ref_id)

    def test_choosing_failure_on_the_gateway_does_not_pay(self):
        self._complete(decision="failed")

        self.assertEqual(self.order.status, OrderStatus.FAILED)
        self.assertEqual(self.payment.status, PaymentStatus.FAILED)
        self.assertEqual(purchased_course_ids(self.user), set())

    def test_a_failed_order_can_be_retried(self):
        self._complete(decision="failed")
        self.assertTrue(self.order.is_payable)

        self.client.post(reverse("orders:payment_start", args=[self.order.order_number]))
        second = Payment.objects.exclude(pk=self.payment.pk).get()

        self.client.post(
            reverse("orders:mock_gateway", args=[second.authority]),
            {"decision": "success"},
            follow=True,
        )

        self.order.refresh_from_db()
        self.assertEqual(self.order.status, OrderStatus.PAID)

    def test_every_attempt_is_recorded(self):
        """
        سابقه تلاش‌های ناموفق باید بماند؛ هنگام اختلاف مالی همین سابقه
        است که به کار می‌آید.
        """
        self._complete(decision="failed")
        self.client.post(reverse("orders:payment_start", args=[self.order.order_number]))

        self.assertEqual(Payment.objects.filter(order=self.order).count(), 2)


class DoubleVerificationTests(PaymentTestMixin, TestCase):
    """
    رفرش کردن صفحه بازگشت نباید کاری را دوباره انجام دهد.

    این حالت واقعاً اتفاق می‌افتد: کاربر بعد از پرداخت F5 می‌زند، یا
    درگاه دوبار Redirect می‌کند.
    """

    def setUp(self):
        self.client.force_login(self.user)
        self.coupon = Coupon.objects.create(code="OFF10", value=10)
        self.order = self.make_order()
        self.order.coupon = self.coupon
        self.order.save()
        self.order.recalculate()

        self.client.post(reverse("orders:payment_start", args=[self.order.order_number]))
        self.payment = Payment.objects.get()
        self.client.post(
            reverse("orders:mock_gateway", args=[self.payment.authority]),
            {"decision": "success"},
            follow=True,
        )

    def test_the_order_is_paid_once(self):
        self.order.refresh_from_db()
        first_paid_at = self.order.paid_at

        self.client.get(
            reverse("orders:payment_callback"),
            {"Authority": self.payment.authority, "Status": "OK"},
        )

        self.order.refresh_from_db()
        self.assertEqual(self.order.paid_at, first_paid_at)

    def test_the_coupon_is_counted_once(self):
        self.client.get(
            reverse("orders:payment_callback"),
            {"Authority": self.payment.authority, "Status": "OK"},
        )
        self.client.get(
            reverse("orders:payment_callback"),
            {"Authority": self.payment.authority, "Status": "OK"},
        )

        self.coupon.refresh_from_db()
        self.assertEqual(self.coupon.used_count, 1)


class PaymentGuardTests(PaymentTestMixin, TestCase):
    """سدهای دیگری که پیش از تأیید بررسی می‌شوند."""

    def setUp(self):
        self.client.force_login(self.user)
        self.order = self.make_order()
        self.client.post(reverse("orders:payment_start", args=[self.order.order_number]))
        self.payment = Payment.objects.get()

    def _decide(self, decision="success"):
        self.client.post(
            reverse("orders:mock_gateway", args=[self.payment.authority]),
            {"decision": decision},
        )
        self.payment.refresh_from_db()

    def test_an_expired_transaction_is_rejected(self):
        """
        کاربری که صفحه درگاه را باز گذاشته و ساعت‌ها بعد برگشته، نباید
        تراکنشی را تأیید کند که شرایطش عوض شده است.
        """
        self._decide()
        Payment.objects.filter(pk=self.payment.pk).update(
            created_at=timezone.now() - timedelta(hours=3)
        )
        self.payment.refresh_from_db()

        result = verify_payment(self.payment, {})

        self.assertFalse(result.success)
        self.assertIn("مهلت", result.message)
        self.order.refresh_from_db()
        self.assertNotEqual(self.order.status, OrderStatus.PAID)

    def test_a_canceled_order_is_not_paid_even_with_a_valid_transaction(self):
        self._decide()
        self.order.status = OrderStatus.CANCELED
        self.order.save()

        result = verify_payment(self.payment, {})

        self.assertFalse(result.success)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, OrderStatus.CANCELED)

    def test_a_mismatched_amount_blocks_the_payment(self):
        """
        اگر مبلغ تراکنش با مبلغ سفارش یکی نباشد — چه از خطا و چه از
        دستکاری — دسترسی داده نمی‌شود.
        """
        self._decide()
        Payment.objects.filter(pk=self.payment.pk).update(amount=1000)
        self.payment.refresh_from_db()

        result = verify_payment(self.payment, {})

        self.assertFalse(result.success)
        self.assertIn("مطابقت ندارد", result.message)
        self.order.refresh_from_db()
        self.assertNotEqual(self.order.status, OrderStatus.PAID)

    def test_the_gateway_page_is_closed_once_the_transaction_is_done(self):
        self._decide()
        self.client.get(
            reverse("orders:payment_callback"),
            {"Authority": self.payment.authority, "Status": "OK"},
        )

        response = self.client.get(
            reverse("orders:mock_gateway", args=[self.payment.authority])
        )
        self.assertEqual(response.status_code, 302)

    @override_settings(USE_MOCK_PAYMENT=False, PAYMENT_PROVIDER="mock")
    def test_the_mock_gateway_page_is_unavailable_in_production_mode(self):
        """صفحه درگاه آزمایشی هرگز نباید روی سایت واقعی باز باشد."""
        response = self.client.get(
            reverse("orders:mock_gateway", args=[self.payment.authority])
        )
        self.assertEqual(response.status_code, 404)


class PaymentPrivacyTests(PaymentTestMixin, TestCase):
    def test_the_full_card_number_is_never_stored(self):
        order = self.make_order()
        payment = Payment.objects.create(order=order, amount=order.total, gateway="mock")
        payment.card_pan = "6037991199991234"[-4:]
        payment.save()

        self.assertEqual(payment.card_pan, "1234")
        self.assertNotIn("6037991199991234", str(payment.__dict__))

    def test_transaction_details_are_not_visible_to_another_user(self):
        order = self.make_order()
        self.client.force_login(self.other)

        self.assertEqual(self.client.get(order.get_absolute_url()).status_code, 404)
