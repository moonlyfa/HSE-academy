"""
تست‌های درگاه زرین‌پال.

هیچ درخواستی واقعاً به زرین‌پال نمی‌رود: `requests.post` جایگزین می‌شود و
پاسخ‌هایی که زرین‌پال در هر حالت برمی‌گرداند شبیه‌سازی می‌شوند. این تست‌ها
سه چیز را نگه می‌دارند:

۱. **مبلغ درست می‌رود** — با واحد صریح، و در verify همان عددی که در
   request رفت. اشتباه در این یکی یعنی یک‌دهم یا ده برابر پول.

۲. **فقط سرور درگاه تصمیم می‌گیرد** — شناسه و مبلغ verify از دیتابیس
   خودمان می‌آیند، نه از آدرس بازگشتی که کاربر می‌تواند دستکاری کند.

۳. **«نمی‌دانم» هیچ‌وقت «نه» ثبت نمی‌شود** — اگر پاسخ verify گم شود،
   تراکنش در انتظار می‌ماند و دوباره پرسیده می‌شود. وگرنه مشتری پول
   داده و چیزی نگرفته.
"""

from datetime import timedelta
from io import StringIO
from unittest.mock import MagicMock, patch

import requests
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.courses.models import Enrollment
from apps.orders.models import OrderStatus, Payment, PaymentStatus
from apps.orders.services import start_payment
from apps.orders.services.payment import ZarinPalGateway, get_payment_gateway, verify_payment
from apps.orders.tests_payment import PaymentTestMixin

MERCHANT = "00000000-0000-0000-0000-000000000000"

ZARINPAL = {
    "USE_MOCK_PAYMENT": False,
    "PAYMENT_PROVIDER": "zarinpal",
    "ZARINPAL_MERCHANT_ID": MERCHANT,
    "ZARINPAL_SANDBOX": True,
    "ZARINPAL_CURRENCY": "IRT",
}

POST = "apps.orders.services.payment.requests.post"


def zp_response(*, data=None, errors=None, status=200):
    """پاسخی به شکل پاسخ واقعی زرین‌پال."""
    response = MagicMock()
    response.status_code = status
    response.json.return_value = {
        "data": data if data is not None else [],
        "errors": errors if errors is not None else [],
    }
    return response


def request_ok(authority="A00000000000000000000000000000012345"):
    return zp_response(data={"code": 100, "message": "Success", "authority": authority})


def verify_ok(code=100, ref_id=201, card_pan="502229******5995"):
    return zp_response(data={"code": code, "ref_id": ref_id, "card_pan": card_pan})


def zp_error(code, message="error"):
    return zp_response(errors={"code": code, "message": message, "validations": []})


class GatewayConstructionTests(TestCase):
    @override_settings(**{**ZARINPAL, "ZARINPAL_MERCHANT_ID": ""})
    def test_missing_merchant_id_is_refused(self):
        with self.assertRaises(ValueError):
            ZarinPalGateway()

    @override_settings(**{**ZARINPAL, "ZARINPAL_CURRENCY": "USD"})
    def test_an_unknown_currency_is_refused(self):
        with self.assertRaises(ValueError):
            ZarinPalGateway()

    @override_settings(**ZARINPAL)
    def test_zarinpal_is_selected_when_mock_is_off(self):
        self.assertIsInstance(get_payment_gateway(), ZarinPalGateway)

    @override_settings(**ZARINPAL)
    def test_sandbox_uses_sandbox_addresses(self):
        gateway = ZarinPalGateway()

        self.assertIn("sandbox.zarinpal.com", gateway.api)
        self.assertIn("sandbox.zarinpal.com", gateway.startpay)

    @override_settings(**{**ZARINPAL, "ZARINPAL_SANDBOX": False})
    def test_production_uses_production_addresses(self):
        gateway = ZarinPalGateway()

        self.assertEqual(gateway.api, "https://api.zarinpal.com/pg/v4/payment")
        self.assertEqual(gateway.startpay, "https://www.zarinpal.com/pg/StartPay/")


