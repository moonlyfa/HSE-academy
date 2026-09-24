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
    "apps.orders",
    "apps.exams",
    "apps.certificates",
    "apps.blog",
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
    # هدرهای امنیتی که جنگو خودش نمی‌فرستد: CSP و Permissions-Policy.
    "apps.core.middleware.SecurityHeadersMiddleware",
    # محدودسازی تلاش ورود به پنل مدیریت (فرم ورود پنل، فرم خود جنگو است).
    "apps.core.middleware.AdminLoginThrottleMiddleware",
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

# ---------------------------------------------------------------------------
# نشست (Session) و کوکی‌ها
# ---------------------------------------------------------------------------
# دو هفته اعتبار: کاربری که دوره خریده نباید هر روز دوباره وارد شود، اما
# نشست ابدی هم روی یک کامپیوتر مشترک خطرناک است.
SESSION_COOKIE_AGE = env.int("SESSION_COOKIE_AGE", default=60 * 60 * 24 * 14)

# SameSite=Lax یعنی کوکی در درخواست‌هایی که از سایت دیگری آمده‌اند فرستاده
# نمی‌شود (مگر پیمایش ساده). این یک لایه دفاع اضافه در برابر CSRF است،
# روی محافظت خود جنگو.
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_HTTPONLY = True

LOGIN_URL = "/accounts/login/"
LOGIN_REDIRECT_URL = "/accounts/dashboard/"
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

# ---------------------------------------------------------------------------
# فایل‌های محافظت‌شده (ویدیو و جزوه دوره‌ها)
# ---------------------------------------------------------------------------
#
# چرا جدا از media؟
# هر چیزی که داخل media/ باشد با یک آدرس ثابت در دسترس است. یعنی اگر ویدیوی
# یک دوره پولی آنجا ذخیره شود، کافی است یک نفر آدرس را کپی کند و برای صد نفر
# دیگر بفرستد — همه بدون خرید تماشا می‌کنند و کل مدل فروش دوره از بین می‌رود.
#
# پس فایل‌های آموزشی در پوشه‌ای بیرون از دسترس مستقیم وب ذخیره می‌شوند و فقط
# از راه یک View که مجوز کاربر را بررسی می‌کند سرو می‌شوند.
PROTECTED_MEDIA_ROOT = Path(
    env("PROTECTED_MEDIA_ROOT", default=str(BASE_DIR / "protected_media"))
)

# در Production تحویل فایل به Nginx سپرده می‌شود (X-Accel-Redirect) تا پایتون
# برای هر ویدیو چند دقیقه مشغول نماند. مقدار زیر مسیر داخلی Nginx است.
USE_X_ACCEL_REDIRECT = env.bool("USE_X_ACCEL_REDIRECT", default=False)
X_ACCEL_REDIRECT_PREFIX = env("X_ACCEL_REDIRECT_PREFIX", default="/protected-internal/")

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

SITE_NAME = env("SITE_NAME", default="HSE Tech")
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
# کد یکبارمصرف پیامکی (OTP)
# ---------------------------------------------------------------------------
# این اعداد تعادل بین امنیت و راحتی کاربر هستند. سخت‌گیرتر کردنشان امنیت را
# بالا می‌برد اما کاربر واقعی را هم اذیت می‌کند.
OTP_CODE_LENGTH = env.int("OTP_CODE_LENGTH", default=6)
OTP_EXPIRY_SECONDS = env.int("OTP_EXPIRY_SECONDS", default=120)      # اعتبار کد: ۲ دقیقه
OTP_MAX_ATTEMPTS = env.int("OTP_MAX_ATTEMPTS", default=5)            # حداکثر تلاش برای هر کد
OTP_RESEND_COOLDOWN_SECONDS = env.int("OTP_RESEND_COOLDOWN_SECONDS", default=90)
OTP_MAX_SENDS_PER_HOUR = env.int("OTP_MAX_SENDS_PER_HOUR", default=5)

# --- پنل پیامک ---
SMS_PROVIDER = env("SMS_PROVIDER", default="mock")
SMS_API_KEY = env("SMS_API_KEY", default="")
SMS_SENDER_NUMBER = env("SMS_SENDER_NUMBER", default="")
SMS_OTP_TEMPLATE = env("SMS_OTP_TEMPLATE", default="")
SMS_TIMEOUT_SECONDS = env.int("SMS_TIMEOUT_SECONDS", default=10)

# ---------------------------------------------------------------------------
# استعلام تطبیق شماره موبایل و کد ملی
# ---------------------------------------------------------------------------
IDENTITY_PROVIDER = env("IDENTITY_PROVIDER", default="mock")
IDENTITY_API_BASE_URL = env("IDENTITY_API_BASE_URL", default="")
IDENTITY_API_KEY = env("IDENTITY_API_KEY", default="")
IDENTITY_API_TIMEOUT = env.int("IDENTITY_API_TIMEOUT", default=10)

# رفتار سرویس آزمایشی: matched | not_matched | failed | by_national_code
MOCK_IDENTITY_RESULT = env("MOCK_IDENTITY_RESULT", default="matched")

