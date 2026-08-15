"""
تست‌های مدل کاربر.

این تست‌ها تضمین می‌کنند اعتبارسنجی موبایل و کد ملی و ساخت کاربر
درست کار می‌کنند. با هر تغییر بعدی در مدل، این تست‌ها محافظ ما هستند.
"""

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase

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
