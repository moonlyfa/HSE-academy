"""
تست‌های پرداخت کارت به کارت.

دو قاعده‌ای که این تست‌ها نگهبانشان هستند:
۱. فرستادن عکس رسید هیچ دسترسی‌ای باز نمی‌کند؛ فقط تأیید مدیر.
۲. عکس رسید بعد از بررسی (تأیید یا رد) روی دیسک نمی‌ماند.
"""

import shutil
import tempfile
from io import BytesIO
from pathlib import Path
from unittest import mock

from django.contrib.auth.models import Permission
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from PIL import Image

from apps.core.models import SiteSetting
from apps.courses.capacity import seats_left
from apps.courses.models import Enrollment, EnrollmentStatus
from apps.orders.models import (
    CardTransfer,
    CardTransferReceipt,
    CardTransferStatus,
    OrderStatus,
    Payment,
    PaymentStatus,
)
from apps.orders.services import (
    approve_card_transfer,
    compress_receipt,
    reject_card_transfer,
    start_payment,
    submit_card_transfer,
)

from .tests_payment import PaymentTestMixin, User

TEMP_PROTECTED_ROOT = Path(tempfile.mkdtemp(prefix="hse-receipts-"))
SEND_SMS = "apps.orders.services.card_transfer._send_sms"


def image_bytes(fmt="PNG", size=(2400, 1200), color=(200, 30, 30)) -> bytes:
    buffer = BytesIO()
    Image.new("RGB", size, color).save(buffer, fmt)
    return buffer.getvalue()


def upload(name="receipt.png", content=None, content_type="image/png") -> SimpleUploadedFile:
    return SimpleUploadedFile(name, content or image_bytes(), content_type=content_type)


def receipt_files() -> list[Path]:
    folder = TEMP_PROTECTED_ROOT / "card-receipts"
    return list(folder.iterdir()) if folder.exists() else []


