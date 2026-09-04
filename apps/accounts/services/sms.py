"""
سرویس ارسال پیامک.

چرا این‌قدر لایه‌بندی؟
شما هنوز پنل پیامک نخریده‌اید. اگر کد ارسال پیامک را مستقیم داخل Viewها
می‌نوشتیم، روزی که پنل واقعی را تهیه کنید باید ده‌ها جای پروژه را عوض کنید.
با این ساختار، فقط یک کلاس جدید اضافه می‌شود و یک خط در فایل .env عوض
می‌شود؛ هیچ View و فرم و مدلی دست نمی‌خورد.

ساختار:
    SmsProvider          ← قرارداد مشترک (چه متدهایی باید وجود داشته باشد)
    MockSmsProvider      ← نسخه آزمایشی: پیامک را در ترمینال چاپ می‌کند
    KavenegarSmsProvider ← نمونه پنل واقعی ایرانی
    get_sms_service()    ← بر اساس تنظیمات، نسخه درست را برمی‌گرداند
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

import requests
from django.conf import settings

logger = logging.getLogger("hse.sms")


def site_name() -> str:
    """
    نام سایت از پنل مدیریت خوانده می‌شود، نه از فایل تنظیمات.

    این‌طور اگر ادمین نام آکادمی را عوض کند، متن پیامک هم خودکار
    بروز می‌شود و نیازی به تغییر کد نیست.
    """
    try:
        from apps.core.models import SiteSetting

        return SiteSetting.load().site_name
    except Exception:  # noqa: BLE001 — پیامک نباید به‌خاطر خطای جانبی متوقف شود
        return settings.SITE_NAME


@dataclass
class SmsResult:
    """
    نتیجه استاندارد ارسال پیامک.

    همه Providerها همین شکل نتیجه را برمی‌گردانند تا کد بالادستی نیازی
    نداشته باشد بداند با کدام پنل کار می‌کند.
    """

    success: bool
    provider: str
    message: str = ""
    tracking_code: str = ""
    raw: dict = field(default_factory=dict)


class SmsProvider(ABC):
    """قرارداد مشترک همه پنل‌های پیامک."""

    name: str = "base"

    @abstractmethod
    def send(self, mobile: str, text: str) -> SmsResult:
        """ارسال یک پیامک ساده."""

    def send_otp(self, mobile: str, code: str) -> SmsResult:
        """
        ارسال کد یکبارمصرف.

        بیشتر پنل‌های ایرانی برای کد تأیید، مسیر جداگانه و ارزان‌تری
        دارند (ارسال با الگو). Providerهایی که چنین امکانی دارند این متد
        را بازنویسی می‌کنند.
        """
        return self.send(mobile, f"کد ورود شما به {site_name()}: {code}")


class MockSmsProvider(SmsProvider):
    """
    نسخه آزمایشی برای محیط توسعه.

    پیامکی ارسال نمی‌شود؛ کد در ترمینال چاپ می‌شود تا بتوانید کل جریان
    ثبت‌نام را بدون خرید پنل پیامک تست کنید.
    """

    name = "mock"

    def send(self, mobile: str, text: str) -> SmsResult:
        # این تنها جایی در کل پروژه است که کد خام نمایش داده می‌شود و
        # فقط در حالت آزمایشی اجرا می‌شود.
        print("\n" + "=" * 60)
        print("  پیامک آزمایشی (ارسال واقعی انجام نشد)")
        print(f"  گیرنده : {mobile}")
        print(f"  متن    : {text}")
        print("=" * 60 + "\n", flush=True)

        return SmsResult(success=True, provider=self.name, message="پیامک آزمایشی چاپ شد.")


class KavenegarSmsProvider(SmsProvider):
    """
    نمونه اتصال به پنل پیامک کاوه‌نگار.

    برای استفاده، در فایل .env این مقادیر را پر کنید:
        SMS_PROVIDER=kavenegar
        SMS_API_KEY=کلید-پنل-شما
        SMS_SENDER_NUMBER=شماره-خط-شما
        SMS_OTP_TEMPLATE=نام-الگوی-تأییدشده   (اختیاری)

    اگر پنل دیگری خریدید، از روی همین کلاس یکی مشابه بسازید و فقط
    آدرس و پارامترها را عوض کنید.
    """

    name = "kavenegar"
    BASE_URL = "https://api.kavenegar.com/v1"

    def __init__(self) -> None:
        self.api_key = settings.SMS_API_KEY
        self.sender = settings.SMS_SENDER_NUMBER
        self.template = settings.SMS_OTP_TEMPLATE
        self.timeout = settings.SMS_TIMEOUT_SECONDS

        if not self.api_key:
            raise ValueError(
                "SMS_API_KEY تنظیم نشده است. مقدار آن را در فایل .env قرار دهید."
            )

    def _post(self, path: str, params: dict) -> SmsResult:
        """
        تماس با سرویس و تبدیل هر خطای ممکن به نتیجه استاندارد.

        کاربر هرگز نباید خطای خام شبکه را ببیند؛ همه حالت‌های خطا اینجا
        گرفته و به پیام فارسی تبدیل می‌شوند.
        """
        url = f"{self.BASE_URL}/{self.api_key}/{path}"

        try:
            response = requests.post(url, data=params, timeout=self.timeout)
            response.raise_for_status()
            payload = response.json()

        except requests.Timeout:
            logger.error("پنل پیامک در زمان مقرر پاسخ نداد.")
            return SmsResult(
                success=False,
                provider=self.name,
                message="سرویس پیامک پاسخ نداد. لطفاً چند لحظه دیگر تلاش کنید.",
            )

        except requests.ConnectionError:
            logger.error("اتصال به پنل پیامک برقرار نشد.")
            return SmsResult(
                success=False,
                provider=self.name,
                message="ارتباط با سرویس پیامک برقرار نشد.",
            )

        except requests.HTTPError as exc:
            status = exc.response.status_code if exc.response is not None else "?"
            logger.error("پنل پیامک خطای HTTP %s برگرداند.", status)
            return SmsResult(
                success=False,
                provider=self.name,
                message="ارسال پیامک با خطا مواجه شد.",
            )

        except ValueError:
            logger.error("پاسخ پنل پیامک قابل خواندن نبود.")
            return SmsResult(
                success=False,
                provider=self.name,
                message="پاسخ سرویس پیامک نامعتبر بود.",
            )

        status = payload.get("return", {}).get("status")
        if status != 200:
            logger.error("پنل پیامک وضعیت %s برگرداند.", status)
            return SmsResult(
                success=False,
                provider=self.name,
                message="ارسال پیامک انجام نشد.",
                raw=payload,
            )

        entries = payload.get("entries") or [{}]
        return SmsResult(
            success=True,
            provider=self.name,
            tracking_code=str(entries[0].get("messageid", "")),
            raw=payload,
        )

    def send(self, mobile: str, text: str) -> SmsResult:
        return self._post(
            "sms/send.json",
            {"receptor": mobile, "sender": self.sender, "message": text},
        )

    def send_otp(self, mobile: str, code: str) -> SmsResult:
        # اگر الگوی تأییدشده دارید، ارسال با الگو ارزان‌تر و سریع‌تر است.
        if self.template:
            return self._post(
                "verify/lookup.json",
                {"receptor": mobile, "token": code, "template": self.template},
            )
        return super().send_otp(mobile, code)


# نگاشت نام پنل به کلاس آن. برای افزودن پنل جدید فقط یک سطر اینجا اضافه کنید.
PROVIDERS: dict[str, type[SmsProvider]] = {
    "mock": MockSmsProvider,
    "kavenegar": KavenegarSmsProvider,
}


def get_sms_service() -> SmsProvider:
    """
    Provider مناسب را بر اساس تنظیمات برمی‌گرداند.

    در محیط توسعه USE_MOCK_SMS=True است و همیشه نسخه آزمایشی برگردانده
    می‌شود، حتی اگر کلید پنل واقعی هم در .env باشد. این یعنی هیچ‌وقت
    به اشتباه از اعتبار پنل واقعی خرج نمی‌شود.
    """
    if settings.USE_MOCK_SMS:
        return MockSmsProvider()

    provider_class = PROVIDERS.get(settings.SMS_PROVIDER)

    if provider_class is None:
        logger.error(
            "پنل پیامک «%s» شناخته نشد. به حالت آزمایشی برگشتیم.",
            settings.SMS_PROVIDER,
        )
        return MockSmsProvider()

    return provider_class()
