"""
بررسی آمادگی سرور پیش از تحویل.

`python manage.py check --deploy` چیزهایی را می‌سنجد که **جنگو** از آن‌ها
خبر دارد: کوکی امن، HSTS، DEBUG. اما چیزهایی هست که فقط این پروژه
می‌داند و اگر اشتباه باشند، سایت بالا می‌آید و ظاهراً کار می‌کند — تا
روزی که معلوم شود نمی‌کرده:

    • جدول کش ساخته نشده  → سقف‌های محدودسازی نرخ بی‌اثرند
    • فایل‌های ثابت جمع نشده → سایت بدون CSS بالا می‌آید
    • پوشه فایل‌های محافظت‌شده داخل media → ویدیوی دوره پولی برای همه باز است
    • کلید درگاه خالی → اولین خرید واقعی شکست می‌خورد

این دستور همان‌ها را می‌گیرد. خروجی‌اش با کد وضعیت ۱ تمام می‌شود اگر
خطایی باشد، تا در اسکریپت استقرار (deploy/update.sh) جلوی ادامه کار را
بگیرد.

    python manage.py deploy_check --settings=config.settings.prod
"""

from __future__ import annotations

from pathlib import Path

from django.conf import settings
from django.core.cache import cache
from django.core.management.base import BaseCommand, CommandError
from django.db import connection