# آیا برای تکمیل ثبت‌نام، احراز هویت اجباری باشد؟
# True  = طبق خواسته کارفرما؛ بدون تطبیق کد ملی، حساب ساخته نمی‌شود.
# False = حساب ساخته می‌شود اما تا احراز هویت، گواهی صادر نخواهد شد.
IDENTITY_REQUIRED_FOR_REGISTRATION = env.bool(
    "IDENTITY_REQUIRED_FOR_REGISTRATION", default=True
)

# ---------------------------------------------------------------------------
# درگاه پرداخت
# ---------------------------------------------------------------------------
PAYMENT_PROVIDER = env("PAYMENT_PROVIDER", default="mock")
PAYMENT_TIMEOUT_SECONDS = env.int("PAYMENT_TIMEOUT_SECONDS", default=15)

# مهلت اعتبار یک تراکنش. اگر کاربر صفحه درگاه را باز بگذارد و نیم‌ساعت
# بعد برگردد، تراکنش دیگر پذیرفته نمی‌شود و باید از نو شروع کند.
PAYMENT_EXPIRY_MINUTES = env.int("PAYMENT_EXPIRY_MINUTES", default=20)

# --- زرین‌پال (فاز ۱۳) ---
ZARINPAL_MERCHANT_ID = env("ZARINPAL_MERCHANT_ID", default="")
ZARINPAL_SANDBOX = env.bool("ZARINPAL_SANDBOX", default=True)

# واحد مبلغی که به زرین‌پال فرستاده می‌شود. قیمت‌های سایت تومان است، پس
# IRT یعنی «همان عدد، با اعلام صریح اینکه تومان است». IRR یعنی سایت عدد را
# پیش از ارسال ده برابر می‌کند. واحد همیشه صریح فرستاده می‌شود؛ هیچ‌چیز به
# پیش‌فرض درگاه سپرده نمی‌شود، چون اشتباهش یعنی یک‌دهم یا ده برابر مبلغ.
ZARINPAL_CURRENCY = env("ZARINPAL_CURRENCY", default="IRT")

# رفتار درگاه آزمایشی هنگام تست خودکار: success | failed | ask
# مقدار ask یعنی صفحه‌ای نمایش داده می‌شود تا خودتان نتیجه را انتخاب کنید.
MOCK_PAYMENT_RESULT = env("MOCK_PAYMENT_RESULT", default="ask")

# ---------------------------------------------------------------------------
# کلاس آنلاین (اسکای‌روم)
# ---------------------------------------------------------------------------
# manual = لینک کلاس را خودتان از پنل اسکای‌روم کپی و در پنل مدیریت وارد
#          می‌کنید. این حالت هیچ سرویسی نمی‌خواهد و همین امروز کار می‌کند.
# skyroom = سایت با API اسکای‌روم حرف می‌زند و برای هر دانشجو یک لینک
#          ورود شخصی و کوتاه‌مدت می‌سازد.
SKYROOM_PROVIDER = env("SKYROOM_PROVIDER", default="manual")
SKYROOM_API_URL = env(
    "SKYROOM_API_URL", default="https://www.skyroom.online/skyroom/api"
)
SKYROOM_API_KEY = env("SKYROOM_API_KEY", default="")
SKYROOM_TIMEOUT_SECONDS = env.int("SKYROOM_TIMEOUT_SECONDS", default=10)

# اعتبار لینک ورود شخصی (ثانیه). کوتاه است تا اگر کسی لینکش را برای
# دیگری فرستاد، تا فردا قابل استفاده نماند.
SKYROOM_LINK_TTL_SECONDS = env.int("SKYROOM_LINK_TTL_SECONDS", default=3600)

# دکمه ورود چند دقیقه قبل از شروع کلاس فعال شود و تا چند دقیقه بعد از
# پایان آن باز بماند.
ONLINE_SESSION_JOIN_LEAD_MINUTES = env.int(
    "ONLINE_SESSION_JOIN_LEAD_MINUTES", default=30
)
ONLINE_SESSION_GRACE_MINUTES = env.int("ONLINE_SESSION_GRACE_MINUTES", default=30)

# ---------------------------------------------------------------------------
# آزمون
# ---------------------------------------------------------------------------
# مهلت آزمون در سرور نگه داشته می‌شود، اما ثبت نهایی دانشجو چند ثانیه در
# راه است. این ارفاق باعث می‌شود پاسخِ کسی که در ثانیه آخر دکمه را زده
# دور ریخته نشود. خیلی بزرگ نکنید؛ هر ثانیه‌اش یعنی وقت اضافه.
EXAM_SUBMIT_GRACE_SECONDS = env.int("EXAM_SUBMIT_GRACE_SECONDS", default=60)