@override_settings(PROTECTED_MEDIA_ROOT=TEMP_PROTECTED_ROOT)
class CardTransferTestBase(PaymentTestMixin, TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(TEMP_PROTECTED_ROOT, ignore_errors=True)

    def setUp(self):
        shutil.rmtree(TEMP_PROTECTED_ROOT / "card-receipts", ignore_errors=True)
        site = SiteSetting.load()
        site.card_transfer_enabled = True
        site.card_transfer_number = "6037-9911-2233-4455"
        site.card_transfer_holder = "آکادمی HSE"
        site.card_transfer_notify_mobile = "09120000000"
        site.save()

        self.admin = User.objects.create_superuser(mobile="09350000000", password="HseTech!2026")
        self.order = self.make_order()
        sms = mock.patch(SEND_SMS)
        self.sms = sms.start()
        self.addCleanup(sms.stop)

    def submit(self, order=None, images=1) -> CardTransfer:
        result = submit_card_transfer(
            order or self.order,
            images=[compress_receipt(upload()) for _ in range(images)],
            payer_card_last4="1234",
            tracking_code="998877",
        )
        self.assertTrue(result.success, result.message)
        return result.transfer


class CompressReceiptTests(TestCase):
    def test_a_large_photo_is_shrunk_and_stored_as_jpeg(self):
        original = image_bytes("PNG", size=(3000, 1500))
        content = compress_receipt(upload(content=original))

        image = Image.open(BytesIO(content.read()))
        self.assertEqual(image.format, "JPEG")
        self.assertEqual(max(image.size), 1600)

    def test_transparent_png_is_accepted(self):
        buffer = BytesIO()
        Image.new("RGBA", (300, 300), (0, 0, 0, 0)).save(buffer, "PNG")
        compress_receipt(upload(content=buffer.getvalue()))

    def test_a_file_that_is_not_an_image_is_rejected(self):
        fake = upload("receipt.png", b"<?php echo 'hi'; ?>")
        with self.assertRaises(ValidationError):
            compress_receipt(fake)

    def test_unsupported_image_format_is_rejected(self):
        with self.assertRaises(ValidationError):
            compress_receipt(upload("r.gif", image_bytes("GIF"), "image/gif"))

    def test_location_data_is_removed(self):
        exif = Image.Exif()
        exif[0x010F] = "PhoneMaker"  # Make
        buffer = BytesIO()
        Image.new("RGB", (400, 400)).save(buffer, "JPEG", exif=exif)

        content = compress_receipt(upload("r.jpg", buffer.getvalue(), "image/jpeg"))

        self.assertFalse(dict(Image.open(BytesIO(content.read())).getexif()))


class CardTransferPageTests(CardTransferTestBase):
    def setUp(self):
        super().setUp()
        self.client.force_login(self.user)
        self.url = reverse("orders:card_transfer", args=[self.order.order_number])

    def test_the_page_shows_the_card_number_and_the_amount(self):
        response = self.client.get(self.url)

        self.assertContains(response, "6037 9911 2233 4455")
        self.assertContains(response, "آکادمی HSE")
        self.assertContains(response, 'enctype="multipart/form-data"')

    def test_the_order_page_offers_card_transfer(self):
        response = self.client.get(self.order.get_absolute_url())
        self.assertContains(response, self.url)

    def test_disabled_card_transfer_is_404_and_hidden(self):
        site = SiteSetting.load()
        site.card_transfer_enabled = False
        site.save()

        self.assertEqual(self.client.get(self.url).status_code, 404)
        self.assertNotContains(self.client.get(self.order.get_absolute_url()), self.url)

    def test_another_users_order_is_404(self):
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(self.url).status_code, 404)

    def test_guest_is_sent_to_login(self):
        self.client.logout()
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)
        self.assertNotIn("6037", response.content.decode())

    def test_sending_a_receipt_queues_it_for_review(self):
        response = self.client.post(
            self.url,
            {"receipts": [upload(), upload()], "payer_card_last4": "۱۲۳۴"},
        )

        self.assertRedirects(response, self.order.get_absolute_url())
        transfer = CardTransfer.objects.get()
        self.assertEqual(transfer.status, CardTransferStatus.SUBMITTED)
        self.assertEqual(transfer.amount, self.order.total)
        self.assertEqual(transfer.payer_card_last4, "1234")
        self.assertEqual(transfer.receipts.count(), 2)
        self.assertEqual(len(receipt_files()), 2)

    def test_sending_a_receipt_does_not_open_the_course(self):
        self.client.post(self.url, {"receipts": [upload()], "payer_card_last4": "1234"})

        self.order.refresh_from_db()
        self.assertEqual(self.order.status, OrderStatus.PENDING)
        self.assertFalse(Enrollment.objects.filter(user=self.user).exists())

    def test_receipt_file_name_is_random(self):
        self.client.post(
            self.url,
            {"receipts": [upload("ali-rezaei.png")], "payer_card_last4": "1234"},
        )
        name = CardTransferReceipt.objects.get().image.name
        self.assertTrue(name.startswith("card-receipts/"))
        self.assertNotIn("ali", name)

    def test_the_admin_is_notified_by_sms(self):
        self.client.post(self.url, {"receipts": [upload()], "payer_card_last4": "1234"})
        self.assertEqual(self.sms.call_args.args[0], "09120000000")

    def test_receipt_is_required(self):
        response = self.client.post(self.url, {"payer_card_last4": "1234"})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(CardTransfer.objects.exists())

    def test_more_than_three_images_are_refused(self):
        response = self.client.post(
            self.url,
            {"receipts": [upload() for _ in range(4)], "payer_card_last4": "1234"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(CardTransfer.objects.exists())
        self.assertEqual(receipt_files(), [])

    def test_last_four_digits_are_validated(self):
        response = self.client.post(self.url, {"receipts": [upload()], "payer_card_last4": "12"})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(CardTransfer.objects.exists())

    def test_a_second_receipt_cannot_be_sent_while_one_is_pending(self):
        self.submit()
        response = self.client.post(self.url, {"receipts": [upload()], "payer_card_last4": "1234"})

        self.assertRedirects(response, self.order.get_absolute_url())
        self.assertEqual(CardTransfer.objects.count(), 1)

    def test_pending_receipt_hides_pay_and_cancel_buttons(self):
        self.submit()
        response = self.client.get(self.order.get_absolute_url())

        self.assertContains(response, "در حال بررسی است")
        self.assertNotContains(
            response, reverse("orders:payment_start", args=[self.order.order_number])
        )
        self.assertNotContains(response, reverse("orders:cancel", args=[self.order.order_number]))

    def test_a_paid_order_cannot_send_a_receipt(self):
        self.order.mark_paid()
        response = self.client.get(self.url)
        self.assertRedirects(response, self.order.get_absolute_url(), fetch_redirect_response=False)


class PendingTransferGuardTests(CardTransferTestBase):
    def test_online_payment_is_blocked_while_a_receipt_is_pending(self):
        self.submit()
        result = start_payment(self.order, "http://testserver/payments/callback/")

        self.assertFalse(result.success)
        self.assertFalse(Payment.objects.exists())

    def test_cancel_is_blocked_while_a_receipt_is_pending(self):
        self.submit()
        self.client.force_login(self.user)
        self.client.post(reverse("orders:cancel", args=[self.order.order_number]))

        self.order.refresh_from_db()
        self.assertEqual(self.order.status, OrderStatus.PENDING)

    def test_a_pending_receipt_holds_a_seat(self):
        self.course.capacity = 1
        self.course.save()

        self.submit()

        self.assertEqual(seats_left(self.course), 0)


class ApproveTests(CardTransferTestBase):
    def test_approval_opens_the_course_and_records_the_payment(self):
        transfer = self.submit()

        result = approve_card_transfer(transfer, self.admin)

        self.assertTrue(result.success)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, OrderStatus.PAID)
        self.assertTrue(
            Enrollment.objects.filter(
                user=self.user, course=self.course, status=EnrollmentStatus.ACTIVE
            ).exists()
        )
        payment = Payment.objects.get()
        self.assertEqual(payment.gateway, "card_to_card")
        self.assertEqual(payment.status, PaymentStatus.SUCCESS)
        self.assertEqual(payment.amount, self.order.total)
        self.assertEqual(payment.ref_id, "998877")

        transfer.refresh_from_db()
        self.assertEqual(transfer.status, CardTransferStatus.APPROVED)
        self.assertEqual(transfer.reviewed_by, self.admin)
        self.assertEqual(transfer.payment, payment)

    def test_approval_deletes_the_receipt_images(self):
        transfer = self.submit(images=2)
        self.assertEqual(len(receipt_files()), 2)

        approve_card_transfer(transfer, self.admin)

        self.assertEqual(receipt_files(), [])
        self.assertFalse(CardTransferReceipt.objects.exists())
        transfer.refresh_from_db()
        self.assertIsNotNone(transfer.receipts_deleted_at)

    def test_the_buyer_is_notified(self):
        transfer = self.submit()
        approve_card_transfer(transfer, self.admin)
        self.assertEqual(self.sms.call_args.args[0], self.order.mobile or self.user.mobile)
        self.assertIn("تأیید شد", self.sms.call_args.args[1])

    def test_approving_twice_records_one_payment(self):
        transfer = self.submit()
        approve_card_transfer(transfer, self.admin)

        second = approve_card_transfer(transfer, self.admin)

        self.assertFalse(second.success)
        self.assertEqual(Payment.objects.count(), 1)

    def test_an_order_already_paid_online_is_not_paid_again(self):
        transfer = self.submit()
        self.order.mark_paid()

        result = approve_card_transfer(transfer, self.admin)

        self.assertFalse(result.success)
        self.assertFalse(Payment.objects.exists())
        self.assertEqual(len(receipt_files()), 1)  # برای تصمیم بعدی مدیر می‌ماند

    def test_amount_mismatch_is_refused(self):
        transfer = self.submit()
        type(self.order).objects.filter(pk=self.order.pk).update(total=self.order.total + 1000)

        result = approve_card_transfer(transfer, self.admin)

        self.assertFalse(result.success)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, OrderStatus.PENDING)

    def test_a_canceled_order_is_refused(self):
        transfer = self.submit()
        type(self.order).objects.filter(pk=self.order.pk).update(status=OrderStatus.CANCELED)

        self.assertFalse(approve_card_transfer(transfer, self.admin).success)