@override_settings(**ZARINPAL)
class AmountTests(PaymentTestMixin, TestCase):
    """
    قیمت‌های سایت تومان است. واحد همیشه صریح فرستاده می‌شود؛ اگر به
    پیش‌فرض درگاه سپرده شود، اشتباهش یک‌دهم یا ده برابر مبلغ است.
    """

    def sent_body(self, post):
        return post.call_args.kwargs["json"]

    def test_toman_is_sent_as_is_with_its_unit(self):
        order = self.make_order()

        with patch(POST, return_value=request_ok()) as post:
            start_payment(order, "http://testserver/payments/callback/")

        body = self.sent_body(post)
        self.assertEqual(body["amount"], order.total)
        self.assertEqual(body["currency"], "IRT")

    @override_settings(ZARINPAL_CURRENCY="IRR")
    def test_rial_is_ten_times_toman(self):
        order = self.make_order()

        with patch(POST, return_value=request_ok()) as post:
            start_payment(order, "http://testserver/payments/callback/")

        body = self.sent_body(post)
        self.assertEqual(body["amount"], order.total * 10)
        self.assertEqual(body["currency"], "IRR")

    def test_verify_sends_the_same_amount_as_request_even_if_settings_change(self):
        """
        اگر مدیر وسط یک تراکنش واحد پول را عوض کند، verify نباید عدد
        دیگری بفرستد؛ زرین‌پال آن را «مبلغ نادرست» رد می‌کند.
        """
        order = self.make_order()
        with patch(POST, return_value=request_ok()):
            start_payment(order, "http://testserver/payments/callback/")
        payment = Payment.objects.get(order=order)

        with self.settings(ZARINPAL_CURRENCY="IRR"):
            with patch(POST, return_value=verify_ok()) as post:
                verify_payment(payment, {})

        self.assertEqual(self.sent_body(post)["amount"], order.total)


@override_settings(**ZARINPAL)
class RequestTests(PaymentTestMixin, TestCase):
    def setUp(self):
        self.order = self.make_order()
        self.callback = "http://testserver/payments/callback/"

    def test_success_sends_the_user_to_startpay(self):
        with patch(POST, return_value=request_ok("A0000TESTAUTHORITY")):
            result = start_payment(self.order, self.callback)

        self.assertTrue(result.success)
        self.assertEqual(
            result.redirect_url, "https://sandbox.zarinpal.com/pg/StartPay/A0000TESTAUTHORITY"
        )

        payment = Payment.objects.get(order=self.order)
        self.assertEqual(payment.authority, "A0000TESTAUTHORITY")
        self.assertEqual(payment.gateway, "zarinpal")
        self.assertEqual(payment.status, PaymentStatus.PENDING)

    def test_request_body_carries_the_callback_and_order(self):
        with patch(POST, return_value=request_ok()) as post:
            start_payment(self.order, self.callback)

        body = post.call_args.kwargs["json"]
        self.assertEqual(body["merchant_id"], MERCHANT)
        self.assertEqual(body["callback_url"], self.callback)
        self.assertEqual(body["metadata"]["order_id"], self.order.order_number)
        self.assertIn(self.order.order_number, body["description"])

    def test_request_goes_to_the_request_endpoint_with_a_timeout(self):
        with patch(POST, return_value=request_ok()) as post:
            start_payment(self.order, self.callback)

        self.assertTrue(post.call_args.args[0].endswith("/payment/request.json"))
        self.assertIn("timeout", post.call_args.kwargs)

    def test_merchant_problem_shows_a_generic_message(self):
        """خطای تنظیمات فروشگاه (-10) به مشتری ربطی ندارد."""
        with patch(POST, return_value=zp_error(-10, "merchant invalid")):
            result = start_payment(self.order, self.callback)

        self.assertFalse(result.success)
        self.assertEqual(result.error_code, "-10")
        self.assertIn("درگاه پرداخت در حال حاضر پاسخ نمی‌دهد", result.message)
        self.assertEqual(Payment.objects.get(order=self.order).status, PaymentStatus.FAILED)

    def test_network_error_does_not_crash(self):
        with patch(POST, side_effect=requests.ConnectionError("no route")):
            result = start_payment(self.order, self.callback)

        self.assertFalse(result.success)
        self.assertEqual(result.error_code, "network")

    def test_server_error_is_a_transport_error(self):
        with patch(POST, return_value=zp_response(status=502)):
            result = start_payment(self.order, self.callback)

        self.assertFalse(result.success)
        self.assertEqual(result.error_code, "network")

    def test_a_non_json_answer_is_a_transport_error(self):
        broken = MagicMock(status_code=200)
        broken.json.side_effect = ValueError("not json")

        with patch(POST, return_value=broken):
            result = start_payment(self.order, self.callback)

        self.assertFalse(result.success)
        self.assertEqual(result.error_code, "network")

    def test_success_code_without_an_authority_is_not_success(self):
        with patch(POST, return_value=zp_response(data={"code": 100})):
            result = start_payment(self.order, self.callback)

        self.assertFalse(result.success)


