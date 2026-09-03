"""
تنظیمات محیط Production (سرور واقعی).

قوانین این فایل:
- DEBUG همیشه False است.
- همه مقادیر حساس فقط از Environment Variables خوانده می‌شوند.
- کوکی‌ها فقط روی HTTPS ارسال می‌شوند.
"""

from .base import *  # noqa: F401,F403
from .base import env

DEBUG = False

# در Production حتماً باید مقدار داشته باشند؛ اگر نباشند پروژه عمداً بالا نمی‌آید.
SECRET_KEY = env("DJANGO_SECRET_KEY")
ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS")

CSRF_TRUSTED_ORIGINS = env.list("DJANGO_CSRF_TRUSTED_ORIGINS", default=[])

# ---------------------------------------------------------------------------
# امنیت
# ---------------------------------------------------------------------------
SECURE_SSL_REDIRECT = env.bool("DJANGO_SECURE_SSL_REDIRECT", default=True)
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = False  # برای ارسال هدر CSRF با HTMX لازم است.
SECURE_HSTS_SECONDS = 60 * 60 * 24 * 30  # 30 روز
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"

# چون پشت Nginx هستیم، Django باید بفهمد درخواست اصلی HTTPS بوده است.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# ---------------------------------------------------------------------------
# ایمیل
# ---------------------------------------------------------------------------
EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
EMAIL_HOST = env("EMAIL_HOST", default="")
EMAIL_PORT = env.int("EMAIL_PORT", default=587)
EMAIL_HOST_USER = env("EMAIL_HOST_USER", default="")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD", default="")
EMAIL_USE_TLS = env.bool("EMAIL_USE_TLS", default=True)
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", default="no-reply@example.com")

# ---------------------------------------------------------------------------
# سرویس‌های خارجی در Production واقعی هستند، نه Mock.
# ---------------------------------------------------------------------------
USE_MOCK_SMS = env.bool("USE_MOCK_SMS", default=False)
USE_MOCK_IDENTITY = env.bool("USE_MOCK_IDENTITY", default=False)
USE_MOCK_PAYMENT = env.bool("USE_MOCK_PAYMENT", default=False)

# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------
# در Production، Gunicorn چند Worker جداگانه اجرا می‌کند. اگر کش حافظه‌ای
# (LocMemCache) بماند، هر Worker شمارنده خودش را دارد و محدودیت تلاش ورود
# عملاً چند برابر می‌شود. پس از کشی استفاده می‌کنیم که بین همه Workerها
# مشترک باشد.
#
# پیش‌نیاز استقرار (یک‌بار اجرا شود):
#     python manage.py createcachetable
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.db.DatabaseCache",
        "LOCATION": "django_cache_table",
        "TIMEOUT": 300,
        "OPTIONS": {"MAX_ENTRIES": 10000},
    }
}

# ---------------------------------------------------------------------------
# Logging: در سرور، لاگ‌ها در فایل ذخیره می‌شوند.
# ---------------------------------------------------------------------------
LOGGING["root"]["handlers"] = ["console", "file"]  # noqa: F405
LOGGING["loggers"]["django"] = {  # noqa: F405
    "handlers": ["console", "file"],
    "level": "WARNING",
    "propagate": False,
}
