"""
تست‌های فاز ۲۳ — استقرار.

فایل‌های `deploy/` کد پایتون نیستند و هیچ تستی اجرایشان نمی‌کند. اما
بعضی از مقادیر داخلشان **باید** با تنظیمات پروژه یکی باشند، و اگر یکی
نباشند، خرابی‌شان ساکت است:

    مسیر internal در Nginx ≠ X_ACCEL_REDIRECT_PREFIX
        → ویدیوی دوره برای هیچ‌کس باز نمی‌شود (یا بدتر، برای همه)

    proxy_add_x_forwarded_for به‌جای remote_addr
        → همه سقف‌های محدودسازی نرخ با یک هدر دستی دور زده می‌شوند

این فایل همان هم‌خوانی‌ها را می‌سنجد، و دستور `deploy_check` را — که
خودش قرار است همین کار را روی سرور انجام دهد.
"""

from io import StringIO
from pathlib import Path

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings

DEPLOY_DIR = Path(settings.BASE_DIR) / "deploy"


def read(name: str) -> str:
    return (DEPLOY_DIR / name).read_text(encoding="utf-8")


def directives(name: str) -> str:
    """
    فایل پیکربندی بدون خطوط توضیح.

    توضیح‌های این فایل‌ها عمداً درباره «چه چیزی را **نباید** نوشت»
    حرف می‌زنند؛ اگر متن خام را بگردیم، همان توضیح‌ها تست را می‌شکنند.
    """
    return "\n".join(
        line for line in read(name).splitlines() if not line.strip().startswith("#")
    )


class DeployFilesExistTests(TestCase):
    """هر چیزی که راهنمای استقرار به آن ارجاع می‌دهد باید واقعاً باشد."""

    EXPECTED = [
        "nginx.conf",
        "gunicorn.conf.py",
        "gunicorn.service",
        "gunicorn.socket",
        "backup.sh",
        "update.sh",
        "hse-backup.service",
        "hse-backup.timer",
        "hse-verify-payments.service",
        "hse-verify-payments.timer",
        "logrotate-hse",
    ]

    def test_every_config_file_is_present(self):
        for name in self.EXPECTED:
            with self.subTest(file=name):
                self.assertTrue((DEPLOY_DIR / name).exists(), f"{name} نیست")

    def test_scripts_are_executable(self):
        import os

        for name in ("backup.sh", "update.sh"):
            with self.subTest(file=name):
                self.assertTrue(
                    os.access(DEPLOY_DIR / name, os.X_OK),
                    f"{name} قابل اجرا نیست (chmod +x)",
                )

    def test_the_runbook_exists(self):
        runbook = Path(settings.BASE_DIR) / "docs" / "deployment.md"
        self.assertTrue(runbook.exists())


class NginxConfigTests(TestCase):
    """
    هم‌خوانی پیکربندی Nginx با تنظیمات پروژه.

    اینها را نمی‌شود با اجرای کد فهمید؛ فقط با خواندن هر دو طرف.
    """

    def setUp(self):
        self.config = read("nginx.conf")


    def test_internal_location_matches_the_x_accel_prefix(self):
        """
        اگر این دو یکی نباشند، جنگو هدر را به مسیری می‌فرستد که Nginx
        نمی‌شناسد و دانلود ویدیو با ۴۰۴ شکست می‌خورد.
        """
        prefix = settings.X_ACCEL_REDIRECT_PREFIX

        self.assertIn(f"location {prefix}", self.config)
        self.assertIn("internal;", self.config)

    def test_protected_files_are_never_served_directly(self):
        """پوشه محافظت‌شده نباید هیچ بلوک عمومی داشته باشد."""
        for line in self.config.splitlines():
            stripped = line.strip()
            if stripped.startswith("location") and "protected_media" in stripped:
                self.fail(f"پوشه محافظت‌شده مستقیم سرو می‌شود: {stripped}")

    def test_forwarded_for_header_is_overwritten_not_appended(self):
        """
        `$proxy_add_x_forwarded_for` مقدار ساختگی کاربر را نگه می‌دارد و
        سقف‌های محدودسازی نرخ را بی‌اثر می‌کند (فاز ۲۱).
        """
        config = directives("nginx.conf")

        self.assertIn("proxy_set_header X-Forwarded-For $remote_addr;", config)
        self.assertNotIn("$proxy_add_x_forwarded_for", config)

    def test_upload_size_is_large_enough_for_course_videos(self):
        self.assertIn("client_max_body_size", self.config)

    def test_http_is_redirected_to_https(self):
        self.assertIn("return 301 https://$host$request_uri;", self.config)

    def test_certbot_challenge_path_is_not_redirected(self):
        """اگر این مسیر هم به HTTPS برود، تمدید خودکار گواهی شکست می‌خورد."""
        self.assertIn("/.well-known/acme-challenge/", self.config)

    def test_static_and_media_are_served_by_nginx(self):
        self.assertIn("location /static/", self.config)
        self.assertIn("location /media/", self.config)

    def test_hidden_files_are_denied(self):
        self.assertIn("location ~ /\\.", self.config)


