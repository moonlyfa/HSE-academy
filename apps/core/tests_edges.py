"""
تست‌های فاز ۲۲ — گوشه‌های کم‌رفت‌وآمد.

اینها شاخه‌هایی هستند که در مسیر عادی کاربر هیچ‌وقت اجرا نمی‌شوند:
ساخت کاربر بدون شماره، تاریخ‌های مرزی شمسی، و مسیر فایل محافظت‌شده.
هر کدام کوچک‌اند، اما وقتی خراب باشند در بدترین لحظه معلوم می‌شوند —
مثلاً تاریخ اشتباه روی گواهیِ چاپ‌شده.
"""

from datetime import date

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.test import TestCase

from apps.core.jalali import gregorian_to_jalali, to_jalali_string, to_persian_digits
from apps.courses.live import upcoming_session_rows, user_sessions
from apps.courses.storages import protected_storage

User = get_user_model()


class UserCreationTests(TestCase):
    """مدل کاربر، پایه همه چیز است."""

    def test_a_user_needs_a_mobile_number(self):
        with self.assertRaises(ValueError):
            User.objects.create_user(mobile="", password="HseTech!2026")

    def test_superuser_gets_the_right_flags(self):
        user = User.objects.create_superuser(mobile="09121234567", password="HseTech!2026")

        self.assertTrue(user.is_staff)
        self.assertTrue(user.is_superuser)
        self.assertTrue(user.is_mobile_verified)

    def test_superuser_cannot_be_created_without_staff_flag(self):
        with self.assertRaises(ValueError):
            User.objects.create_superuser(
                mobile="09121234567", password="HseTech!2026", is_staff=False
            )

    def test_superuser_cannot_be_created_without_superuser_flag(self):
        with self.assertRaises(ValueError):
            User.objects.create_superuser(
                mobile="09121234567", password="HseTech!2026", is_superuser=False
            )

    def test_password_is_hashed_even_for_a_superuser(self):
        user = User.objects.create_superuser(mobile="09121234567", password="HseTech!2026")

        self.assertNotEqual(user.password, "HseTech!2026")
        self.assertTrue(user.check_password("HseTech!2026"))


class JalaliEdgeTests(TestCase):
    """
    تبدیل تاریخ، روی گواهی چاپ می‌شود و پاک نمی‌شود.

    تاریخ‌های انتخاب‌شده مرزی‌اند: اول سال، آخر سال، روز کبیسه و
    سال‌های پیش و پس از ۱۶۰۰ میلادی (دو شاخه متفاوت در فرمول).
    """

    def test_new_year(self):
        self.assertEqual(gregorian_to_jalali(2026, 3, 21), (1405, 1, 1))

    def test_last_day_of_the_year(self):
        self.assertEqual(gregorian_to_jalali(2026, 3, 20), (1404, 12, 29))

    def test_leap_day(self):
        """۳۰ اسفند فقط در سال کبیسه وجود دارد."""
        self.assertEqual(gregorian_to_jalali(2025, 3, 20), (1403, 12, 30))

    def test_a_date_before_1600(self):
        """شاخه دیگر فرمول، که در کار روزمره هیچ‌وقت اجرا نمی‌شود."""
        year, month, day = gregorian_to_jalali(1599, 6, 15)

        self.assertEqual(year, 978)
        self.assertTrue(1 <= month <= 12)
        self.assertTrue(1 <= day <= 31)

    def test_formatted_string_uses_persian_digits(self):
        text = to_jalali_string(date(2026, 3, 21))

        self.assertIn("فروردین", text)
        self.assertIn("۱۴۰۵", text)

    def test_weekday_can_be_included(self):
        text = to_jalali_string(date(2026, 3, 21), with_weekday=True)
        self.assertGreater(len(text.split()), 3)

    def test_empty_value_stays_empty(self):
        self.assertEqual(to_jalali_string(None), "")

    def test_digit_conversion(self):
        self.assertEqual(to_persian_digits("1404/12/30"), "۱۴۰۴/۱۲/۳۰")


class GuestHelpersTests(TestCase):
    """توابعی که ممکن است با کاربر واردنشده صدا زده شوند."""

    def test_online_classes_of_a_guest_are_empty(self):
        guest = AnonymousUser()

        self.assertEqual(user_sessions(guest).count(), 0)
        self.assertEqual(upcoming_session_rows(guest), [])


class ProtectedStorageTests(TestCase):
    """فایل‌های دوره بیرون از پوشه عمومی نگهداری می‌شوند."""

    def test_storage_points_outside_the_public_media_folder(self):
        from django.conf import settings

        self.assertNotIn(str(settings.MEDIA_ROOT), protected_storage.location)

    def test_storage_url_prefix_goes_through_the_permission_check(self):
        """آدرس عمومی این فایل‌ها به Viewی می‌رسد که مجوز را می‌سنجد."""
        self.assertEqual(protected_storage.base_url, "/protected-media/")
