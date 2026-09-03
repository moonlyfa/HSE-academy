"""
تست‌های مدل کاربر.

این تست‌ها تضمین می‌کنند اعتبارسنجی موبایل و کد ملی و ساخت کاربر
درست کار می‌کنند. با هر تغییر بعدی در مدل، این تست‌ها محافظ ما هستند.
"""

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from apps.accounts.validators import validate_iranian_mobile, validate_national_code

User = get_user_model()


class UserModelTests(TestCase):
    def test_create_user_with_mobile(self):
        user = User.objects.create_user(mobile="09121234567", password="test-pass-123")
        self.assertEqual(user.mobile, "09121234567")
        self.assertTrue(user.is_active)
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_mobile_verified)
        # رمز عبور باید هش شده باشد، نه ذخیره خام.
        self.assertNotEqual(user.password, "test-pass-123")
        self.assertTrue(user.check_password("test-pass-123"))

    def test_create_superuser(self):
        admin = User.objects.create_superuser(mobile="09121112233", password="admin-pass-123")
        self.assertTrue(admin.is_staff)
        self.assertTrue(admin.is_superuser)
        self.assertEqual(admin.role, "super_admin")

    def test_mobile_must_be_valid(self):
        with self.assertRaises(ValidationError):
            User.objects.create_user(mobile="12345", password="x")

    def test_masked_mobile_hides_middle_digits(self):
        user = User.objects.create_user(mobile="09121234567", password="test-pass-123")
        self.assertEqual(user.masked_mobile, "0912***4567")

    def test_full_name_falls_back_to_mobile_in_str(self):
        user = User.objects.create_user(mobile="09121234567", password="test-pass-123")
        self.assertEqual(str(user), "09121234567")
        user.first_name = "علی"
        user.last_name = "رضایی"
        self.assertEqual(str(user), "علی رضایی")


class ValidatorTests(TestCase):
    def test_valid_mobile_numbers(self):
        validate_iranian_mobile("09121234567")  # نباید خطا بدهد

    def test_invalid_mobile_numbers(self):
        for bad in ["9121234567", "091212345678", "08121234567", "", "0912abcdefg"]:
            with self.subTest(mobile=bad), self.assertRaises(ValidationError):
                validate_iranian_mobile(bad)

    def test_valid_national_codes(self):
        # نمونه کدهای ملی با رقم کنترل صحیح
        for good in ["0499370899", "0790419904", "0084575948"]:
            with self.subTest(code=good):
                validate_national_code(good)

    def test_invalid_national_codes(self):
        for bad in ["1234567890", "0000000000", "1111111111", "12345", "abcdefghij"]:
            with self.subTest(code=bad), self.assertRaises(ValidationError):
                validate_national_code(bad)


class MobileNormalizationTests(TestCase):
    """کاربر ایرانی ممکن است شماره را به شکل‌های مختلف وارد کند."""

    def test_various_formats_normalize_to_standard(self):
        from apps.accounts.forms import normalize_mobile

        cases = {
            "09121234567": "09121234567",
            "۰۹۱۲۱۲۳۴۵۶۷": "09121234567",      # اعداد فارسی
            "٠٩١٢١٢٣٤٥٦٧": "09121234567",      # اعداد عربی
            "0912 123 4567": "09121234567",     # با فاصله
            "0912-123-4567": "09121234567",     # با خط تیره
            "+989121234567": "09121234567",     # با کد کشور
            "00989121234567": "09121234567",
            "989121234567": "09121234567",
            "  09121234567  ": "09121234567",
        }
        for raw, expected in cases.items():
            with self.subTest(raw=raw):
                self.assertEqual(normalize_mobile(raw), expected)