class Command(BaseCommand):
    help = "بررسی آمادگی تنظیمات و سرور برای اجرای واقعی"

    def add_arguments(self, parser):
        parser.add_argument(
            "--strict",
            action="store_true",
            help="هشدارها را هم مثل خطا حساب کن (برای اجرای خودکار در استقرار)",
        )

    # --- ابزار گزارش ---------------------------------------------------

    def ok(self, message: str) -> None:
        self.stdout.write(self.style.SUCCESS(f"  ✓ {message}"))

    def warn(self, message: str) -> None:
        self.warnings.append(message)
        self.stdout.write(self.style.WARNING(f"  ! {message}"))

    def fail(self, message: str) -> None:
        self.errors.append(message)
        self.stdout.write(self.style.ERROR(f"  ✗ {message}"))

    # --- اجرا ------------------------------------------------------------

    def handle(self, *args, **options):
        self.errors: list[str] = []
        self.warnings: list[str] = []

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("بررسی آمادگی استقرار"))
        self.stdout.write("─" * 46)

        self.check_debug()
        self.check_secret_key()
        self.check_allowed_hosts()
        self.check_database()
        self.check_cache()
        self.check_static_files()
        self.check_protected_media()
        self.check_external_services()
        self.check_email()

        self.stdout.write("─" * 46)
        self.report(strict=options["strict"])

    # --- بررسی‌ها ---------------------------------------------------------

    def check_debug(self) -> None:
        if settings.DEBUG:
            self.fail("DEBUG روشن است. در سرور واقعی باید False باشد.")
        else:
            self.ok("DEBUG خاموش است")

    def check_secret_key(self) -> None:
        key = settings.SECRET_KEY

        if len(key) < 50:
            self.fail("DJANGO_SECRET_KEY کوتاه است (کمتر از ۵۰ کاراکتر).")
        elif key.startswith("django-insecure-") or len(set(key)) < 10:
            self.fail("DJANGO_SECRET_KEY قابل حدس است؛ کلید تازه بسازید.")
        else:
            self.ok("کلید امنیتی مناسب است")

    def check_allowed_hosts(self) -> None:
        hosts = [host for host in settings.ALLOWED_HOSTS if host]

        if not hosts:
            self.fail("DJANGO_ALLOWED_HOSTS خالی است.")
        elif "*" in hosts:
            self.fail("DJANGO_ALLOWED_HOSTS روی * تنظیم شده؛ دامنه واقعی را بنویسید.")
        else:
            self.ok(f"دامنه‌های مجاز: {'، '.join(hosts)}")

    def check_database(self) -> None:
        engine = settings.DATABASES["default"]["ENGINE"]

        if "sqlite" in engine:
            self.warn(
                "دیتابیس SQLite است. برای سایت واقعی PostgreSQL توصیه می‌شود "
                "(DATABASE_URL در فایل .env)."
            )
        else:
            self.ok("دیتابیس PostgreSQL است")

        try:
            connection.ensure_connection()
            self.ok("اتصال به دیتابیس برقرار است")
        except Exception as exc:  # noqa: BLE001 — هر خطای اتصال، خطای استقرار است
            self.fail(f"اتصال به دیتابیس برقرار نشد: {exc}")

    def check_cache(self) -> None:
        """
        کش، زیرساخت محدودسازی نرخ است.

        با DatabaseCache، اگر جدولش ساخته نشده باشد، هر خواندن و نوشتن
        خطا می‌دهد — یعنی سقف‌ها عملاً وجود ندارند.
        """
        backend = settings.CACHES["default"]["BACKEND"]

        if "locmem" in backend.lower():
            self.warn(
                "کش حافظه‌ای است. با چند Worker، هر کدام شمارنده خودش را "
                "دارد و سقف‌های محدودسازی نرخ چند برابر می‌شوند."
            )

        try:
            cache.set("deploy-check", "ok", 10)
            if cache.get("deploy-check") == "ok":
                self.ok("کش کار می‌کند")
            else:
                self.fail("کش مقدار ذخیره‌شده را برنگرداند.")
        except Exception as exc:  # noqa: BLE001
            self.fail(
                f"کش کار نمی‌کند ({exc}). اگر DatabaseCache است، یک‌بار "
                "«python manage.py createcachetable» را اجرا کنید."
            )

    def check_static_files(self) -> None:
        static_root = Path(settings.STATIC_ROOT)

        if not static_root.exists() or not any(static_root.iterdir()):
            self.fail(
                "فایل‌های ثابت جمع‌آوری نشده‌اند؛ سایت بدون CSS بالا می‌آید. "
                "«python manage.py collectstatic» را اجرا کنید."
            )
            return

        self.ok("فایل‌های ثابت جمع‌آوری شده‌اند")

        # ManifestStaticFilesStorage بدون این فایل کار نمی‌کند.
        if "Manifest" in settings.STORAGES["staticfiles"]["BACKEND"]:
            if (static_root / "staticfiles.json").exists():
                self.ok("فهرست نسخه‌بندی فایل‌های ثابت موجود است")
            else:
                self.fail("فایل staticfiles.json نیست؛ collectstatic را دوباره اجرا کنید.")

    def check_protected_media(self) -> None:
        """
        مهم‌ترین بررسی این دستور.

        اگر پوشه فایل‌های محافظت‌شده داخل media باشد، Nginx آن را مثل
        بقیه فایل‌های عمومی سرو می‌کند و ویدیوی دوره پولی با یک آدرس
        ساده برای همه باز است — بدون هیچ خطایی، بدون هیچ نشانه‌ای.
        """
        protected = Path(settings.PROTECTED_MEDIA_ROOT).resolve()
        media = Path(settings.MEDIA_ROOT).resolve()
        static_root = Path(settings.STATIC_ROOT).resolve()

        if protected == media or media in protected.parents:
            self.fail(
                "پوشه فایل‌های محافظت‌شده داخل media است؛ محتوای دوره پولی "
                "برای همه قابل دانلود می‌شود."
            )
        elif static_root in protected.parents:
            self.fail("پوشه فایل‌های محافظت‌شده داخل staticfiles است.")
        else:
            self.ok("فایل‌های محافظت‌شده بیرون از مسیرهای عمومی‌اند")

        if not protected.exists():
            self.warn(f"پوشه {protected} هنوز ساخته نشده است.")

        if not settings.USE_X_ACCEL_REDIRECT:
            self.warn(
                "USE_X_ACCEL_REDIRECT خاموش است؛ ارسال هر ویدیو یک Worker "
                "پایتون را تا پایان دانلود مشغول نگه می‌دارد."
            )
        else:
            self.ok(
                "تحویل فایل با Nginx انجام می‌شود "
                f"(مسیر داخلی: {settings.X_ACCEL_REDIRECT_PREFIX})"
            )

    def check_external_services(self) -> None:
        if settings.USE_MOCK_PAYMENT:
            self.fail("درگاه پرداخت در حالت آزمایشی است؛ خرید بدون پرداخت ممکن می‌شود.")
        elif settings.PAYMENT_PROVIDER == "zarinpal" and not settings.ZARINPAL_MERCHANT_ID:
            self.fail("درگاه زرین‌پال انتخاب شده اما ZARINPAL_MERCHANT_ID خالی است.")
        else:
            self.ok(f"درگاه پرداخت: {settings.PAYMENT_PROVIDER}")

        if settings.USE_MOCK_SMS:
            self.warn("پیامک در حالت آزمایشی است؛ کد تأیید واقعی ارسال نمی‌شود.")
        elif not settings.SMS_API_KEY:
            self.fail("پنل پیامک واقعی انتخاب شده اما SMS_API_KEY خالی است.")
        else:
            self.ok(f"پنل پیامک: {settings.SMS_PROVIDER}")

        if settings.USE_MOCK_IDENTITY:
            self.warn("استعلام هویت در حالت آزمایشی است.")
        else:
            self.ok(f"سرویس استعلام هویت: {settings.IDENTITY_PROVIDER}")

    def check_email(self) -> None:
        if "smtp" in settings.EMAIL_BACKEND and not settings.EMAIL_HOST:
            self.warn("ارسال ایمیل تنظیم نشده است (EMAIL_HOST خالی).")
        else:
            self.ok("تنظیمات ایمیل مشکلی ندارد")

    # --- جمع‌بندی ---------------------------------------------------------

    def report(self, *, strict: bool) -> None:
        if self.errors:
            raise CommandError(
                f"{len(self.errors)} مورد باید پیش از تحویل برطرف شود."
            )

        if self.warnings and strict:
            raise CommandError(
                f"{len(self.warnings)} هشدار (حالت سخت‌گیرانه فعال است)."
            )

        if self.warnings:
            self.stdout.write(
                self.style.WARNING(
                    f"آماده است، با {len(self.warnings)} هشدار. موارد بالا را ببینید."
                )
            )
        else:
            self.stdout.write(self.style.SUCCESS("همه‌چیز آماده است."))

        self.stdout.write("")
