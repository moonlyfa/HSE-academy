"""
تنظیمات پایه پروژه آکادمی HSE.

این فایل شامل تنظیماتی است که در همه محیط‌ها (Development و Production) مشترک است.
تنظیمات اختصاصی هر محیط در فایل‌های dev.py و prod.py قرار دارد.

هیچ مقدار حساسی (SECRET_KEY، رمز دیتابیس، کلید API) نباید مستقیماً در این فایل
نوشته شود؛ همه از طریق فایل .env خوانده می‌شوند.
"""

from pathlib import Path

import environ

# BASE_DIR ریشه پروژه است (پوشه‌ای که manage.py در آن قرار دارد).
# این فایل در config/settings/base.py است، پس سه بار parent می‌گیریم.
BASE_DIR = Path(__file__).resolve().parent.parent.parent

# ---------------------------------------------------------------------------
# خواندن متغیرهای محیطی از فایل .env
# ---------------------------------------------------------------------------
env = environ.Env()
environ.Env.read_env(BASE_DIR / ".env")

SECRET_KEY = env("DJANGO_SECRET_KEY", default="insecure-dev-key-change-me")
DEBUG = env.bool("DJANGO_DEBUG", default=False)
ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS", default=["127.0.0.1", "localhost"])

# ---------------------------------------------------------------------------
# اپلیکیشن‌ها
# ---------------------------------------------------------------------------
DJANGO_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.sitemaps",
    "django.contrib.humanize",
    "django.contrib.staticfiles",
]

THIRD_PARTY_APPS: list[str] = []

# اپلیکیشن‌های خود پروژه. در فازهای بعدی به این لیست اضافه می‌شود.
LOCAL_APPS = [
    "apps.core",
    "apps.accounts",
    "apps.courses",
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    # WhiteNoise فایل‌های استاتیک را در Production بدون نیاز به تنظیم اضافه Nginx سرو می‌کند.
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                # اطلاعات عمومی سایت (نام، شماره تماس و ...) در همه قالب‌ها در دسترس باشد.
                "apps.core.context_processors.site_context",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# ---------------------------------------------------------------------------
# دیتابیس
# ---------------------------------------------------------------------------
# در Development مقدار پیش‌فرض SQLite است و در Production از طریق DATABASE_URL
# به PostgreSQL وصل می‌شویم.
DATABASES = {
    "default": env.db_url(
        "DATABASE_URL",
        default=f"sqlite:///{BASE_DIR / 'db.sqlite3'}",
    )
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ---------------------------------------------------------------------------
# مدل کاربر سفارشی
# ---------------------------------------------------------------------------
# این تنظیم باید از همان اولین migrate پروژه وجود داشته باشد؛ تغییر آن بعد از
# ساخت دیتابیس بسیار پرهزینه است.
AUTH_USER_MODEL = "accounts.User"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LOGIN_URL = "/accounts/login/"
LOGIN_REDIRECT_URL = "/dashboard/"
LOGOUT_REDIRECT_URL = "/"

# ---------------------------------------------------------------------------
# زبان، منطقه زمانی و بومی‌سازی
# ---------------------------------------------------------------------------
LANGUAGE_CODE = "fa-ir"
TIME_ZONE = "Asia/Tehran"
USE_I18N = True
USE_TZ = True
LOCALE_PATHS = [BASE_DIR / "locale"]

# ---------------------------------------------------------------------------
# فایل‌های استاتیک و مدیا
# ---------------------------------------------------------------------------
STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}

# حداکثر حجم داده‌ای که در حافظه نگه داشته می‌شود؛ بیشتر از این روی دیسک موقت می‌رود.
DATA_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024  # 10 مگابایت
FILE_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024  # 10 مگابایت

# ---------------------------------------------------------------------------
# پیام‌های Django (messages framework) با کلاس‌های Bootstrap
# ---------------------------------------------------------------------------
from django.contrib.messages import constants as message_constants  # noqa: E402

MESSAGE_TAGS = {
    message_constants.DEBUG: "secondary",
    message_constants.INFO: "info",
    message_constants.SUCCESS: "success",
    message_constants.WARNING: "warning",
    message_constants.ERROR: "danger",
}

# ---------------------------------------------------------------------------
# تنظیمات اختصاصی پروژه (Feature Flags و اطلاعات سایت)
# ---------------------------------------------------------------------------
# آدرس پنل مدیریت. در Production آن را به چیزی غیرقابل حدس تغییر دهید.
ADMIN_URL = env("DJANGO_ADMIN_URL", default="admin").strip("/")

SITE_NAME = env("SITE_NAME", default="آکادمی HSE")
SITE_DOMAIN = env("SITE_DOMAIN", default="127.0.0.1:8000")
SITE_SUPPORT_PHONE = env("SITE_SUPPORT_PHONE", default="۰۲۱-۰۰۰۰۰۰۰۰")
SITE_SUPPORT_EMAIL = env("SITE_SUPPORT_EMAIL", default="info@example.com")

# سرویس‌های خارجی: در حالت Mock بدون نیاز به خرید API قابل تست هستند.
USE_MOCK_SMS = env.bool("USE_MOCK_SMS", default=True)
USE_MOCK_IDENTITY = env.bool("USE_MOCK_IDENTITY", default=True)
USE_MOCK_PAYMENT = env.bool("USE_MOCK_PAYMENT", default=True)

# بخش مقالات و اخبار در نسخه اول منتشر نمی‌شود اما زیرساخت آن ساخته می‌شود.
BLOG_ENABLED = env.bool("BLOG_ENABLED", default=False)

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
# هرگز اطلاعات حساس (کد OTP خام، رمز عبور، توکن پرداخت) را لاگ نکنید.
LOGS_DIR = BASE_DIR / "logs"
LOGS_DIR.mkdir(exist_ok=True)

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "{asctime} [{levelname}] {name}: {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "verbose",
        },
        "file": {
            "class": "logging.handlers.RotatingFileHandler",
            "filename": LOGS_DIR / "app.log",
            "maxBytes": 5 * 1024 * 1024,  # 5 مگابایت
            "backupCount": 5,
            "formatter": "verbose",
            "encoding": "utf-8",
        },
    },
    "root": {"handlers": ["console"], "level": "INFO"},
    "loggers": {
        # لاگر اختصاصی پروژه. در کد از logging.getLogger("hse.payments") استفاده می‌کنیم.
        "hse": {
            "handlers": ["console", "file"],
            "level": "INFO",
            "propagate": False,
        },
    },
}