class GunicornConfigTests(TestCase):
    def test_service_uses_the_shared_gunicorn_config(self):
        service = read("gunicorn.service")

        self.assertIn("deploy/gunicorn.conf.py", service)
        self.assertIn("DJANGO_SETTINGS_MODULE=config.settings.prod", service)

    def test_service_does_not_run_as_root(self):
        service = read("gunicorn.service")

        self.assertIn("User=hse", service)
        self.assertNotIn("User=root", service)

    def test_service_reads_secrets_from_the_env_file(self):
        """
        کلیدها نباید داخل فایل سرویس باشند؛ آن فایل با systemctl cat
        برای همه قابل خواندن است.
        """
        service = read("gunicorn.service")

        self.assertIn("EnvironmentFile=", service)
        self.assertNotIn("SECRET_KEY=", service)

    def test_socket_is_shared_with_the_web_server_group(self):
        socket = read("gunicorn.socket")

        self.assertIn("SocketGroup=www-data", socket)


class VerifyPaymentsTimerTests(TestCase):
    """تایمری که تراکنش‌های نامعلوم را دوباره از درگاه می‌پرسد."""

    def test_the_service_runs_the_pending_payments_command(self):
        service = read("hse-verify-payments.service")

        self.assertIn("verify_pending_payments", service)
        self.assertIn("config.settings.prod", service)
        self.assertIn("EnvironmentFile=", service)

    def test_it_runs_often_enough_to_matter(self):
        """مشتری‌ای که پاسخ بانکش گم شده، نباید ساعت‌ها منتظر بماند."""
        timer = read("hse-verify-payments.timer")

        self.assertIn("OnUnitActiveSec=10min", timer)


class BackupTests(TestCase):
    """پشتیبانی که یکی از سه بخش را جا بیندازد، بی‌فایده است."""

    def setUp(self):
        self.script = read("backup.sh")

    def test_database_media_and_protected_media_are_all_backed_up(self):
        self.assertIn("pg_dump", self.script)
        self.assertIn("media", self.script)
        self.assertIn("protected_media", self.script)

    def test_env_file_is_included_and_locked_down(self):
        self.assertIn(".env", self.script)
        self.assertIn("chmod 600", self.script)

    def test_old_backups_are_removed(self):
        """بدون پاک‌سازی، دیسک سرور پر می‌شود و سایت می‌خوابد."""
        self.assertIn("KEEP_DAYS", self.script)
        self.assertIn("-mtime", self.script)

    def test_the_script_stops_on_the_first_error(self):
        """بدون این، یک pg_dump شکست‌خورده «پشتیبان موفق» گزارش می‌شود."""
        self.assertIn("set -euo pipefail", self.script)

    def test_the_timer_survives_a_server_that_was_off(self):
        timer = read("hse-backup.timer")

        self.assertIn("OnCalendar=", timer)
        self.assertIn("Persistent=true", timer)


class UpdateScriptTests(TestCase):
    def setUp(self):
        self.script = read("update.sh")

    def test_it_backs_up_before_touching_anything(self):
        backup_at = self.script.index("backup.sh")
        migrate_at = self.script.index("migrate")

        self.assertLess(backup_at, migrate_at, "پشتیبان باید پیش از مهاجرت باشد")

    def test_it_checks_the_settings_before_migrating(self):
        check_at = self.script.index("deploy_check")
        migrate_at = self.script.index("migrate")

        self.assertLess(check_at, migrate_at)

    def test_it_collects_static_files(self):
        self.assertIn("collectstatic", self.script)

    def test_it_stops_on_the_first_error(self):
        self.assertIn("set -euo pipefail", self.script)


