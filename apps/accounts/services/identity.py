"""
سرویس تطبیق شماره موبایل و کد ملی.

این سرویس بررسی می‌کند که آیا شماره موبایل و کد ملی متعلق به یک نفر هستند
یا نه. در ایران این کار از طریق سامانه «شاهکار» انجام می‌شود که معمولاً
با واسطه‌هایی مثل فینوتک، جیبیت یا زیبال در دسترس است.

شما هنوز سرویس‌دهنده را انتخاب نکرده‌اید، پس دقیقاً مثل سرویس پیامک
لایه‌بندی شده است:

    IdentityProvider        ← قرارداد مشترک
    MockIdentityProvider    ← نسخه آزمایشی برای توسعه
    ShahkarIdentityProvider ← نمونه سرویس واقعی
    get_identity_service()  ← انتخاب خودکار بر اساس تنظیمات

روزی که سرویس واقعی را خریدید، فقط یک کلاس اضافه می‌شود و یک خط در .env
عوض می‌شود. هیچ View و فرم و مدلی دست نمی‌خورد.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

import requests
from django.conf import settings

logger = logging.getLogger("hse.identity")


@dataclass
class IdentityResult:
    """
    نتیجه استاندارد استعلام.

    توجه به تفاوت دو فیلد اول — این مهم‌ترین نکته این فایل است:

    success = آیا توانستیم با سرویس حرف بزنیم؟
    matched = آیا شماره و کد ملی متعلق به یک نفر بودند؟

    این دو کاملاً جدا هستند. اگر سرویس قطع باشد success=False است و
    matched اصلاً معنا ندارد. اگر این دو را قاطی کنیم، قطعی سرویس با
    «هویت تطبیق ندارد» یکی می‌شود و کاربر بی‌گناه رد می‌شود.
    """

    success: bool
    matched: bool = False
    provider: str = ""
    tracking_code: str = ""
    message: str = ""
    raw: dict = field(default_factory=dict)


class IdentityProvider(ABC):
    """قرارداد مشترک همه سرویس‌های استعلام هویت."""

    name: str = "base"

    @abstractmethod
    def verify(self, mobile: str, national_code: str) -> IdentityResult:
        """بررسی تطبیق شماره موبایل و کد ملی."""


class MockIdentityProvider(IdentityProvider):
    """
    نسخه آزمایشی برای محیط توسعه — بدون هیچ تماسی با اینترنت.

    نتیجه با تنظیم MOCK_IDENTITY_RESULT در فایل .env کنترل می‌شود:

        matched          پیش‌فرض — همیشه تطبیق دارد (جریان عادی سایت)
        not_matched      همیشه تطبیق ندارد (تست پیام خطای کاربر)
        failed           همیشه خطای سرویس (تست قطعی سرویس)
        by_national_code بر اساس دو رقم آخر کد ملی: ۰۰ تطبیق ندارد، ۹۹ خطا

    چرا پیش‌فرض «همیشه تطبیق دارد» است و نه قانون رقمی؟
    چون کد ملی واقعی شما ممکن است تصادفاً به ۰۰ یا ۹۹ ختم شود و بدون
    اینکه بدانید چرا، ثبت‌نام رد شود. حالت رقمی هست، اما فقط وقتی
    خودتان عمداً روشنش کنید.
    """

    name = "mock"

    def verify(self, mobile: str, national_code: str) -> IdentityResult:
        mode = getattr(settings, "MOCK_IDENTITY_RESULT", "matched")

        if mode == "by_national_code":
            if national_code.endswith("99"):
                mode = "failed"
            elif national_code.endswith("00"):
                mode = "not_matched"
            else:
                mode = "matched"

        if mode == "failed":
            return IdentityResult(
                success=False,
                provider=self.name,
                message=(
                    "در حال حاضر امکان ارتباط با سرویس احراز هویت وجود ندارد. "
                    "لطفاً چند دقیقه دیگر مجدداً تلاش کنید. (شبیه‌سازی)"
                ),
            )

        if mode == "not_matched":
            return IdentityResult(
                success=True,
                matched=False,
                provider=self.name,
                tracking_code="MOCK-NOT-MATCHED",
                message="شماره موبایل و کد ملی متعلق به یک نفر نیستند.",
            )

        return IdentityResult(
            success=True,
            matched=True,
            provider=self.name,
            tracking_code="MOCK-MATCHED",
            message="تطبیق با موفقیت انجام شد.",
        )


class ShahkarIdentityProvider(IdentityProvider):
    """
    نمونه اتصال به سرویس واقعی استعلام شاهکار.

    ساختار درخواست هر ارائه‌دهنده کمی فرق دارد. این کلاس یک الگوی کاری
    است: وقتی سرویس را خریدید، آدرس و نام فیلدها را مطابق مستندات همان
    سرویس عوض کنید. بقیه پروژه دست‌نخورده می‌ماند.

    تنظیمات لازم در .env:
        USE_MOCK_IDENTITY=False
        IDENTITY_PROVIDER=shahkar
        IDENTITY_API_BASE_URL=آدرس-سرویس
        IDENTITY_API_KEY=کلید-شما
    """

    name = "shahkar"

    def __init__(self) -> None:
        self.base_url = settings.IDENTITY_API_BASE_URL.rstrip("/")
        self.api_key = settings.IDENTITY_API_KEY
        self.timeout = settings.IDENTITY_API_TIMEOUT

        if not self.base_url or not self.api_key:
            raise ValueError(
                "IDENTITY_API_BASE_URL و IDENTITY_API_KEY باید در فایل .env تنظیم شوند."
            )

    def verify(self, mobile: str, national_code: str) -> IdentityResult:
        url = f"{self.base_url}/shahkar/verify"

        # کلید در هدر Authorization فرستاده می‌شود، نه در آدرس.
        # اگر در آدرس باشد، در لاگ سرور و تاریخچه مرورگر ذخیره می‌شود.
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        payload = {"mobile": mobile, "nationalCode": national_code}

        try:
            response = requests.post(
                url, json=payload, headers=headers, timeout=self.timeout
            )
            response.raise_for_status()
            data = response.json()

        except requests.Timeout:
            logger.error("سرویس استعلام هویت در زمان مقرر پاسخ نداد.")
            return IdentityResult(
                success=False,
                provider=self.name,
                message=(
                    "در حال حاضر امکان ارتباط با سرویس احراز هویت وجود ندارد. "
                    "لطفاً چند دقیقه دیگر مجدداً تلاش کنید."
                ),
            )

        except requests.ConnectionError:
            logger.error("اتصال به سرویس استعلام هویت برقرار نشد.")
            return IdentityResult(
                success=False,
                provider=self.name,
                message=(
                    "ارتباط با سرویس احراز هویت برقرار نشد. "
                    "لطفاً چند دقیقه دیگر مجدداً تلاش کنید."
                ),
            )

        except requests.HTTPError as exc:
            status = exc.response.status_code if exc.response is not None else 0

            if status == 401:
                # این خطای کاربر نیست؛ کلید سرویس مشکل دارد و باید فوراً
                # به مدیر سایت اطلاع داده شود.
                logger.critical("کلید سرویس استعلام هویت نامعتبر است.")
            elif status == 429:
                logger.warning("سقف درخواست سرویس استعلام هویت پر شده است.")
            else:
                logger.error("سرویس استعلام هویت خطای HTTP %s داد.", status)

            return IdentityResult(
                success=False,
                provider=self.name,
                message=(
                    "سرویس احراز هویت در دسترس نیست. "
                    "لطفاً چند دقیقه دیگر مجدداً تلاش کنید."
                ),
            )

        except ValueError:
            logger.error("پاسخ سرویس استعلام هویت قابل خواندن نبود.")
            return IdentityResult(
                success=False,
                provider=self.name,
                message="پاسخ سرویس احراز هویت نامعتبر بود.",
            )

        # نام فیلدهای زیر را مطابق مستندات سرویسی که خریدید تنظیم کنید.
        matched = bool(data.get("matched") or data.get("result") is True)

        return IdentityResult(
            success=True,
            matched=matched,
            provider=self.name,
            tracking_code=str(data.get("trackId") or data.get("trackingCode") or ""),
            message=(
                "تطبیق با موفقیت انجام شد."
                if matched
                else "شماره موبایل و کد ملی متعلق به یک نفر نیستند."
            ),
            raw=data,
        )


# برای افزودن سرویس جدید فقط یک سطر اینجا اضافه کنید.
PROVIDERS: dict[str, type[IdentityProvider]] = {
    "mock": MockIdentityProvider,
    "shahkar": ShahkarIdentityProvider,
}


def get_identity_service() -> IdentityProvider:
    """
    سرویس مناسب را بر اساس تنظیمات برمی‌گرداند.

    در محیط توسعه همیشه نسخه آزمایشی برگردانده می‌شود — حتی اگر کلید
    سرویس واقعی در .env باشد. هر استعلام واقعی هزینه دارد و نباید
    به اشتباه هنگام تست خرج شود.
    """
    if settings.USE_MOCK_IDENTITY:
        return MockIdentityProvider()

    provider_class = PROVIDERS.get(settings.IDENTITY_PROVIDER)

    if provider_class is None:
        logger.error(
            "سرویس استعلام «%s» شناخته نشد. به حالت آزمایشی برگشتیم.",
            settings.IDENTITY_PROVIDER,
        )
        return MockIdentityProvider()

    return provider_class()


def verify_identity(
    mobile: str,
    national_code: str,
    user=None,
    ip_address: str | None = None,
) -> IdentityResult:
    """
    استعلام هویت و ثبت سابقه آن.

    این تابع نقطه ورود اصلی است: Viewها همیشه این را صدا می‌زنند، نه
    مستقیماً Providerها. این‌طور ثبت سابقه هیچ‌وقت فراموش نمی‌شود.
    """
    from apps.accounts.models import IdentityStatus, IdentityVerification

    result = get_identity_service().verify(mobile, national_code)

    if not result.success:
        status = IdentityStatus.FAILED
    elif result.matched:
        status = IdentityStatus.MATCHED
    else:
        status = IdentityStatus.NOT_MATCHED

    IdentityVerification.objects.create(
        user=user,
        mobile=mobile,
        national_code=national_code,
        status=status,
        provider=result.provider,
        tracking_code=result.tracking_code,
        message=result.message[:300],
        raw_response=result.raw,
        ip_address=ip_address,
    )

    # کد ملی کامل هرگز لاگ نمی‌شود.
    logger.info(
        "استعلام هویت انجام شد. موبایل=%s وضعیت=%s سرویس=%s",
        f"{mobile[:4]}***{mobile[-4:]}" if len(mobile) == 11 else "نامعتبر",
        status,
        result.provider,
    )

    return result
