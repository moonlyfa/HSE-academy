"""
سرویس کلاس آنلاین.

ساختار دقیقاً مثل سرویس پیامک، احراز هویت و درگاه پرداخت است:

    SkyroomProvider      ← قرارداد مشترک
    ManualLinkProvider   ← لینکی که مدیر از پنل اسکای‌روم کپی کرده است
    SkyroomApiProvider   ← ساخت لینک ورود شخصی از راه API اسکای‌روم
    get_skyroom_service()← بر اساس تنظیمات، نسخه درست را برمی‌گرداند

**چرا دو حالت؟**

حالت دستی همین امروز و بدون خرید هیچ سرویسی کار می‌کند: مدیر در پنل
اسکای‌روم کلاس می‌سازد، لینکش را کپی می‌کند و در پنل مدیریت سایت
می‌گذارد. سایت آن لینک را فقط به کسی می‌دهد که در دوره ثبت‌نام دارد.

ضعف این حالت این است که لینک برای همه یکی است؛ اگر دانشجویی آن را در
گروه بفرستد، بقیه هم می‌توانند وارد شوند. حالت API همین ضعف را می‌بندد:
برای هر دانشجو یک آدرس ورود جداگانه و کوتاه‌مدت ساخته می‌شود. تعویض این
دو، یک خط در فایل .env است و هیچ View و مدل و قالبی دست نمی‌خورد.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass

import requests
from django.conf import settings

logger = logging.getLogger("hse.skyroom")


@dataclass
class JoinLink:
    """
    نتیجه استاندارد درخواست ورود به کلاس.

    همه Providerها همین شکل را برمی‌گردانند تا View نیازی نداشته باشد
    بداند لینک از پنل مدیریت آمده یا از API.
    """

    success: bool
    url: str = ""
    provider: str = ""
    message: str = ""


class SkyroomProvider(ABC):
    """قرارداد مشترک همه سامانه‌های کلاس آنلاین."""

    name: str = "base"

    @abstractmethod
    def join_link(self, session, user) -> JoinLink:
        """آدرسی که این کاربر باید برای ورود به این جلسه باز کند."""


class ManualLinkProvider(SkyroomProvider):
    """
    لینک ثابتی که مدیر در پنل مدیریت وارد کرده است.

    ساده‌ترین حالت ممکن و همان چیزی که آکادمی‌ها امروز با آن کار
    می‌کنند. تفاوتش با «گذاشتن لینک در صفحه» این است که اینجا لینک از
    دید کاربر پنهان است و فقط بعد از بررسی ثبت‌نام تحویل داده می‌شود.
    """

    name = "manual"

    def join_link(self, session, user) -> JoinLink:
        if not session.meeting_url:
            return JoinLink(
                False,
                provider=self.name,
                message="لینک این جلسه هنوز توسط مدیر ثبت نشده است.",
            )
        return JoinLink(True, url=session.meeting_url, provider=self.name)


class SkyroomApiProvider(SkyroomProvider):
    """
    اتصال خودکار به API اسکای‌روم.

    برای هر دانشجو یک «لینک ورود» جداگانه ساخته می‌شود که فقط تا مدت
    مشخصی اعتبار دارد (SKYROOM_LINK_TTL_SECONDS). نام کاربر هم به کلاس
    فرستاده می‌شود تا مدرس در فهرست حاضرین، نام واقعی را ببیند نه یک
    شماره.

    اگر API در دسترس نباشد، به لینک دستی برمی‌گردیم: کلاس نباید به‌خاطر
    قطعی یک سرویس جانبی از دست برود.
    """

    name = "skyroom"

    def __init__(self) -> None:
        self.api_key = settings.SKYROOM_API_KEY
        if not self.api_key:
            raise ValueError(
                "SKYROOM_API_KEY تنظیم نشده است. مقدار آن را در فایل .env قرار دهید."
            )
        self.endpoint = f"{settings.SKYROOM_API_URL.rstrip('/')}/{self.api_key}"

    def join_link(self, session, user) -> JoinLink:
        if not session.room_id:
            return ManualLinkProvider().join_link(session, user)

        payload = {
            "action": "createLoginUrl",
            "params": {
                "room_id": session.room_id,
                "user_id": user.pk,
                "nickname": user.get_full_name() or user.masked_mobile,
                "access": 1,  # ۱ = شرکت‌کننده. مدرس را از پنل خودتان تعیین کنید.
                "language": "fa",
                "ttl": settings.SKYROOM_LINK_TTL_SECONDS,
            },
        }

        try:
            response = requests.post(
                self.endpoint,
                json=payload,
                timeout=settings.SKYROOM_TIMEOUT_SECONDS,
            )
            data = response.json()
        except (requests.RequestException, ValueError) as exc:
            logger.error("خطا در تماس با اسکای‌روم. جلسه=%s خطا=%s", session.pk, exc)
            return self._fallback(session, user, "ارتباط با سامانه کلاس برقرار نشد.")

        if not data.get("ok"):
            logger.error(
                "اسکای‌روم درخواست را نپذیرفت. جلسه=%s پاسخ=%s",
                session.pk,
                data.get("error_message") or data.get("error_code"),
            )
            return self._fallback(session, user, "سامانه کلاس پاسخ معتبری نداد.")

        return JoinLink(True, url=data.get("result", ""), provider=self.name)

    def _fallback(self, session, user, message: str) -> JoinLink:
        """وقتی API جواب نداد، لینک ثابتِ همان جلسه (اگر هست) به کار می‌آید."""
        manual = ManualLinkProvider().join_link(session, user)
        if manual.success:
            logger.warning("ورود به کلاس با لینک دستی انجام شد. جلسه=%s", session.pk)
            return manual
        return JoinLink(False, provider=self.name, message=message)


PROVIDERS: dict[str, type[SkyroomProvider]] = {
    "manual": ManualLinkProvider,
    "skyroom": SkyroomApiProvider,
}


def get_skyroom_service() -> SkyroomProvider:
    """
    سرویس کلاس آنلاین را بر اساس تنظیمات برمی‌گرداند.

    اگر مقدار تنظیمات نامعتبر بود یا کلید API نبود، به حالت دستی
    برمی‌گردیم — یعنی بدترین حالت این است که لینک ثابت داده شود، نه
    اینکه کلاس اصلاً باز نشود.
    """
    provider_class = PROVIDERS.get(settings.SKYROOM_PROVIDER)

    if provider_class is None:
        logger.error(
            "سرویس کلاس آنلاین «%s» شناخته نشد. به حالت دستی برگشتیم.",
            settings.SKYROOM_PROVIDER,
        )
        return ManualLinkProvider()

    try:
        return provider_class()
    except ValueError as exc:
        logger.error("%s به حالت دستی برگشتیم.", exc)
        return ManualLinkProvider()