class RejectTests(CardTransferTestBase):
    def test_rejection_deletes_images_and_keeps_the_order_payable(self):
        transfer = self.submit()

        result = reject_card_transfer(transfer, self.admin, "واریزی دیده نشد.")

        self.assertTrue(result.success)
        self.assertEqual(receipt_files(), [])
        transfer.refresh_from_db()
        self.assertEqual(transfer.status, CardTransferStatus.REJECTED)
        self.order.refresh_from_db()
        self.assertTrue(self.order.is_payable)
        self.assertFalse(Enrollment.objects.filter(user=self.user).exists())
        self.assertIn("واریزی دیده نشد", self.sms.call_args.args[1])

    def test_a_reason_is_required(self):
        transfer = self.submit()

        self.assertFalse(reject_card_transfer(transfer, self.admin, "  ").success)
        transfer.refresh_from_db()
        self.assertTrue(transfer.is_pending)

    def test_after_rejection_the_buyer_sees_the_reason_and_can_try_again(self):
        transfer = self.submit()
        reject_card_transfer(transfer, self.admin, "مبلغ ناقص بود.")
        self.client.force_login(self.user)

        response = self.client.get(self.order.get_absolute_url())

        self.assertContains(response, "مبلغ ناقص بود.")
        self.submit()  # رسید تازه پذیرفته می‌شود