class DeployCheckCommandTests(TestCase):
    """
    دستوری که روی سرور اجرا می‌شود و می‌گوید آماده هست یا نه.

    تنظیمات محیط تست عمداً شبیه سرور نیست، پس هر تست همان چیزی را که
    می‌سنجد موقتاً درست (یا خراب) می‌کند.
    """

    def run_check(self, **options) -> str:
        out = StringIO()
        call_command("deploy_check", stdout=out, stderr=out, **options)
        return out.getvalue()

    def output_of_failed_check(self) -> str:
        out = StringIO()
        with self.assertRaises(CommandError):
            call_command("deploy_check", stdout=out, stderr=out)
        return out.getvalue()

    def test_it_refuses_a_site_running_with_the_mock_gateway(self):
        with override_settings(USE_MOCK_PAYMENT=True):
            output = self.output_of_failed_check()

        self.assertIn("درگاه پرداخت در حالت آزمایشی", output)

    def test_it_refuses_a_weak_secret_key(self):
        with override_settings(SECRET_KEY="short"):
            output = self.output_of_failed_check()

        self.assertIn("DJANGO_SECRET_KEY", output)

    def test_it_refuses_a_wildcard_allowed_hosts(self):
        with override_settings(ALLOWED_HOSTS=["*"]):
            output = self.output_of_failed_check()

        self.assertIn("دامنه واقعی", output)

    def test_it_catches_protected_media_inside_the_public_folder(self):
        """
        بدترین اشتباه ممکن در تنظیم مسیرها: ویدیوی دوره پولی با یک
        آدرس ساده برای همه باز می‌شود، بی‌هیچ نشانه‌ای.
        """
        media = Path(settings.MEDIA_ROOT)

        with override_settings(PROTECTED_MEDIA_ROOT=media / "protected"):
            output = self.output_of_failed_check()

        self.assertIn("داخل media", output)

    def test_it_warns_about_a_gateway_without_a_merchant_id(self):
        with override_settings(
            USE_MOCK_PAYMENT=False,
            PAYMENT_PROVIDER="zarinpal",
            ZARINPAL_MERCHANT_ID="",
        ):
            output = self.output_of_failed_check()

        self.assertIn("ZARINPAL_MERCHANT_ID", output)

    def test_it_refuses_the_zarinpal_sandbox_on_a_real_site(self):
        """Sandbox روی سایت واقعی: مشتری دوره را می‌گیرد، پولی نمی‌رسد."""
        with override_settings(**self.healthy_settings(ZARINPAL_SANDBOX=True)):
            output = self.output_of_failed_check()

        self.assertIn("ZARINPAL_SANDBOX", output)

    def test_it_refuses_an_unknown_currency(self):
        with override_settings(**self.healthy_settings(ZARINPAL_CURRENCY="USD")):
            output = self.output_of_failed_check()

        self.assertIn("ZARINPAL_CURRENCY", output)

    def test_it_warns_but_does_not_fail_on_mock_sms(self):
        """
        پیامک آزمایشی ممکن است عمدی باشد (پنل هنوز خریداری نشده)؛
        هشدار درست است، اما جلوی استقرار را نمی‌گیرد.
        """
        healthy = self.healthy_settings(USE_MOCK_SMS=True)

        with override_settings(**healthy):
            output = self.run_check()

        self.assertIn("پیامک در حالت آزمایشی", output)
        self.assertIn("هشدار", output)

    def test_strict_mode_turns_warnings_into_failures(self):
        """در اسکریپت استقرار خودکار، هشدار هم باید متوقف‌کننده باشد."""
        healthy = self.healthy_settings(USE_MOCK_SMS=True)

        with override_settings(**healthy):
            out = StringIO()
            with self.assertRaises(CommandError):
                call_command("deploy_check", "--strict", stdout=out, stderr=out)

    def test_a_healthy_configuration_passes(self):
        """
        هیچ خطایی نباید باشد.

        دو هشدار باقی می‌ماند (SQLite و کش حافظه‌ای) چون محیط تست
        همین است؛ مهم این است که هیچ ✗ ای نباشد و دستور با خطا تمام
        نشود.
        """
        with override_settings(**self.healthy_settings()):
            output = self.run_check()

        self.assertNotIn("✗", output)
        self.assertIn("آماده است", output)

    # --- ابزار ------------------------------------------------------------

    def healthy_settings(self, **overrides) -> dict:
        """
        تنظیماتی که دستور باید آن‌ها را سالم بداند.

        فایل‌های ثابت در محیط تست جمع‌آوری نشده‌اند، پس STATIC_ROOT را به
        پوشه‌ای اشاره می‌دهیم که هست (خود پوشه static پروژه).
        """
        healthy = {
            "DEBUG": False,
            "SECRET_KEY": "k" * 60 + "-unique-enough-3f9a",
            "ALLOWED_HOSTS": ["hse.example.ir"],
            "STATIC_ROOT": Path(settings.BASE_DIR) / "static",
            "STORAGES": {
                **settings.STORAGES,
                "staticfiles": {
                    "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"
                },
            },
            "USE_MOCK_PAYMENT": False,
            "USE_MOCK_SMS": False,
            "USE_MOCK_IDENTITY": False,
            "PAYMENT_PROVIDER": "zarinpal",
            "ZARINPAL_MERCHANT_ID": "test-merchant",
            "ZARINPAL_SANDBOX": False,
            "ZARINPAL_CURRENCY": "IRT",
            "SMS_API_KEY": "test-key",
            "USE_X_ACCEL_REDIRECT": True,
        }
        healthy.update(overrides)
        return healthy