@override_settings(**ZARINPAL)
class VerifyTests(PaymentTestMixin, TestCase):
    def setUp(self):
        self.order = self.make_order()
        with patch(POST, return_value=request_ok("A0000REALAUTHORITY")):
            start_payment(self.order, "http://testserver/payments/callback/")
        self.payment = Payment.objects.get(order=self.order)

    def test_code_100_pays_the_order_and_opens_the_course(self):
        with patch(POST, return_value=verify_ok(ref_id=987654)):
            result = verify_payment(self.payment, {})

        self.assertTrue(result.success)
        self.payment.refresh_from_db()
        self.order.refresh_from_db()

        self.assertEqual(self.payment.status, PaymentStatus.SUCCESS)
        self.assertEqual(self.payment.ref_id, "987654")
        self.assertEqual(self.payment.card_pan, "5995")  # فقط چهار رقم آخر
        self.assertEqual(self.order.status, OrderStatus.PAID)
        self.assertTrue(Enrollment.objects.filter(user=self.user, course=self.course).exists())

    def test_code_101_already_verified_is_still_success(self):
        """
        101 یعنی «قبلاً تأیید شده». دقیقاً همان وقتی رخ می‌دهد که تأیید
        اول انجام شد ولی پاسخش به ما نرسید.
        """
        with patch(POST, return_value=verify_ok(code=101)):
            result = verify_payment(self.payment, {})

        self.assertTrue(result.success)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, OrderStatus.PAID)

    def test_authority_and_amount_come_from_our_database_not_the_callback(self):
        """کاربر آدرس بازگشت را با شناسه و مبلغ دیگری دستکاری کرده است."""
        forged = {"Authority": "A0000SOMEONE-ELSES", "Status": "OK", "amount": "1000"}

        with patch(POST, return_value=verify_ok()) as post:
            verify_payment(self.payment, forged)

        body = post.call_args.kwargs["json"]
        self.assertEqual(body["authority"], "A0000REALAUTHORITY")
        self.assertEqual(body["amount"], self.order.total)

    def test_cancelled_payment_tells_the_user_why(self):
        with patch(POST, return_value=zp_error(-51, "Session is not valid")):
            result = verify_payment(self.payment, {})

        self.assertFalse(result.success)
        self.assertIn("لغو شد", result.message)
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, PaymentStatus.FAILED)
        self.assertEqual(self.payment.error_code, "-51")

    def test_other_verify_errors_mention_the_automatic_refund(self):
        with patch(POST, return_value=zp_error(-54, "authority invalid")):
            result = verify_payment(self.payment, {})

        self.assertFalse(result.success)
        self.assertIn("۷۲ ساعت", result.message)

    def test_gateway_message_is_kept_for_support(self):
        with patch(POST, return_value=zp_error(-54, "Authority is invalid.")):
            verify_payment(self.payment, {})

        self.payment.refresh_from_db()
        self.assertEqual(self.payment.error_code, "-54")


