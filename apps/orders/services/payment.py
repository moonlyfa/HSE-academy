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

import requests
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

    # True یعنی «نمی‌دانیم چه شد» — مثلاً پاسخ درگاه در شبکه گم شد. چنین
    # تراکنشی نباید «ناموفق» ثبت شود، چون ممکن است پول کسر و تأیید شده
    # باشد؛ باید دوباره پرسید.
    retryable: bool = False


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
    درگاه زرین‌پال (API نسخه ۴).

    فعال‌سازی، دو خط در فایل .env است:

        USE_MOCK_PAYMENT=False
        PAYMENT_PROVIDER=zarinpal
        ZARINPAL_MERCHANT_ID=<کد پذیرنده>

    **سه قاعده که این کلاس را شکل داده‌اند:**

    ۱. **مبلغ و شناسه تراکنش در verify از دیتابیس خودمان می‌آیند،** نه از
       آدرس بازگشتی. آدرس بازگشتی را مرورگر کاربر صدا می‌زند و هرچه در
       آن هست قابل دستکاری است.

    ۲. **واحد پول صریح فرستاده می‌شود.** قیمت‌های این سایت به تومان است و
       زرین‌پال هم ریال می‌پذیرد هم تومان. اگر واحد را نفرستیم و درگاه
       ریال فرض کند، مشتری یک‌دهم مبلغ را می‌پردازد؛ اگر برعکس، ده برابر.
       هر دو فاجعه‌اند، پس هیچ‌چیز به فرض سپرده نمی‌شود.

    ۳. **«نمی‌دانم» با «نه» فرق دارد.** اگر پاسخ verify در شبکه گم شود،
       ممکن است زرین‌پال تراکنش را تأیید کرده و پول مشتری کسر شده باشد.
       ثبت «ناموفق» در این حالت یعنی مشتری پول داده و چیزی نگرفته. پس
       چنین خطایی retryable است و تراکنش در انتظار می‌ماند تا دوباره
       پرسیده شود (دستور verify_pending_payments).
    """

    name = "zarinpal"

    PRODUCTION_API = "https://api.zarinpal.com/pg/v4/payment"
    PRODUCTION_STARTPAY = "https://www.zarinpal.com/pg/StartPay/"
    SANDBOX_API = "https://sandbox.zarinpal.com/pg/v4/payment"
    SANDBOX_STARTPAY = "https://sandbox.zarinpal.com/pg/StartPay/"

    # کد موفقیت. 101 یعنی «موفق، و قبلاً هم تأیید شده بود» — برای ما همان
    # موفقیت است؛ اتفاقاً وقتی رخ می‌دهد که تأیید قبلی در شبکه گم شده بود.
    CODE_OK = 100
    CODE_ALREADY_VERIFIED = 101

    # پیام فارسی برای خطاهای رایج. فهرست کامل در مستندات زرین‌پال است؛
    # برای کدی که اینجا نیست، پیام کلی به کاربر نشان داده می‌شود و متن
    # اصلی درگاه در لاگ و در raw_response تراکنش می‌ماند.
    ERROR_MESSAGES = {
        -9: "اطلاعات ارسالی به درگاه معتبر نبود.",
        -10: "کد پذیرنده یا آدرس سرور در درگاه معتبر نیست.",
        -11: "حساب پذیرنده در درگاه فعال نیست.",
        -12: "تعداد درخواست‌ها به درگاه بیش از حد مجاز بوده است.",
        -15: "حساب پذیرنده در درگاه معلق شده است.",
        -50: "مبلغ پرداخت‌شده با مبلغ سفارش یکی نیست.",
        -51: "پرداخت انجام نشد یا توسط شما لغو شد.",
        -53: "این تراکنش متعلق به این فروشگاه نیست.",
        -54: "شناسه تراکنش نامعتبر است.",
    }

    # خطاهایی که کاربر باید عین علتشان را ببیند. بقیه، مشکل تنظیمات
    # فروشگاه‌اند و نشان دادنشان به مشتری فقط گیج‌کننده است.
    USER_FACING_CODES = {-50, -51}

    SUPPORTED_CURRENCIES = {"IRT", "IRR"}

    def __init__(self) -> None:
        self.merchant_id = settings.ZARINPAL_MERCHANT_ID
        if not self.merchant_id:
            raise ValueError(
                "ZARINPAL_MERCHANT_ID تنظیم نشده است. مقدار آن را در فایل .env قرار دهید."
            )

        self.currency = settings.ZARINPAL_CURRENCY.upper()
        if self.currency not in self.SUPPORTED_CURRENCIES:
            raise ValueError(
                f"ZARINPAL_CURRENCY باید IRT (تومان) یا IRR (ریال) باشد، نه «{self.currency}»."
            )

        self.sandbox = settings.ZARINPAL_SANDBOX
        self.api = self.SANDBOX_API if self.sandbox else self.PRODUCTION_API
        self.startpay = self.SANDBOX_STARTPAY if self.sandbox else self.PRODUCTION_STARTPAY
        self.timeout = settings.PAYMENT_TIMEOUT_SECONDS

    # --- مبلغ -------------------------------------------------------------

    def gateway_amount(self, amount_toman: int) -> int:
        """
        مبلغ، در واحدی که به درگاه فرستاده می‌شود.

        تنها جای پروژه که تومان به چیز دیگری تبدیل می‌شود. هر تغییری در
        واحد پول باید همین‌جا و فقط همین‌جا انجام شود.
        """
        return amount_toman * 10 if self.currency == "IRR" else amount_toman

    # --- درخواست پرداخت ---------------------------------------------------

    def request(self, payment: Payment, callback_url: str) -> PaymentResult:
        order = payment.order
        amount = self.gateway_amount(payment.amount)

        body = {
            "merchant_id": self.merchant_id,
            "amount": amount,
            "currency": self.currency,
            "callback_url": callback_url,
            "description": f"سفارش {order.order_number}",
            "metadata": {
                "mobile": order.mobile or "",
                "order_id": order.order_number,
            },
        }

        response = self._post("request.json", body)
        if response.transport_error:
            return PaymentResult(
                success=False,
                message="ارتباط با درگاه پرداخت برقرار نشد. لطفاً چند دقیقه دیگر دوباره تلاش کنید.",
                error_code="network",
                raw={"error": response.transport_error},
            )

        # مبلغ و واحدی که واقعاً فرستاده شد، کنار تراکنش ذخیره می‌شود تا
        # verify دقیقاً همان را بفرستد — حتی اگر تنظیمات در این فاصله عوض
        # شده باشد.
        sent = {"gateway_amount": amount, "currency": self.currency}

        authority = response.data.get("authority", "")
        if response.code == self.CODE_OK and authority:
            return PaymentResult(
                success=True,
                authority=authority,
                redirect_url=f"{self.startpay}{authority}",
                raw={"request": response.data, **sent},
            )

        return self._failure(response, stage="request", extra=sent)

    # --- تأیید پرداخت -----------------------------------------------------

    def verify(self, payment: Payment, data: dict) -> PaymentResult:
        """
        تأیید سرور به سرور.

        `data` (پارامترهای آدرس بازگشتی) عمداً استفاده نمی‌شود: شناسه
        تراکنش و مبلغ هر دو از رکورد خودمان خوانده می‌شوند.
        """
        amount = payment.raw_response.get(
            "gateway_amount", self.gateway_amount(payment.amount)
        )

        body = {
            "merchant_id": self.merchant_id,
            "amount": amount,
            "authority": payment.authority,
        }

        response = self._post("verify.json", body)
        if response.transport_error:
            return PaymentResult(
                success=False,
                message=(
                    "پاسخ درگاه دریافت نشد. پرداخت شما در حال بررسی است؛ اگر مبلغی "
                    "کسر شده، تا دقایقی دیگر دسترسی دوره خودکار فعال می‌شود."
                ),
                error_code="network",
                retryable=True,
                raw={"error": response.transport_error},
            )

        if response.code in (self.CODE_OK, self.CODE_ALREADY_VERIFIED):
            return PaymentResult(
                success=True,
                ref_id=str(response.data.get("ref_id", "")),
                card_pan=str(response.data.get("card_pan", "")),
                raw={
                    "verify": response.data,
                    "already_verified": response.code == self.CODE_ALREADY_VERIFIED,
                },
            )

        return self._failure(response, stage="verify")

    # --- ابزار --------------------------------------------------------------

    def _post(self, endpoint: str, body: dict) -> "_ZarinPalResponse":
        """
        یک درخواست به API زرین‌پال.

        خطای شبکه، پاسخ غیر JSON و خطای ۵xx سرور همه «transport_error»
        حساب می‌شوند: یعنی نمی‌دانیم درگاه چه کرد. پاسخ JSON با فیلد
        errors، یعنی درگاه صریحاً «نه» گفته است.
        """
        url = f"{self.api}/{endpoint}"

        try:
            http = requests.post(
                url,
                json=body,
                headers={"Accept": "application/json"},
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            logger.error("خطای شبکه در تماس با زرین‌پال. آدرس=%s خطا=%s", endpoint, exc)
            return _ZarinPalResponse(transport_error=str(exc)[:200])

        if http.status_code >= 500:
            logger.error("خطای سرور زرین‌پال. آدرس=%s کد=%s", endpoint, http.status_code)
            return _ZarinPalResponse(transport_error=f"http {http.status_code}")

        try:
            payload = http.json()
        except ValueError:
            logger.error("پاسخ نامعتبر از زرین‌پال. آدرس=%s", endpoint)
            return _ZarinPalResponse(transport_error="invalid json")

        return _ZarinPalResponse.from_payload(payload)

    def _failure(self, response: "_ZarinPalResponse", *, stage: str, extra=None) -> PaymentResult:
        code = response.code
        known = self.ERROR_MESSAGES.get(code)

        if code in self.USER_FACING_CODES and known:
            message = known
        elif stage == "request":
            message = "درگاه پرداخت در حال حاضر پاسخ نمی‌دهد. لطفاً کمی بعد دوباره تلاش کنید."
        else:
            message = "پرداخت تأیید نشد. اگر مبلغی کسر شده، تا ۷۲ ساعت آینده به حساب شما برمی‌گردد."

        logger.warning(
            "زرین‌پال خطا داد. مرحله=%s کد=%s پیام=%s",
            stage,
            code,
            response.message or known or "—",
        )

        return PaymentResult(
            success=False,
            message=message,
            error_code=str(code) if code is not None else "unknown",
            raw={
                "errors": response.errors,
                "gateway_message": response.message,
                **(extra or {}),
            },
        )


@dataclass
class _ZarinPalResponse:
    """پاسخ API زرین‌پال، یک‌دست‌شده."""

    code: int | None = None
    data: dict = field(default_factory=dict)
    errors: dict | list = field(default_factory=dict)
    message: str = ""
    transport_error: str = ""

    @classmethod
    def from_payload(cls, payload: dict) -> "_ZarinPalResponse":
        """
        زرین‌پال در موفقیت `data` را شیء و `errors` را فهرست خالی
        برمی‌گرداند، و در خطا برعکس. هر دو شکل اینجا یکی می‌شوند.
        """
        data = payload.get("data") if isinstance(payload, dict) else None
        errors = payload.get("errors") if isinstance(payload, dict) else None

        data = data if isinstance(data, dict) else {}

        if isinstance(errors, dict) and errors:
            return cls(
                code=_as_int(errors.get("code")),
                data=data,
                errors=errors,
                message=str(errors.get("message", ""))[:300],
            )

        return cls(code=_as_int(data.get("code")), data=data, errors=errors or {})


def _as_int(value) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


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

    from apps.courses.capacity import full_message, lock_and_find_full

    gateway = get_payment_gateway()

    # ساخت تراکنش همان «نگه داشتن صندلی» است؛ بررسی ظرفیت و ساختنش باید
    # زیر یک قفل باشند تا دو نفر هم‌زمان آخرین صندلی را نگیرند. تماس با
    # درگاه بیرون از قفل است تا کندی درگاه، بقیه خریداران را معطل نکند.
    with transaction.atomic():
        full = lock_and_find_full(
            order.items.values_list("course_id", flat=True), order.user
        )
        if full:
            logger.info(
                "شروع پرداخت به خاطر تکمیل ظرفیت متوقف شد. سفارش=%s دوره‌ها=%s",
                order.order_number,
                ",".join(course.slug for course in full),
            )
            return PaymentResult(
                success=False,
                message=full_message(full) + " مبلغی از حساب شما کسر نشده است.",
            )

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
    #
    # در درگاه‌های شبکه شاپرک، تراکنشی که فروشنده verify نکند خودکار به
    # حساب مشتری برمی‌گردد. پس رد کردن تراکنش منقضی **بدون** صدا زدن
    # verify، پول کسی را نمی‌خورد — فقط پرداخت دیرهنگام را نمی‌پذیرد.
    #
    # یک استثنا: اگر قبلاً verify فرستاده‌ایم و پاسخش در شبکه گم شده،
    # ممکن است درگاه تأییدش کرده باشد و دیگر خودکار برنگردد. چنین
    # تراکنشی باید دوباره پرسیده شود، هر چقدر هم دیر شده باشد.
    already_asked = bool(payment.raw_response.get("verify_attempts"))

    if payment.is_expired() and not already_asked:
        _fail(payment, "مهلت این تراکنش تمام شده است.", "expired")
        return PaymentResult(
            success=False,
            message=(
                "مهلت این تراکنش تمام شده است. اگر مبلغی از حساب شما کسر شده، "
                "تا ۷۲ ساعت آینده خودکار برمی‌گردد."
            ),
        )

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
    #
    #    تلاش **پیش از** تماس ثبت می‌شود، نه بعدش: اگر پردازه وسط تماس از
    #    کار بیفتد، باید بدانیم که شاید درگاه تأیید کرده باشد.
    payment.raw_response = {
        **payment.raw_response,
        "verify_attempts": payment.raw_response.get("verify_attempts", 0) + 1,
    }
    payment.save(update_fields=["raw_response", "updated_at"])

    gateway = get_payment_gateway()
    result = gateway.verify(payment, data)

    # «نمی‌دانیم» با «نه» فرق دارد. تراکنش در انتظار می‌ماند تا دوباره
    # پرسیده شود — با بازگشت دوباره کاربر به همین آدرس، یا با دستور
    # verify_pending_payments.
    if result.retryable:
        payment.raw_response = {
            **payment.raw_response,
            "last_verify_error": result.raw.get("error", result.error_code),
            "last_verify_at": timezone.now().isoformat(),
        }
        payment.save(update_fields=["raw_response", "updated_at"])
        logger.error(
            "تأیید پرداخت نامعلوم ماند و بعداً دوباره پرسیده می‌شود. سفارش=%s شناسه=%s",
            order.order_number,
            payment.authority,
        )
        return result

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
