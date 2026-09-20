"""
تست‌های فاز ۲۲ — دستورهای مدیریتی و بالا آمدن پروژه در Production.

این‌ها کدهایی‌اند که هیچ‌وقت در مرورگر اجرا نمی‌شوند، پس هیچ تست صفحه‌ای
به آن‌ها نمی‌رسد — و دقیقاً وقتی صدا زده می‌شوند که کسی پشت ترمینال
سرور نشسته و انتظار دارد کار کنند:

    python manage.py enrollments        ← گزارش وضعیت دسترسی‌ها
    python manage.py setup_groups       ← ساخت گروه‌های نقش
    python manage.py make_admin ...     ← ساخت حساب مدیر

و آخرین مورد: خودِ `config/settings/prod.py`. یک اشتباه تایپی در آن
فایل یعنی سایت روی سرور اصلاً بالا نمی‌آید، و آن لحظه بدترین وقت برای
فهمیدنش است.
"""

from datetime import timedelta
from io import StringIO

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.courses.enrollment import enroll, revoke
from apps.courses.models import Course, CourseCategory

User = get_user_model()


def run(command: str, *args, **options) -> str:
    """دستور را اجرا می‌کند و خروجی ترمینالش را برمی‌گرداند."""
    out = StringIO()
    call_command(command, *args, stdout=out, stderr=out, **options)
    return out.getvalue()


class EnrollmentsReportTests(TestCase):
    """گزارشی که کارفرما برای دیدن وضعیت فروش و دسترسی‌ها اجرا می‌کند."""

    @classmethod
    def setUpTestData(cls):
        cls.category = CourseCategory.objects.create(name="ایمنی", slug="safety")
        cls.lifetime_course = Course.objects.create(
            title="دوره دائمی", slug="lifetime", category=cls.category, is_published=True
        )
        cls.timed_course = Course.objects.create(
            title="دوره مدت‌دار",
            slug="timed",
            category=cls.category,
            access_duration_days=30,
            is_published=True,
        )

        cls.student = User.objects.create_user(mobile="09121234567")
        cls.other = User.objects.create_user(mobile="09127654321")

    def test_report_runs_on_an_empty_database(self):
        """روز اول راه‌اندازی، هنوز هیچ ثبت‌نامی نیست."""
        output = run("enrollments")

        self.assertIn("وضعیت دسترسی دانشجویان", output)
        self.assertIn("هیچ دسترسی‌ای تمام نمی‌شود", output)

    def test_report_counts_each_kind_of_access(self):
        enroll(self.student, self.lifetime_course)
        enroll(self.student, self.timed_course)
        revoke(enroll(self.other, self.lifetime_course))

        output = run("enrollments")

        self.assertIn("دسترسی دائمی", output)
        self.assertIn("تعلیق‌شده", output)
        self.assertIn(self.lifetime_course.title, output)

    def test_report_warns_about_access_ending_soon(self):
        enrollment = enroll(self.student, self.timed_course)
        enrollment.expires_at = timezone.now() + timedelta(days=3)
        enrollment.save(update_fields=["expires_at"])

        output = run("enrollments", "--expiring", "7")

        self.assertIn("تا 7 روز آینده تمام می‌شوند", output)
        self.assertIn(self.student.masked_mobile, output)

    def test_report_never_prints_a_full_mobile_number(self):
        """شماره کامل در خروجی ترمینال و لاگ‌ها نمی‌آید."""
        enrollment = enroll(self.student, self.timed_course)
        enrollment.expires_at = timezone.now() + timedelta(days=2)
        enrollment.save(update_fields=["expires_at"])

        output = run("enrollments")

        self.assertNotIn(self.student.mobile, output)
        self.assertIn("***", output)

    def test_expiring_window_is_configurable(self):
        enrollment = enroll(self.student, self.timed_course)
        enrollment.expires_at = timezone.now() + timedelta(days=20)
        enrollment.save(update_fields=["expires_at"])

        self.assertIn("هیچ دسترسی‌ای تمام نمی‌شود", run("enrollments", "--expiring", "7"))
        self.assertIn(self.timed_course.title, run("enrollments", "--expiring", "30"))


class GroupSetupTests(TestCase):
    """گروه‌های نقش، پیش از دادن دسترسی به همکاران ساخته می‌شوند."""

    def test_groups_are_created(self):
        run("setup_groups")

        self.assertTrue(Group.objects.exists())

    def test_running_it_twice_is_safe(self):
        """دستور راه‌اندازی باید قابل اجرای دوباره باشد."""
        run("setup_groups")
        count = Group.objects.count()

        run("setup_groups")

        self.assertEqual(Group.objects.count(), count)


