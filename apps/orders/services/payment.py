"""
سرویس درگاه پرداخت.

ساختار دقیقاً مثل سرویس پیامک و احراز هویت است:

    PaymentGateway          ← قرارداد مشترک همه درگاه‌ها
    MockPaymentGateway      ← درگاه آزمایشی برای توسعه و تست
    ZarinPalGateway         ← درگاه واقعی (فاز ۱۳)
    get_payment_gateway()   ← بر اساس تنظیمات، نسخه درست را برمی‌گرداند

مهم‌ترین قاعده امنیتی کل پروژه اینجاست:

    ┌──────────────────────────────────────────────────────────────┐
    │ هیچ سفارشی از روی پارامترهای آدرس بازگشتی درگاه               │
    │ «پرداخت‌شده» علامت نمی‌خورد.                                   │
    └──────────────────────────────────────────────────────────────┘

چرا؟ آدرس بازگشتی را مرورگر کاربر صدا می‌زند، نه درگاه. یعنی هرکسی
می‌تواند دستی در نوار آدرس بنویسد:

    /payments/callback/?Authority=XYZ&Status=OK

اگر سایت همین را باور کند، دوره چند میلیونی بدون پرداخت یک ریال باز
می‌شود. این رایج‌ترین راه کلاهبرداری از فروشگاه‌های ایرانی است.

راه درست: بعد از بازگشت کاربر، خود سرور ما مستقیماً از درگاه می‌پرسد
«این تراکنش واقعاً پرداخت شده؟ چقدر؟» و فقط اگر پاسخ درگاه مثبت بود و
مبلغ هم دقیقاً با سفارش جور بود، دسترسی داده می‌شود.
"""

from __future__ import annotations

import logging
import secrets
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.orders.models import Order, OrderStatus, Payment, PaymentStatus

from .orders import mark_order_paid

logger = logging.getLogger("hse.payment")


@dataclass
class PaymentResult:
    """
    نتیجه استاندارد کار با درگاه.

    همه درگاه‌ها همین شکل نتیجه را برمی‌گردانند تا کد بالادستی نیازی
    نداشته باشد بداند با کدام درگاه کار می‌کند.
    """

    success: bool
    message: str = ""
    redirect_url: str = ""
    authority: str = ""
    ref_id: str = ""
    card_pan: str = ""
    error_code: str = ""
    raw: dict = field(default_factory=dict)


class PaymentGateway(ABC):
    """قرارداد مشترک همه درگاه‌های پرداخت."""

    name: str = "base"

    @abstractmethod
    def request(self, payment: Payment, callback_url: str) -> PaymentResult:
        """
        شروع پرداخت.

        به درگاه می‌گوییم «این مبلغ را از این کاربر بگیر» و درگاه یک
        شناسه (authority) و آدرسی می‌دهد که کاربر را به آن می‌فرستیم.
        """

    @abstractmethod
    def verify(self, payment: Payment, data: dict) -> PaymentResult:
        """
        تأیید پرداخت — تماس سرور به سرور با درگاه.

        `data` پارامترهای آدرس بازگشتی است و **فقط برای پیدا کردن تراکنش**
        استفاده می‌شود؛ هرگز به‌عنوان سند پرداخت پذیرفته نمی‌شود.
        """


class MockPaymentGateway(PaymentGateway):
    """
    درگاه آزمایشی.

    هیچ پولی جابه‌جا نمی‌شود؛ به‌جای بانک، صفحه‌ای در خود سایت باز می‌شود
    که دو دکمه دارد: «پرداخت موفق» و «پرداخت ناموفق». با همین می‌شود کل
    مسیر خرید را — از سبد تا باز شدن دسترسی دوره — بدون خرید هیچ درگاهی
    آزمایش کرد.

    نکته مهم: این درگاه هم مرحله تأیید سمت سرور را شبیه‌سازی می‌کند.
    تصمیم کاربر روی صفحه درگاه در دیتابیس ذخیره می‌شود و متد verify همان
    داده ذخیره‌شده را می‌خواند — نه پارامتر آدرس را. اگر این‌طور نبود،
    معماری امنیتی ما در حالت آزمایشی «کار می‌کرد» ولی در حالت واقعی
    امتحان نشده می‌ماند.
    """

    name = "mock"

    def request(self, payment: Payment, callback_url: str) -> PaymentResult:
        from django.urls import reverse

        authority = f"MOCK-{secrets.token_hex(12).upper()}"
        gateway_url = reverse("orders:mock_gateway", kwargs={"authority": authority})

        print("\n" + "=" * 60)
        print("  درگاه پرداخت آزمایشی (هیچ پولی جابه‌جا نشد)")
        print(f"  سفارش : {payment.order.order_number}")
        print(f"  مبلغ  : {payment.amount:,} تومان")
        print(f"  آدرس  : {gateway_url}")
        print("=" * 60 + "\n", flush=True)

        return PaymentResult(
            success=True,
            authority=authority,
            redirect_url=gateway_url,
            raw={"gateway": "mock", "callback": callback_url},
        )

    def verify(self, payment: Payment, data: dict) -> PaymentResult:
        """
        تأیید تراکنش آزمایشی.

        تصمیم را از `raw_response` می‌خوانیم — یعنی از دیتابیس خودمان که
        هنگام کلیک کاربر روی صفحه درگاه پر شده — نه از پارامتر آدرس.
        این همان چیزی است که در درگاه واقعی، تماس سرور به سرور انجامش
        می‌دهد.
        """
        decision = payment.raw_response.get("mock_decision")

        if decision != "success":
            return PaymentResult(
                success=False,
                message="پرداخت انجام نشد یا توسط شما لغو شد.",
                error_code="mock_not_paid",
                raw={"decision": decision},
            )

        return PaymentResult(
            success=True,
            ref_id=payment.raw_response.get("mock_ref_id", ""),
            card_pan=payment.raw_response.get("mock_card_pan", "6037"),
            raw={"decision": decision, "verified_by": "mock"},
        )


