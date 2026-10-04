"""
پرداخت کارت به کارت.

    خریدار مبلغ را به کارت آکادمی واریز می‌کند و عکس رسید می‌فرستد
        → submit_card_transfer()
    مدیر عکس را در پنل می‌بیند و تأیید یا رد می‌کند
        → approve_card_transfer() / reject_card_transfer()

دو قاعده:

۱. **فقط مدیر پرداخت را تأیید می‌کند.** فرستادن رسید هیچ دسترسی‌ای باز
   نمی‌کند؛ عکس رسید را هر کسی می‌تواند بسازد. دسترسی فقط وقتی باز می‌شود
   که مدیر واریز را در حساب بانکی دیده و تأیید کرده باشد — دقیقاً مثل
   درگاه که تأیید را سرور از بانک می‌پرسد، نه از کاربر.

۲. **عکس رسید موقت است.** با فرستادن، عکس فشرده و کوچک می‌شود (حدود
   ۱۰۰ تا ۳۰۰ کیلوبایت) و بیرون از پوشه عمومی ذخیره می‌شود. با تأیید یا رد
   مدیر، همان لحظه از دیسک پاک می‌شود. آنچه می‌ماند فقط رد مالی است:
   مبلغ، چهار رقم آخر کارت، شماره پیگیری، بررسی‌کننده و زمان.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from io import BytesIO

from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.db import IntegrityError, transaction
from django.utils import timezone
from PIL import Image, ImageOps, UnidentifiedImageError

from apps.core.jalali import to_persian_digits
from apps.orders.models import (
    CardTransfer,
    CardTransferReceipt,
    CardTransferStatus,
    Order,
    OrderStatus,
    Payment,
    PaymentStatus,
)

from .orders import mark_order_paid

logger = logging.getLogger("hse.payment")

CARD_TRANSFER_GATEWAY = "card_to_card"

MAX_RECEIPTS = 3
MAX_UPLOAD_BYTES = 8 * 1024 * 1024  # حجم فایل ارسالی، پیش از فشرده‌سازی
MAX_SIDE = 1600  # بلندترین ضلع عکس پس از کوچک‌سازی؛ برای خواندن رسید کافی است
MAX_PIXELS = 40_000_000  # جلوی «بمب فشرده‌سازی» را می‌گیرد
JPEG_QUALITY = 80
ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP"}


@dataclass
class CardTransferResult:
    success: bool
    message: str = ""
    transfer: CardTransfer | None = None


# ---------------------------------------------------------------------------
# عکس رسید
# ---------------------------------------------------------------------------


def compress_receipt(uploaded) -> ContentFile:
    """
    عکس ارسالی را بررسی، کوچک و دوباره ذخیره می‌کند.

    دوباره‌سازی عکس سه فایده دارد: حجم را چند برابر کم می‌کند، اطلاعات
    پنهان عکس (مکان، مدل گوشی) را پاک می‌کند، و هر فایلی که فقط پسوند عکس
    دارد ولی عکس نیست، همین‌جا رد می‌شود.
    """
    if uploaded.size > MAX_UPLOAD_BYTES:
        raise ValidationError("حجم هر عکس باید کمتر از ۸ مگابایت باشد.")

    try:
        image = Image.open(uploaded)
        image.verify()  # فایل خراب یا جعلی همین‌جا خطا می‌دهد
        uploaded.seek(0)
        image = Image.open(uploaded)

        if image.format not in ALLOWED_FORMATS:
            raise ValidationError("فقط عکس JPG، PNG یا WEBP پذیرفته می‌شود.")
        if image.width * image.height > MAX_PIXELS:
            raise ValidationError("ابعاد عکس بیش از حد بزرگ است.")

        image = ImageOps.exif_transpose(image)  # عکس چرخیده گوشی، صاف شود
        if image.mode in ("RGBA", "LA", "P"):
            image = image.convert("RGBA")
            background = Image.new("RGB", image.size, "white")
            background.paste(image, mask=image.getchannel("A"))
            image = background
        else:
            image = image.convert("RGB")

        image.thumbnail((MAX_SIDE, MAX_SIDE))

        buffer = BytesIO()
        image.save(buffer, "JPEG", quality=JPEG_QUALITY, optimize=True)
    except ValidationError:
        raise
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
        raise ValidationError("این فایل عکس معتبری نیست.") from None

    return ContentFile(buffer.getvalue(), name="receipt.jpg")


# ---------------------------------------------------------------------------
# ارسال رسید (خریدار)
# ---------------------------------------------------------------------------


def pending_transfer(order: Order) -> CardTransfer | None:
    return order.card_transfers.filter(status=CardTransferStatus.SUBMITTED).first()


def submit_card_transfer(
    order: Order,
    *,
    images: list[ContentFile],
    payer_card_last4: str,
    tracking_code: str = "",
    payer_note: str = "",
) -> CardTransferResult:
    """
    ثبت رسید کارت به کارت. هیچ دسترسی‌ای باز نمی‌کند؛ فقط صف بررسی مدیر.

    صندلی کلاس از همین لحظه تا تصمیم مدیر نگه داشته می‌شود (capacity.py).
    اگر کلاس در فاصله دیدن شماره کارت تا فرستادن رسید پر شده باشد، رسید
    باز هم پذیرفته می‌شود: پول احتمالاً واریز شده و تصمیم (پذیرفتن با
    یک صندلی اضافه، یا رد و برگرداندن مبلغ) با مدیر است.
    """
    if not order.is_payable:
        return CardTransferResult(False, "این سفارش قابل پرداخت نیست.")
    if order.total <= 0:
        return CardTransferResult(False, "مبلغ این سفارش صفر است و نیازی به پرداخت ندارد.")
    if not images:
        return CardTransferResult(False, "عکس رسید را بفرستید.")

    from apps.courses.capacity import lock_and_find_full

    try:
        with transaction.atomic():
            # قفل روی دوره‌ها، تا شمارش صندلی با ثبت‌نام هم‌زمان قاطی نشود.
            full = lock_and_find_full(
                order.items.values_list("course_id", flat=True), order.user
            )
            transfer = CardTransfer.objects.create(
                order=order,
                amount=order.total,
                payer_card_last4=payer_card_last4,
                tracking_code=tracking_code[:40],
                payer_note=payer_note[:300],
            )
            for content in images:
                receipt = CardTransferReceipt(transfer=transfer, size_bytes=content.size)
                receipt.image.save(content.name, content, save=False)
                receipt.save()
    except IntegrityError:
        # رسید دیگری برای همین سفارش هم‌زمان ثبت شده (دو بار کلیک).
        return CardTransferResult(
            False, "برای این سفارش یک رسید در انتظار بررسی هست."
        )

    if full:
        logger.warning(
            "رسید کارت به کارت برای کلاس پر ثبت شد؛ تصمیم با مدیر. سفارش=%s دوره‌ها=%s",
            order.order_number,
            ",".join(course.slug for course in full),
        )

    logger.info(
        "رسید کارت به کارت ثبت شد. سفارش=%s مبلغ=%s عکس=%s",
        order.order_number,
        order.total,
        len(images),
    )
    _notify_admin(transfer)
    return CardTransferResult(
        True,
        "رسید شما ثبت شد. پس از تأیید واریز، دسترسی دوره‌ها فعال و به شما پیامک می‌شود.",
        transfer,
    )


# ---------------------------------------------------------------------------
# بررسی رسید (مدیر)
# ---------------------------------------------------------------------------


def approve_card_transfer(transfer: CardTransfer, reviewer) -> CardTransferResult:
    """
    تأیید واریز: ثبت تراکنش موفق، باز شدن دوره‌ها، پاک شدن عکس رسید.

    تأیید فقط یک بار انجام می‌شود، حتی اگر مدیر دو بار کلیک کند یا دو
    مدیر هم‌زمان تأیید کنند (قفل روی ردیف).
    """
    with transaction.atomic():
        transfer = (
            CardTransfer.objects.select_for_update()
            .select_related("order")
            .get(pk=transfer.pk)
        )
        order = transfer.order

        if not transfer.is_pending:
            return CardTransferResult(False, "این رسید قبلاً بررسی شده است.", transfer)
        if order.is_paid:
            return CardTransferResult(
                False,
                "این سفارش قبلاً از راه دیگری پرداخت شده است. رسید را رد کنید و "
                "مبلغ کارت به کارت را به خریدار برگردانید.",
                transfer,
            )
        if order.status in (OrderStatus.CANCELED, OrderStatus.REFUNDED):
            return CardTransferResult(
                False, "این سفارش لغو شده است. رسید را رد کنید.", transfer
            )
        if transfer.amount != order.total:
            return CardTransferResult(
                False,
                "مبلغ سفارش پس از ارسال رسید تغییر کرده است. رسید را رد کنید.",
                transfer,
            )

        now = timezone.now()
        payment = Payment.objects.create(
            order=order,
            gateway=CARD_TRANSFER_GATEWAY,
            amount=transfer.amount,
            status=PaymentStatus.SUCCESS,
            ref_id=transfer.tracking_code,
            card_pan=transfer.payer_card_last4,
            verified_at=now,
            raw_response={
                "card_transfer_id": transfer.pk,
                "approved_by": getattr(reviewer, "pk", None),
            },
        )
        transfer.status = CardTransferStatus.APPROVED
        transfer.payment = payment
        transfer.reviewed_by = reviewer
        transfer.reviewed_at = now
        transfer.save(
            update_fields=["status", "payment", "reviewed_by", "reviewed_at", "updated_at"]
        )

        mark_order_paid(order)

    # پاک کردن فایل بعد از ثبت قطعی؛ اگر ثبت شکست می‌خورد، عکس برای
    # بررسی دوباره می‌ماند.
    transfer.delete_receipt_files()

    logger.info(
        "کارت به کارت تأیید شد. سفارش=%s مبلغ=%s بررسی‌کننده=%s",
        order.order_number,
        transfer.amount,
        getattr(reviewer, "pk", None),
    )
    _notify_buyer(
        order,
        f"پرداخت کارت به کارت سفارش {order.order_number} تأیید شد و دوره‌ها "
        "در حساب کاربری شما فعال است.",
    )
    return CardTransferResult(True, "پرداخت تأیید شد و دوره‌ها برای خریدار باز شد.", transfer)


def reject_card_transfer(transfer: CardTransfer, reviewer, reason: str) -> CardTransferResult:
    """
    رد رسید: عکس پاک می‌شود و سفارش دوباره قابل پرداخت است.

    دلیل رد اجباری است؛ خریدار باید بداند چه کار کند (رسید واضح‌تر، مبلغ
    کامل، یا پرداخت آنلاین).
    """
    reason = (reason or "").strip()
    if not reason:
        return CardTransferResult(False, "دلیل رد را بنویسید؛ برای خریدار پیامک می‌شود.", transfer)

    with transaction.atomic():
        transfer = (
            CardTransfer.objects.select_for_update()
            .select_related("order")
            .get(pk=transfer.pk)
        )
        if not transfer.is_pending:
            return CardTransferResult(False, "این رسید قبلاً بررسی شده است.", transfer)

        transfer.status = CardTransferStatus.REJECTED
        transfer.reject_reason = reason[:300]
        transfer.reviewed_by = reviewer
        transfer.reviewed_at = timezone.now()
        transfer.save(
            update_fields=["status", "reject_reason", "reviewed_by", "reviewed_at", "updated_at"]
        )

    transfer.delete_receipt_files()

    order = transfer.order
    logger.info(
        "کارت به کارت رد شد. سفارش=%s بررسی‌کننده=%s",
        order.order_number,
        getattr(reviewer, "pk", None),
    )
    _notify_buyer(
        order,
        f"رسید کارت به کارت سفارش {order.order_number} تأیید نشد: {transfer.reject_reason}",
    )
    return CardTransferResult(True, "رسید رد شد و به خریدار اطلاع داده شد.", transfer)


# ---------------------------------------------------------------------------
# پیامک‌ها — خطای پیامک هیچ‌وقت جلوی پرداخت را نمی‌گیرد.
# ---------------------------------------------------------------------------


def _send_sms(mobile: str, text: str) -> None:
    if not mobile:
        return
    try:
        from apps.accounts.services.sms import get_sms_service

        get_sms_service().send(mobile, text)
    except Exception:  # noqa: BLE001 — پیامک اختیاری است
        logger.exception("ارسال پیامک کارت به کارت ناموفق بود.")


def _notify_buyer(order: Order, text: str) -> None:
    _send_sms(order.mobile or getattr(order.user, "mobile", ""), text)


def _notify_admin(transfer: CardTransfer) -> None:
    from apps.core.models import SiteSetting

    mobile = SiteSetting.load().card_transfer_notify_mobile.strip()
    amount = to_persian_digits(f"{transfer.amount:,}")
    _send_sms(
        mobile,
        f"رسید کارت به کارت جدید: سفارش {transfer.order.order_number}، "
        f"مبلغ {amount} تومان. برای بررسی به پنل مدیریت بروید.",
    )