class AdminReviewTests(CardTransferTestBase):
    def setUp(self):
        super().setUp()
        self.transfer = self.submit()
        self.url = reverse("admin:orders_cardtransfer_change", args=[self.transfer.pk])
        self.client.force_login(self.admin)

    def test_the_review_page_shows_the_receipt_image(self):
        response = self.client.get(self.url)

        image_url = self.transfer.receipts.get().image.url
        self.assertContains(response, image_url)
        self.assertContains(response, "_approve_transfer")

    def test_the_admin_can_open_the_image(self):
        image_url = self.transfer.receipts.get().image.url
        response = self.client.get(image_url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Cache-Control"], "private, no-store")

    def test_the_approve_button_opens_the_course(self):
        response = self.client.post(self.url, {"_approve_transfer": "1"})

        self.assertRedirects(response, reverse("admin:orders_cardtransfer_changelist"))
        self.order.refresh_from_db()
        self.assertTrue(self.order.is_paid)
        self.assertEqual(receipt_files(), [])

    def test_the_reject_button_needs_a_reason(self):
        self.client.post(self.url, {"_reject_transfer": "1", "reject_reason": ""})
        self.transfer.refresh_from_db()
        self.assertTrue(self.transfer.is_pending)

        self.client.post(self.url, {"_reject_transfer": "1", "reject_reason": "رسید ناخوانا"})
        self.transfer.refresh_from_db()
        self.assertEqual(self.transfer.status, CardTransferStatus.REJECTED)
        self.assertEqual(self.transfer.reject_reason, "رسید ناخوانا")

    def test_after_review_the_image_link_is_gone(self):
        image_url = self.transfer.receipts.get().image.url
        self.client.post(self.url, {"_approve_transfer": "1"})

        self.assertEqual(self.client.get(image_url).status_code, 404)
        self.assertContains(self.client.get(self.url), "پاک شده است")

    def test_the_list_shows_how_many_are_waiting(self):
        response = self.client.get(reverse("admin:orders_cardtransfer_changelist"))
        self.assertContains(response, "۱ رسید در انتظار بررسی")

    def test_staff_without_permission_cannot_see_receipts(self):
        staff = User.objects.create_user(
            mobile="09360000000", password="HseTech!2026", is_staff=True
        )
        staff.user_permissions.add(Permission.objects.get(codename="view_course"))
        self.client.force_login(staff)

        image_url = self.transfer.receipts.get().image.url
        self.assertEqual(self.client.get(image_url).status_code, 404)
        self.assertEqual(self.client.get(self.url).status_code, 403)

    def test_view_only_staff_cannot_approve(self):
        staff = User.objects.create_user(
            mobile="09360000001", password="HseTech!2026", is_staff=True
        )
        staff.user_permissions.add(Permission.objects.get(codename="view_cardtransfer"))
        self.client.force_login(staff)

        self.assertNotContains(self.client.get(self.url), "_approve_transfer")
        response = self.client.post(self.url, {"_approve_transfer": "1"})

        self.assertEqual(response.status_code, 403)
        self.order.refresh_from_db()
        self.assertFalse(self.order.is_paid)

    def test_guest_cannot_open_a_receipt(self):
        image_url = self.transfer.receipts.get().image.url
        self.client.logout()
        response = self.client.get(image_url)
        self.assertNotEqual(response.status_code, 200)


class SiteSettingCardTests(TestCase):
    def test_enabling_without_a_valid_card_number_is_refused(self):
        site = SiteSetting.load()
        site.card_transfer_enabled = True
        site.card_transfer_number = "6037 99"
        with self.assertRaises(ValidationError):
            site.full_clean()

    def test_persian_digits_in_the_card_number_are_accepted(self):
        site = SiteSetting(card_transfer_enabled=True, card_transfer_number="۶۰۳۷۹۹۱۱۲۲۳۳۴۴۵۵")
        self.assertTrue(site.card_transfer_available)
        self.assertEqual(site.card_transfer_display, "6037 9911 2233 4455")
