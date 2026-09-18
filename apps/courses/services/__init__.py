"""
سرویس‌های بخش دوره‌ها.

برای اینکه بقیه پروژه لازم نباشد بداند هر تابع در کدام فایل است، همه از
همین‌جا در دسترس‌اند:

    from apps.courses.services import get_skyroom_service
"""

from .skyroom import (  # noqa: F401
    JoinLink,
    ManualLinkProvider,
    SkyroomApiProvider,
    SkyroomProvider,
    get_skyroom_service,
)