class ZarinPalGateway(PaymentGateway):
    """
    درگاه واقعی زرین‌پال.

    پیاده‌سازی کامل در فاز ۱۳ انجام می‌شود. همین که کلاسش اینجاست یعنی
    وقتی درگاه را خریدید، فقط یک خط در فایل .env عوض می‌شود:

        PAYMENT_PROVIDER=zarinpal
        USE_MOCK_PAYMENT=False

    و هیچ View و مدل و قالبی دست نمی‌خورد.
    """

    name = "zarinpal"

    def __init__(self) -> None:
        self.merchant_id = settings.ZARINPAL_MERCHANT_ID
        if not self.merchant_id:
            raise ValueError(
                "ZARINPAL_MERCHANT_ID تنظیم نشده است. مقدار آن را در فایل .env قرار دهید."
            )

    def request(self, payment: Payment, callback_url: str) -> PaymentResult:
        raise NotImplementedError("اتصال به زرین‌پال در فاز ۱۳ انجام می‌شود.")

    def verify(self, payment: Payment, data: dict) -> PaymentResult:
        raise NotImplementedError("اتصال به زرین‌پال در فاز ۱۳ انجام می‌شود.")


GATEWAYS: dict[str, type[PaymentGateway]] = {
    "mock": MockPaymentGateway,
    "zarinpal": ZarinPalGateway,
}


def get_payment_gateway() -> PaymentGateway:
    """
    درگاه مناسب را بر اساس تنظیمات برمی‌گرداند.

    در محیط توسعه USE_MOCK_PAYMENT=True است و همیشه درگاه آزمایشی
    برگردانده می‌شود — حتی اگر کلید درگاه واقعی هم در .env باشد. این یعنی
    هیچ‌وقت به اشتباه در محیط تست، تراکنش واقعی زده نمی‌شود.
    """
    if settings.USE_MOCK_PAYMENT:
        return MockPaymentGateway()

    gateway_class = GATEWAYS.get(settings.PAYMENT_PROVIDER)

    if gateway_class is None:
        logger.error(
            "درگاه پرداخت «%s» شناخته نشد. به حالت آزمایشی برگشتیم.",
            settings.PAYMENT_PROVIDER,
        )
        return MockPaymentGateway()

    return gateway_class()


# ---------------------------------------------------------------------------
# جریان پرداخت
# ---------------------------------------------------------------------------


def start_payment(order: Order, callback_url: str) -> PaymentResult:
    """
    شروع پرداخت یک سفارش.

    یک رکورد Payment ساخته می‌شود تا حتی اگر کاربر وسط راه صفحه را ببندد،
    رد این تلاش در دیتابیس بماند.
    """
    if not order.is_payable:
        return PaymentResult(
            success=False, message="این سفارش قابل پرداخت نیست."
        )

    if order.total <= 0:
        return PaymentResult(
            success=False, message="مبلغ این سفارش صفر است و نیازی به پرداخت ندارد."
        )

    gateway = get_payment_gateway()
    payment = Payment.objects.create(
        order=order, gateway=gateway.name, amount=order.total
    )

    result = gateway.request(payment, callback_url)

    if not result.success:
        payment.status = PaymentStatus.FAILED
        payment.error_message = result.message[:300]
        payment.error_code = result.error_code[:50]
        payment.raw_response = result.raw
        payment.save(
            update_fields=["status", "error_message", "error_code", "raw_response", "updated_at"]
        )

        logger.error(
            "شروع پرداخت ناموفق بود. سفارش=%s درگاه=%s خطا=%s",
            order.order_number,
            gateway.name,
            result.error_code or result.message,
        )
        return result

    payment.authority = result.authority
    payment.raw_response = result.raw
    payment.save(update_fields=["authority", "raw_response", "updated_at"])

    logger.info(
        "پرداخت آغاز شد. سفارش=%s درگاه=%s مبلغ=%s",
        order.order_number,
        gateway.name,
        payment.amount,
    )
    return result