# ---------------------------------------------------------------------------
# امنیت و محدودسازی نرخ درخواست
# ---------------------------------------------------------------------------
# آیا هدر X-Forwarded-For قابل اعتماد است؟ فقط وقتی سایت پشت Proxy خودمان
# (Nginx) باشد. اگر همیشه باور شود، هرکسی می‌تواند با هدر ساختگی سقف‌ها را
# دور بزند: هر درخواست، یک IP جدید. در Production روشن است.
TRUST_X_FORWARDED_FOR = env.bool("TRUST_X_FORWARDED_FOR", default=False)

# سقف‌های ساعتی به‌ازای هر IP. صفر یعنی بدون محدودیت.
#
# اعداد عمداً سخاوتمندند: در ایران یک شرکت یا آموزشگاه معمولاً با یک IP
# مشترک به اینترنت وصل است، و ثبت‌نام گروهی ده‌ها کارمند از همان IP یک
# اتفاق عادی است — نه حمله. سقف باید جلوی اسکریپت را بگیرد، نه جلوی
# مشتری سازمانی را.
CONTACT_MAX_PER_HOUR = env.int("CONTACT_MAX_PER_HOUR", default=10)
REGISTRATION_MAX_PER_HOUR = env.int("REGISTRATION_MAX_PER_HOUR", default=40)
PASSWORD_RESET_MAX_PER_HOUR = env.int("PASSWORD_RESET_MAX_PER_HOUR", default=20)

# ورود به پنل مدیریت: تعداد مدیران کم است و هیچ مدیری در یک ساعت بیست بار
# رمز را اشتباه نمی‌زند؛ پس سقف می‌تواند سخت‌گیر باشد.
ADMIN_LOGIN_MAX_PER_HOUR = env.int("ADMIN_LOGIN_MAX_PER_HOUR", default=20)

# --- Content Security Policy ---
# سایت هیچ فایل جاوااسکریپت یا CSS خارجی ندارد، پس می‌توانیم سخت‌گیرترین
# حالت را بگذاریم: مرورگر اجازه ندارد اسکریپتی از جای دیگری اجرا کند. اگر
# روزی کسی موفق شود متنی داخل صفحه تزریق کند، همین یک هدر جلوی اجرایش را
# می‌گیرد.
#
# style-src ناچاراً 'unsafe-inline' دارد چون چند قالب از style درون‌خطی
# برای مقدار متغیرهای CSS استفاده می‌کنند. خطر CSS تزریقی در مقایسه با
# اسکریپت ناچیز است و کل خروجی قالب‌ها هم Escape می‌شود.
CSP_ENABLED = env.bool("CSP_ENABLED", default=True)

# حالت گزارش‌محور: سیاست اعمال نمی‌شود، فقط تخلف‌ها در کنسول مرورگر دیده
# می‌شوند. برای اولین روزهای استقرار مفید است.
CSP_REPORT_ONLY = env.bool("CSP_REPORT_ONLY", default=False)

CSP_DIRECTIVES = [
    "default-src 'self'",
    "script-src 'self'",
    "style-src 'self' 'unsafe-inline'",
    "img-src 'self' data:",
    "font-src 'self'",
    "connect-src 'self'",
    "form-action 'self'",
    "base-uri 'self'",
    "object-src 'none'",
    "frame-src 'none'",
    # همان کاری که X_FRAME_OPTIONS می‌کند، با پشتیبانی بهتر مرورگرهای تازه.
    "frame-ancestors 'none'",
]

# سایت به دوربین، میکروفون و موقعیت مکانی نیازی ندارد؛ بستنشان جلوی
# سوءاستفاده یک اسکریپت تزریق‌شده یا افزونه مرورگر را می‌گیرد.
PERMISSIONS_POLICY = "camera=(), microphone=(), geolocation=(), payment=(), usb=()"

# ---------------------------------------------------------------------------
# سئو
# ---------------------------------------------------------------------------
# روی سرور آزمایشی این را False کنید: robots.txt کل سایت را می‌بندد و همه
# صفحه‌ها تگ noindex می‌گیرند. اگر نسخه آزمایشی ایندکس شود، گوگل دو سایت
# با محتوای یکسان می‌بیند و اعتبار سایت اصلی را هم پایین می‌آورد.
SEO_ALLOW_INDEXING = env.bool("SEO_ALLOW_INDEXING", default=True)

# ---------------------------------------------------------------------------
# استعلام گواهی
# ---------------------------------------------------------------------------
# صفحه استعلام عمومی است و کد گواهی ترتیبی؛ بدون سقف، یک برنامه ساده
# می‌تواند کدها را یکی‌یکی امتحان کند و ببیند کدام‌ها واقعی‌اند. این عدد
# در حدی است که هیچ کارفرمای واقعی به آن نمی‌خورد. صفر یعنی بدون محدودیت.
CERTIFICATE_LOOKUP_MAX_PER_HOUR = env.int("CERTIFICATE_LOOKUP_MAX_PER_HOUR", default=30)

# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------
# از کش برای محدودسازی تلاش‌های ناموفق ورود و در فاز ۴ برای محدودیت ارسال
# پیامک استفاده می‌شود.
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "hse-local-cache",
    }
}

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