class RegistrationViewTests(TestCase):
    def setUp(self):
        self.url = reverse("accounts:register")
        self.valid = {
            "first_name": "سارا",
            "last_name": "محمدی",
            "mobile": "09121234567",
            "password1": "HseTech!2026",
            "password2": "HseTech!2026",
            "accept_terms": "on",
        }

    def test_page_loads(self):
        self.assertEqual(self.client.get(self.url).status_code, 200)

    def test_successful_registration_creates_user_and_logs_in(self):
        self.client.post(self.url, self.valid)

        user = User.objects.get(mobile="09121234567")
        self.assertEqual(user.first_name, "سارا")
        self.assertIn("_auth_user_id", self.client.session)

    def test_new_account_is_not_mobile_verified(self):
        """تأیید موبایل باید در فاز ۴ با کد پیامکی انجام شود، نه خودکار."""
        self.client.post(self.url, self.valid)
        self.assertFalse(User.objects.get(mobile="09121234567").is_mobile_verified)

    def test_password_is_hashed_not_stored_raw(self):
        self.client.post(self.url, self.valid)
        user = User.objects.get(mobile="09121234567")
        self.assertNotIn("HseTech!2026", user.password)
        self.assertTrue(user.check_password("HseTech!2026"))

    def test_duplicate_mobile_is_rejected(self):
        User.objects.create_user(mobile="09121234567", password="x")
        response = self.client.post(self.url, self.valid)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(User.objects.filter(mobile="09121234567").count(), 1)

    def test_mismatched_passwords_rejected(self):
        data = {**self.valid, "password2": "different-password"}
        self.client.post(self.url, data)
        self.assertFalse(User.objects.filter(mobile="09121234567").exists())

    def test_terms_must_be_accepted(self):
        data = {k: v for k, v in self.valid.items() if k != "accept_terms"}
        self.client.post(self.url, data)
        self.assertFalse(User.objects.filter(mobile="09121234567").exists())

    def test_persian_digits_accepted_in_mobile(self):
        data = {**self.valid, "mobile": "۰۹۱۲۱۲۳۴۵۶۷"}
        self.client.post(self.url, data)
        self.assertTrue(User.objects.filter(mobile="09121234567").exists())


class LoginViewTests(TestCase):
    def setUp(self):
        from django.core.cache import cache

        cache.clear()
        self.url = reverse("accounts:login")
        self.user = User.objects.create_user(mobile="09121234567", password="HseTech!2026")

    def test_login_with_correct_credentials(self):
        self.client.post(self.url, {"mobile": "09121234567", "password": "HseTech!2026"})
        self.assertIn("_auth_user_id", self.client.session)

    def test_login_with_persian_digits(self):
        self.client.post(self.url, {"mobile": "۰۹۱۲۱۲۳۴۵۶۷", "password": "HseTech!2026"})
        self.assertIn("_auth_user_id", self.client.session)

    def test_wrong_password_rejected(self):
        self.client.post(self.url, {"mobile": "09121234567", "password": "wrong"})
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_error_message_does_not_reveal_which_field_was_wrong(self):
        """
        پیام خطا نباید فرق بگذارد بین «شماره وجود ندارد» و «رمز غلط است»،
        وگرنه مهاجم می‌تواند بفهمد چه شماره‌هایی در سایت ثبت‌نام کرده‌اند.
        """
        wrong_password = self.client.post(
            self.url, {"mobile": "09121234567", "password": "wrong"}
        ).content.decode()
        unknown_mobile = self.client.post(
            self.url, {"mobile": "09129999999", "password": "wrong"}
        ).content.decode()

        message = "شماره موبایل یا رمز عبور اشتباه است."
        self.assertIn(message, wrong_password)
        self.assertIn(message, unknown_mobile)

    def test_inactive_user_cannot_log_in(self):
        self.user.is_active = False
        self.user.save()
        self.client.post(self.url, {"mobile": "09121234567", "password": "HseTech!2026"})
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_logged_in_user_is_redirected_away_from_login_page(self):
        self.client.force_login(self.user)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)

    def test_next_parameter_redirects_within_site(self):
        response = self.client.post(
            self.url,
            {"mobile": "09121234567", "password": "HseTech!2026", "next": "/courses/"},
        )
        self.assertEqual(response.headers["Location"], "/courses/")

    def test_external_next_parameter_is_ignored(self):
        """
        تست امنیتی: اگر آدرس بازگشت را بدون بررسی قبول کنیم، مهاجم می‌تواند
        کاربر را بعد از ورود به سایت جعلی بفرستد (Open Redirect).
        """
        response = self.client.post(
            self.url,
            {
                "mobile": "09121234567",
                "password": "HseTech!2026",
                "next": "https://evil.example.com/steal",
            },
        )
        self.assertNotIn("evil.example.com", response.headers["Location"])
        self.assertEqual(response.headers["Location"], reverse("accounts:dashboard"))


class LoginThrottlingTests(TestCase):
    """محافظت در برابر حمله امتحان کردن پیاپی رمزها."""

    def setUp(self):
        from django.core.cache import cache

        cache.clear()
        self.url = reverse("accounts:login")
        User.objects.create_user(mobile="09121234567", password="HseTech!2026")

    def test_account_locks_after_five_failed_attempts(self):
        for _ in range(5):
            self.client.post(self.url, {"mobile": "09121234567", "password": "wrong"})

        response = self.client.post(
            self.url, {"mobile": "09121234567", "password": "wrong"}
        )
        self.assertContains(response, "مسدود شده است")

    def test_correct_password_rejected_while_locked(self):
        for _ in range(5):
            self.client.post(self.url, {"mobile": "09121234567", "password": "wrong"})

        self.client.post(self.url, {"mobile": "09121234567", "password": "HseTech!2026"})
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_successful_login_clears_the_counter(self):
        from apps.accounts.throttling import remaining_attempts

        for _ in range(3):
            self.client.post(self.url, {"mobile": "09121234567", "password": "wrong"})

        self.client.post(self.url, {"mobile": "09121234567", "password": "HseTech!2026"})
        self.assertIn("_auth_user_id", self.client.session)

        request = self.client.request().wsgi_request
        self.assertEqual(remaining_attempts(request, "09121234567"), 5)


class LogoutTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(mobile="09121234567", password="HseTech!2026")
        self.client.force_login(self.user)

    def test_get_request_does_not_log_out(self):
        """
        تست امنیتی: اگر خروج با GET ممکن باشد، مهاجم می‌تواند با گذاشتن
        <img src="/accounts/logout/"> در یک صفحه، کاربر را ناخواسته خارج کند.
        """
        self.client.get(reverse("accounts:logout"))
        self.assertIn("_auth_user_id", self.client.session)

    def test_post_request_logs_out(self):
        self.client.post(reverse("accounts:logout"))
        self.assertNotIn("_auth_user_id", self.client.session)


class ProtectedPageTests(TestCase):
    """صفحات شخصی نباید برای کاربر مهمان باز شوند."""

    def setUp(self):
        self.user = User.objects.create_user(mobile="09121234567", password="HseTech!2026")

    def test_anonymous_user_redirected_to_login(self):
        for name in ("accounts:dashboard", "accounts:profile", "accounts:change_password"):
            with self.subTest(page=name):
                response = self.client.get(reverse(name))
                self.assertEqual(response.status_code, 302)
                self.assertIn("/accounts/login/", response.headers["Location"])

    def test_logged_in_user_can_open_pages(self):
        self.client.force_login(self.user)
        for name in ("accounts:dashboard", "accounts:profile", "accounts:change_password"):
            with self.subTest(page=name):
                self.assertEqual(self.client.get(reverse(name)).status_code, 200)


class ProfileTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(mobile="09121234567", password="HseTech!2026")
        self.client.force_login(self.user)

    def test_profile_update_saves(self):
        self.client.post(
            reverse("accounts:profile"),
            {"first_name": "علی", "last_name": "رضایی", "email": "ali@example.com"},
        )
        self.user.refresh_from_db()
        self.assertEqual(self.user.full_name, "علی رضایی")

    def test_mobile_cannot_be_changed_through_profile_form(self):
        """موبایل نام کاربری است؛ تغییرش باید با تأیید پیامکی باشد (فاز ۴)."""
        self.client.post(
            reverse("accounts:profile"),
            {"first_name": "علی", "last_name": "رضایی", "mobile": "09129999999"},
        )
        self.user.refresh_from_db()
        self.assertEqual(self.user.mobile, "09121234567")

    def test_password_change_requires_current_password(self):
        self.client.post(
            reverse("accounts:change_password"),
            {
                "current_password": "wrong-password",
                "new_password1": "NewPass!2026",
                "new_password2": "NewPass!2026",
            },
        )
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("HseTech!2026"))

    def test_password_change_works_and_keeps_user_logged_in(self):
        self.client.post(
            reverse("accounts:change_password"),
            {
                "current_password": "HseTech!2026",
                "new_password1": "NewPass!2026",
                "new_password2": "NewPass!2026",
            },
        )
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("NewPass!2026"))
        # بدون update_session_auth_hash کاربر از حساب خودش بیرون می‌افتاد
        self.assertIn("_auth_user_id", self.client.session)


class RoleGroupTests(TestCase):
    def test_setup_groups_creates_all_roles(self):
        from io import StringIO

        from django.contrib.auth.models import Group
        from django.core.management import call_command

        call_command("setup_groups", stdout=StringIO())

        for name in ("مدیر", "مدرس", "مدیر محتوا", "پشتیبانی", "مالی", "دانشجو"):
            with self.subTest(group=name):
                self.assertTrue(Group.objects.filter(name=name).exists())

    def test_instructor_group_cannot_delete_courses(self):
        from io import StringIO

        from django.contrib.auth.models import Group
        from django.core.management import call_command

        call_command("setup_groups", stdout=StringIO())
        instructor = Group.objects.get(name="مدرس")
        codenames = set(instructor.permissions.values_list("codename", flat=True))

        self.assertIn("change_course", codenames)
        self.assertNotIn("delete_course", codenames)

    def test_running_twice_is_safe(self):
        from io import StringIO

        from django.contrib.auth.models import Group
        from django.core.management import call_command

        call_command("setup_groups", stdout=StringIO())
        call_command("setup_groups", stdout=StringIO())
        self.assertEqual(Group.objects.filter(name="مدیر").count(), 1)