def verify_payment(payment: Payment, data: dict) -> PaymentResult:
    """
    تأیید نهایی پرداخت و باز کردن دسترسی.

    ترتیب بررسی‌ها عمدی است — از ارزان‌ترین به گران‌ترین، و از مهم‌ترین
    نظر امنیتی به کم‌اهمیت‌تر:

    ۱. آیا این تراکنش قبلاً تأیید شده؟ (جلوگیری از تأیید دوباره)
    ۲. آیا مهلتش تمام نشده؟
    ۳. آیا سفارش هنوز قابل پرداخت است؟
    ۴. حالا از خود درگاه بپرس (تماس سرور به سرور)
    ۵. آیا مبلغ تأییدشده دقیقاً با مبلغ سفارش یکی است؟
    """
    order = payment.order

    # ۱. تأیید دوباره نباید دسترسی دوباره بدهد یا کد تخفیف را دوبار بسوزاند.
    if payment.is_successful:
        return PaymentResult(
            success=True,
            message="این پرداخت قبلاً تأیید شده است.",
            ref_id=payment.ref_id,
        )

    if not payment.is_pending:
        return PaymentResult(
            success=False, message="این تراکنش دیگر معتبر نیست."
        )

    # ۲. تراکنشی که ساعت‌ها باز مانده پذیرفته نمی‌شود.
    if payment.is_expired():
        _fail(payment, "مهلت این تراکنش تمام شده است.", "expired")
        return PaymentResult(success=False, message="مهلت این تراکنش تمام شده است.")

    # ۳. سفارشی که در این فاصله لغو شده نباید پرداخت شود.
    if order.status == OrderStatus.CANCELED:
        _fail(payment, "این سفارش لغو شده است.", "order_canceled")
        return PaymentResult(success=False, message="این سفارش لغو شده است.")

    if order.is_paid:
        payment.status = PaymentStatus.SUCCESS
        payment.save(update_fields=["status", "updated_at"])
        return PaymentResult(success=True, message="این سفارش قبلاً پرداخت شده است.")

    # ۴. اینجاست که واقعاً از درگاه می‌پرسیم. تا این لحظه هیچ‌چیز از
    #    پارامترهای آدرس بازگشتی باور نشده است.
    gateway = get_payment_gateway()
    result = gateway.verify(payment, data)

    if not result.success:
        _fail(payment, result.message or "پرداخت تأیید نشد.", result.error_code)
        logger.warning(
            "تأیید پرداخت ناموفق. سفارش=%s شناسه=%s خطا=%s",
            order.order_number,
            payment.authority,
            result.error_code or result.message,
        )
        return result

    # ۵. آخرین سد: مبلغی که تأیید شده باید دقیقاً همان مبلغ سفارش باشد.
    #    اگر جایی مبلغ دستکاری شده باشد، همین‌جا گرفته می‌شود.
    if payment.amount != order.total:
        _fail(payment, "مبلغ پرداخت با مبلغ سفارش مطابقت ندارد.", "amount_mismatch")
        logger.error(
            "اختلاف مبلغ در تأیید پرداخت! سفارش=%s مبلغ‌سفارش=%s مبلغ‌تراکنش=%s",
            order.order_number,
            order.total,
            payment.amount,
        )
        return PaymentResult(
            success=False,
            message="مبلغ پرداخت با مبلغ سفارش مطابقت ندارد. با پشتیبانی تماس بگیرید.",
        )

    with transaction.atomic():
        payment.status = PaymentStatus.SUCCESS
        payment.ref_id = result.ref_id[:100]
        payment.card_pan = result.card_pan[-4:] if result.card_pan else ""
        payment.verified_at = timezone.now()
        payment.raw_response = {**payment.raw_response, "verify": result.raw}
        payment.save(
            update_fields=[
                "status",
                "ref_id",
                "card_pan",
                "verified_at",
                "raw_response",
                "updated_at",
            ]
        )

        mark_order_paid(order)

    logger.info(
        "پرداخت تأیید شد. سفارش=%s پیگیری=%s مبلغ=%s",
        order.order_number,
        payment.ref_id,
        payment.amount,
    )
    return result


def _fail(payment: Payment, message: str, code: str = "") -> None:
    """ثبت شکست یک تراکنش، با دلیلش."""
    payment.status = PaymentStatus.FAILED
    payment.error_message = message[:300]
    payment.error_code = (code or "")[:50]
    payment.save(
        update_fields=["status", "error_message", "error_code", "updated_at"]
    )

    order = payment.order
    if order.status == OrderStatus.PENDING:
        order.status = OrderStatus.FAILED
        order.save(update_fields=["status", "updated_at"])
