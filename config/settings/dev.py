"""
تنظیمات محیط توسعه (روی سیستم شخصی شما).

اینجا سرعت توسعه و دیدن خطاها مهم است، نه امنیت سخت‌گیرانه.
"""

import sys

from .base import *  # noqa: F401,F403
from .base import MIDDLEWARE, env

DEBUG = env.bool("DJANGO_DEBUG", default=True)

ALLOWED_HOSTS = ["127.0.0.1", "localhost", "0.0.0.0", "testserver"]

# در توسعه، ایمیل‌ها به‌جای ارسال واقعی در ترمینال چاپ می‌شوند.
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

# در توسعه فایل‌های استاتیک را بدون manifest سرو می‌کنیم تا نیازی به collectstatic نباشد.
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}

# در توسعه، خود Django فایل‌های استاتیک را سرو می‌کند و WhiteNoise لازم نیست.
# حذف آن، هشدار «پوشه staticfiles وجود ندارد» را هم از بین می‌برد.
MIDDLEWARE = [m for m in MIDDLEWARE if "whitenoise" not in m]

# در توسعه رمزهای ساده مثل «1234» را هم بپذیریم تا تست سریع‌تر باشد.
AUTH_PASSWORD_VALIDATORS = []

# لاگ کامل کوئری‌های SQL در صورت نیاز (پیش‌فرض خاموش است تا ترمینال شلوغ نشود).
if env.bool("DJANGO_LOG_SQL", default=False):
    LOGGING["loggers"]["django.db.backends"] = {  # noqa: F405
        "handlers": ["console"],
        "level": "DEBUG",
        "propagate": False,
    }


# ---------------------------------------------------------------------------
# سرعت اجرای تست‌ها
# ---------------------------------------------------------------------------
# هش کردن رمز عبور عمداً کند است تا حدس زدن رمز سخت شود. اما در تست‌ها
# ده‌ها کاربر ساخته می‌شود و همین کندی، اجرای تست‌ها را چند برابر می‌کند.
# فقط هنگام اجرای تست از الگوریتم سریع استفاده می‌کنیم؛ این تنظیم هیچ
# تأثیری روی رمزهای واقعی سایت ندارد.
if "test" in sys.argv:
    PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