@override_settings(**ZARINPAL)
class LostResponseTests(PaymentTestMixin, TestCase):
    """
    خطرناک‌ترین حالت پرداخت: verify فرستاده شد و پاسخش گم شد.

    شاید زرین‌پال تأیید کرده و پول کسر شده؛ شاید نه. ثبت «ناموفق» یعنی
    مشتری پول داده و چیزی نگرفته — و چون تأیید شده، شاپرک هم خودکار
    برنمی‌گرداند.
    """

    def setUp(self):
        self.order = self.make_order()
        with patch(POST, return_value=request_ok()):
            start_payment(self.order, "http://testserver/payments/callback/")
        self.payment = Payment.objects.get(order=self.order)

    def lose_the_response(self):
        with patch(POST, side_effect=requests.Timeout("read timed out")):
            return verify_payment(self.payment, {})

    def test_a_lost_response_leaves_the_payment_pending(self):
        result = self.lose_the_response()

        self.assertFalse(result.success)
        self.assertTrue(result.retryable)

        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, PaymentStatus.PENDING)
        self.assertEqual(self.payment.raw_response["verify_attempts"], 1)
        self.assertIn("last_verify_error", self.payment.raw_response)

        self.order.refresh_from_db()
        self.assertNotEqual(self.order.status, OrderStatus.PAID)

    def test_asking_again_later_opens_the_course(self):
        """زرین‌پال این بار 101 می‌گوید: تأیید قبلی رسیده بود."""
        self.lose_the_response()

        with patch(POST, return_value=verify_ok(code=101)):
            result = verify_payment(self.payment, {})

        self.assertTrue(result.success)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, OrderStatus.PAID)
        self.assertTrue(Enrollment.objects.filter(user=self.user, course=self.course).exists())

    def test_expiry_does_not_block_a_payment_we_already_asked_about(self):
        """
        قاعده انقضا برای تراکنشی است که هیچ‌وقت verify نشده (شاپرک خودکار
        برش می‌گرداند). تراکنشی که شاید تأیید شده، هر چقدر دیر، باید
        دوباره پرسیده شود.
        """
        self.lose_the_response()
        Payment.objects.filter(pk=self.payment.pk).update(
            created_at=timezone.now() - timedelta(hours=5)
        )
        self.payment.refresh_from_db()

        with patch(POST, return_value=verify_ok(code=101)):
            result = verify_payment(self.payment, {})

        self.assertTrue(result.success)

    def test_an_expired_payment_never_asked_about_is_closed_without_calling_the_gateway(self):
        """
        verify نکردن یعنی شاپرک پول را برمی‌گرداند. صدا زدن verify در این
        حالت، پرداختی را تأیید می‌کرد که دیگر نمی‌خواهیم بپذیریم.
        """
        Payment.objects.filter(pk=self.payment.pk).update(
            created_at=timezone.now() - timedelta(hours=5)
        )
        self.payment.refresh_from_db()

        with patch(POST) as post:
            result = verify_payment(self.payment, {})

        post.assert_not_called()
        self.assertFalse(result.success)
        self.assertIn("۷۲ ساعت", result.message)

    def test_the_result_page_does_not_offer_to_pay_again(self):
        """دکمه «پرداخت دوباره» در این حالت یعنی احتمال دو بار پول دادن."""
        self.client.force_login(self.user)

        with patch(POST, side_effect=requests.Timeout("read timed out")):
            response = self.client.get(
                reverse("orders:payment_callback"),
                {"Authority": self.payment.authority, "Status": "OK"},
            )

        self.assertContains(response, "در حال بررسی")
        self.assertContains(response, "دوباره پرداخت نکنید")
        self.assertNotContains(
            response, reverse("orders:payment_start", args=[self.order.order_number])
        )


@override_settings(**ZARINPAL)
class PendingPaymentsCommandTests(PaymentTestMixin, TestCase):
    """دستوری که هر ده دقیقه روی سرور اجرا می‌شود."""

    def start(self):
        order = self.make_order()
        with patch(POST, return_value=request_ok(f"A{order.pk:035d}")):
            start_payment(order, "http://testserver/payments/callback/")
        return Payment.objects.get(order=order)

    def run_command(self, *args) -> str:
        out = StringIO()
        call_command("verify_pending_payments", *args, stdout=out)
        return out.getvalue()

    def make_uncertain(self, payment):
        with patch(POST, side_effect=requests.Timeout("lost")):
            verify_payment(payment, {})

    def age(self, payment, hours):
        Payment.objects.filter(pk=payment.pk).update(
            created_at=timezone.now() - timedelta(hours=hours)
        )

    def test_an_uncertain_payment_is_resolved(self):
        payment = self.start()
        self.make_uncertain(payment)

        with patch(POST, return_value=verify_ok(code=101)):
            output = self.run_command()

        payment.refresh_from_db()
        self.assertEqual(payment.status, PaymentStatus.SUCCESS)
        self.assertIn("تأییدشده: 1", output)

    def test_an_abandoned_expired_payment_is_closed_without_asking(self):
        payment = self.start()
        self.age(payment, hours=2)

        with patch(POST) as post:
            self.run_command()

        post.assert_not_called()
        payment.refresh_from_db()
        self.assertEqual(payment.status, PaymentStatus.FAILED)
        self.assertEqual(payment.error_code, "expired")

    def test_a_payment_still_in_its_window_is_left_alone(self):
        """کاربر شاید همین حالا روی صفحه بانک باشد."""
        payment = self.start()

        with patch(POST) as post:
            output = self.run_command()

        post.assert_not_called()
        payment.refresh_from_db()
        self.assertEqual(payment.status, PaymentStatus.PENDING)
        self.assertIn("دست نخورد): 1", output)

    def test_a_still_unreachable_gateway_keeps_it_uncertain(self):
        payment = self.start()
        self.make_uncertain(payment)

        with patch(POST, side_effect=requests.Timeout("still lost")):
            output = self.run_command()

        payment.refresh_from_db()
        self.assertEqual(payment.status, PaymentStatus.PENDING)
        self.assertIn("هنوز نامعلوم: 1", output)

    def test_dry_run_changes_nothing(self):
        payment = self.start()
        self.make_uncertain(payment)

        with patch(POST) as post:
            output = self.run_command("--dry-run")

        post.assert_not_called()
        payment.refresh_from_db()
        self.assertEqual(payment.status, PaymentStatus.PENDING)
        self.assertIn("آزمایشی", output)