@override_settings(DEBUG=True)
class MakeAdminTests(TestCase):
    """
    ساخت حساب مدیر در محیط توسعه.

    جنگو هنگام اجرای تست‌ها `DEBUG` را False می‌کند، و این دستور عمداً
    در آن حالت کار نمی‌کند؛ پس اینجا موقتاً روشنش می‌کنیم.
    """

    def test_creates_a_staff_account(self):
        run("make_admin", "09121234567", "HseTech!2026")

        user = User.objects.get(mobile="09121234567")
        self.assertTrue(user.is_staff)
        self.assertTrue(user.is_superuser)
        self.assertTrue(user.check_password("HseTech!2026"))

    def test_promotes_an_existing_user_without_a_second_account(self):
        User.objects.create_user(mobile="09121234567", password="OldPass!2026")

        run("make_admin", "09121234567", "HseTech!2026")

        self.assertEqual(User.objects.filter(mobile="09121234567").count(), 1)
        self.assertTrue(User.objects.get(mobile="09121234567").is_staff)

    def test_listing_admins(self):
        User.objects.create_user(mobile="09121234567", is_staff=True)

        output = run("make_admin", list=True)

        self.assertIn("0912", output)

    @override_settings(DEBUG=False)
    def test_refuses_to_run_on_a_production_server_without_force(self):
        """
        ساخت مدیر با رمزِ روی خط فرمان، روی سرور واقعی خطرناک است
        (در تاریخچه Shell می‌ماند).
        """
        from django.core.management.base import CommandError

        with self.assertRaises(CommandError):
            run("make_admin", "09121234567", "HseTech!2026")


class ProductionSettingsTests(TestCase):
    """
    تنظیمات Production باید بدون خطا خوانده شوند — و جلوی تنظیم خطرناک
    را بگیرند.

    هیچ تست دیگری این فایل را اجرا نمی‌کند (تست‌ها با تنظیمات توسعه
    اجرا می‌شوند)، پس یک اشتباه در آن تا لحظه استقرار پنهان می‌ماند.
    """

    SAFE_ENV = {
        "DJANGO_SECRET_KEY": "x" * 60,
        "DJANGO_ALLOWED_HOSTS": "hse.example.ir",
        "USE_MOCK_SMS": "False",
        "USE_MOCK_IDENTITY": "False",
        "USE_MOCK_PAYMENT": "False",
    }

    def load(self, **overrides):
        """
        تنظیمات Production را با متغیرهای محیطی دلخواه می‌خواند.

        وارد کردن ماژول هم **داخل** بلوک است، نه بیرونش: فایل تنظیمات
        در همان لحظه import اجرا می‌شود و محافظ‌هایش همان‌جا خطا
        می‌دهند.
        """
        import importlib
        import os
        from unittest.mock import patch

        with patch.dict(os.environ, {**self.SAFE_ENV, **overrides}):
            module = importlib.import_module("config.settings.prod")
            return importlib.reload(module)

    def test_production_settings_import_cleanly(self):
        prod = self.load()

        self.assertFalse(prod.DEBUG)
        self.assertTrue(prod.SESSION_COOKIE_SECURE)
        self.assertTrue(prod.CSRF_COOKIE_SECURE)
        self.assertGreater(prod.SECURE_HSTS_SECONDS, 0)
        self.assertEqual(prod.X_FRAME_OPTIONS, "DENY")

    def test_production_uses_a_cache_shared_between_workers(self):
        """
        با کش حافظه‌ای، هر Worker شمارنده خودش را دارد و همه سقف‌های
        محدودسازی نرخ عملاً چند برابر می‌شوند.
        """
        prod = self.load()

        self.assertNotIn("locmem", prod.CACHES["default"]["BACKEND"].lower())

    def test_the_site_refuses_to_start_with_the_mock_payment_gateway(self):
        """
        محتمل‌ترین اشتباه استقرار: کپی کردن فایل .env توسعه روی سرور.

        درگاه آزمایشی روی سایت واقعی یعنی هرکسی با یک کلیک «پرداخت
        موفق»، دوره را رایگان برمی‌دارد — و هیچ خطایی هم در لاگ نیست.
        """
        from django.core.exceptions import ImproperlyConfigured

        with self.assertRaises(ImproperlyConfigured) as raised:
            self.load(USE_MOCK_PAYMENT="True")

        self.assertIn("USE_MOCK_PAYMENT", str(raised.exception))

    def test_mock_sms_needs_an_explicit_decision(self):
        """
        پیامک آزمایشی ممکن است عمدی باشد (پنل هنوز خریداری نشده)، اما
        باید صریح اعلام شود نه اینکه از فایل .env توسعه سر بخورد.
        """
        from django.core.exceptions import ImproperlyConfigured

        with self.assertRaises(ImproperlyConfigured):
            self.load(USE_MOCK_SMS="True")

        prod = self.load(USE_MOCK_SMS="True", ALLOW_MOCK_SERVICES="True")
        self.assertTrue(prod.USE_MOCK_SMS)

    def tearDown(self):
        """تنظیمات را به حالت سالم برمی‌گردانیم تا تست بعدی اثر نگیرد."""
        self.load()
