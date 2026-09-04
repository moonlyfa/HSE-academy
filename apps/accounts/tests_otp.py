"""
تست‌های کد یکبارمصرف پیامکی.

برای دسترسی به کد خام در تست، سرویس پیامک را با یک نسخه ضبط‌کننده
جایگزین می‌کنیم. این تنها راه درست است: کد خام در دیتابیس وجود ندارد،
پس تست هم نباید بتواند آن را از دیتابیس بخواند.
"""

from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import OtpCode, OtpPurpose
from apps.accounts.services.sms import SmsProvider, SmsResult

User = get_user_model()


class CapturingSmsProvider(SmsProvider):
    """سرویس پیامک آزمایشی که کدهای ارسالی را برای تست نگه می‌دارد."""

    name = "capture"
    sent: list[tuple[str, str]] = []

    def send(self, mobile: str, text: str) -> SmsResult:
        self.sent.append((mobile, text))
        return SmsResult(success=True, provider=self.name)

    def send_otp(self, mobile: str, code: str) -> SmsResult:
        self.sent.append((mobile, code))
        return SmsResult(success=True, provider=self.name)


class OtpTestMixin:
    """ابزار مشترک: گرفتن کد ارسال‌شده و پاک کردن حافظه بین تست‌ها."""

    def setUp(self):
        super().setUp()
        CapturingSmsProvider.sent = []
        patcher = patch(
            "apps.accounts.services.otp.get_sms_service",
            return_value=CapturingSmsProvider(),
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    @property
    def last_code(self) -> str:
        self.assertTrue(CapturingSmsProvider.sent, "هیچ پیامکی ارسال نشده است.")
        return CapturingSmsProvider.sent[-1][1]

    def _bypass_cooldown(self, mobile: str, purpose: str) -> None:
        """
        عقب بردن زمان ساخت کد قبلی، تا محدودیت ۹۰ ثانیه مانع تست نشود.

        خودِ محدودیت در تست جداگانه بررسی می‌شود.
        """
        OtpCode.objects.filter(mobile=mobile, purpose=purpose).update(
            created_at=timezone.now() - timedelta(minutes=5)
        )


class OtpServiceTests(OtpTestMixin, TestCase):
    """تست مستقیم سرویس، بدون عبور از صفحات."""

    def test_code_is_never_stored_in_plain_text(self):
        from apps.accounts.services.otp import send_otp

        send_otp("09121234567", OtpPurpose.REGISTER)
        otp = OtpCode.objects.get()

        self.assertNotIn(self.last_code, otp.code_hash)
        self.assertEqual(len(otp.code_hash), 64)  # طول خروجی SHA-256

    def test_code_has_configured_length(self):
        from apps.accounts.services.otp import send_otp

        send_otp("09121234567", OtpPurpose.REGISTER)

        self.assertEqual(len(self.last_code), 6)
        self.assertTrue(self.last_code.isdigit())

    def test_correct_code_verifies(self):
        from apps.accounts.services.otp import send_otp, verify_otp

        send_otp("09121234567", OtpPurpose.REGISTER)
        result = verify_otp("09121234567", OtpPurpose.REGISTER, self.last_code)

        self.assertTrue(result.success)

    def test_code_cannot_be_used_twice(self):
        from apps.accounts.services.otp import send_otp, verify_otp

        send_otp("09121234567", OtpPurpose.REGISTER)
        code = self.last_code

        self.assertTrue(verify_otp("09121234567", OtpPurpose.REGISTER, code).success)
        self.assertFalse(verify_otp("09121234567", OtpPurpose.REGISTER, code).success)

    def test_code_for_one_purpose_does_not_work_for_another(self):
        """کد بازیابی رمز نباید برای ثبت‌نام قابل استفاده باشد."""
        from apps.accounts.services.otp import send_otp, verify_otp

        send_otp("09121234567", OtpPurpose.PASSWORD_RESET)
        code = self.last_code

        self.assertFalse(verify_otp("09121234567", OtpPurpose.REGISTER, code).success)

    def test_code_for_one_mobile_does_not_work_for_another(self):
        from apps.accounts.services.otp import send_otp, verify_otp

        send_otp("09121234567", OtpPurpose.REGISTER)
        code = self.last_code

        self.assertFalse(verify_otp("09129999999", OtpPurpose.REGISTER, code).success)

    def test_expired_code_is_rejected(self):
        from apps.accounts.services.otp import send_otp, verify_otp

        send_otp("09121234567", OtpPurpose.REGISTER)
        code = self.last_code

        OtpCode.objects.update(expires_at=timezone.now() - timedelta(seconds=1))
        result = verify_otp("09121234567", OtpPurpose.REGISTER, code)

        self.assertFalse(result.success)
        self.assertIn("اعتبار کد تمام", result.message)

    def test_attempts_are_limited(self):
        from apps.accounts.services.otp import send_otp, verify_otp

        send_otp("09121234567", OtpPurpose.REGISTER)
        code = self.last_code

        for _ in range(5):
            verify_otp("09121234567", OtpPurpose.REGISTER, "000000")

        # حتی کد درست هم بعد از اتمام تلاش‌ها پذیرفته نمی‌شود
        self.assertFalse(verify_otp("09121234567", OtpPurpose.REGISTER, code).success)

    def test_resend_is_blocked_during_cooldown(self):
        from apps.accounts.services.otp import send_otp

        self.assertTrue(send_otp("09121234567", OtpPurpose.REGISTER).success)
        second = send_otp("09121234567", OtpPurpose.REGISTER)

        self.assertFalse(second.success)
        self.assertGreater(second.cooldown_seconds, 0)

    def test_new_code_invalidates_the_previous_one(self):
        from apps.accounts.services.otp import send_otp, verify_otp

        send_otp("09121234567", OtpPurpose.REGISTER)
        first_code = self.last_code

        self._bypass_cooldown("09121234567", OtpPurpose.REGISTER)
        send_otp("09121234567", OtpPurpose.REGISTER)

        self.assertFalse(
            verify_otp("09121234567", OtpPurpose.REGISTER, first_code).success
        )

    @override_settings(OTP_MAX_SENDS_PER_HOUR=3)
    def test_hourly_send_limit(self):
        from apps.accounts.services.otp import send_otp

        for _ in range(3):
            send_otp("09121234567", OtpPurpose.REGISTER)
            self._bypass_cooldown("09121234567", OtpPurpose.REGISTER)

        blocked = send_otp("09121234567", OtpPurpose.REGISTER)
        self.assertFalse(blocked.success)
        self.assertIn("زیاد بوده", blocked.message)

    def test_failed_sms_invalidates_the_code(self):
        """اگر پیامک نرفت، کد نباید فعال بماند و سهمیه ارسال نباید بسوزد."""
        from apps.accounts.services.otp import send_otp

        class FailingProvider(SmsProvider):
            name = "failing"

            def send(self, mobile, text):
                return SmsResult(success=False, provider=self.name, message="خطا")

            def send_otp(self, mobile, code):
                return self.send(mobile, code)

        with patch(
            "apps.accounts.services.otp.get_sms_service", return_value=FailingProvider()
        ):
            result = send_otp("09121234567", OtpPurpose.REGISTER)

        self.assertFalse(result.success)
        self.assertTrue(OtpCode.objects.get().is_used)


class RegistrationFlowTests(OtpTestMixin, TestCase):
    """جریان سه‌مرحله‌ای ثبت‌نام."""

    def _complete_step_one(self, mobile="09121234567"):
        return self.client.post(reverse("accounts:register"), {"mobile": mobile})

    def test_step_one_sends_code_and_redirects(self):
        response = self._complete_step_one()

        self.assertRedirects(response, reverse("accounts:register_verify"))
        self.assertEqual(OtpCode.objects.count(), 1)

    def test_step_one_rejects_already_registered_mobile(self):
        User.objects.create_user(mobile="09121234567", password="x")
        self._complete_step_one()

        self.assertEqual(OtpCode.objects.count(), 0)

    def test_cannot_skip_to_verify_without_entering_mobile(self):
        response = self.client.get(reverse("accounts:register_verify"))
        self.assertRedirects(response, reverse("accounts:register"))

    def test_cannot_skip_to_complete_without_verifying_code(self):
        """
        مهم‌ترین تست امنیتی این فاز: کسی نباید بتواند با رفتن مستقیم به
        آدرس گام سوم، بدون تأیید پیامکی حساب بسازد.
        """
        self._complete_step_one()

        response = self.client.get(reverse("accounts:register_complete"))
        self.assertRedirects(response, reverse("accounts:register"))

        self.client.post(
            reverse("accounts:register_complete"),
            {
                "first_name": "علی",
                "last_name": "رضایی",
                "password1": "HseTech!2026",
                "password2": "HseTech!2026",
                "accept_terms": "on",
            },
        )
        self.assertFalse(User.objects.filter(mobile="09121234567").exists())

    def test_full_flow_creates_verified_user(self):
        self._complete_step_one()

        self.client.post(reverse("accounts:register_verify"), {"code": self.last_code})

        self.client.post(
            reverse("accounts:register_complete"),
            {
                "first_name": "نگین",
                "last_name": "هوشنگی",
                "password1": "HseTech!2026",
                "password2": "HseTech!2026",
                "accept_terms": "on",
            },
        )

        user = User.objects.get(mobile="09121234567")
        self.assertTrue(user.is_mobile_verified)
        self.assertEqual(user.first_name, "نگین")
        self.assertIn("_auth_user_id", self.client.session)

    def test_wrong_code_does_not_advance(self):
        self._complete_step_one()

        self.client.post(reverse("accounts:register_verify"), {"code": "000000"})
        response = self.client.get(reverse("accounts:register_complete"))

        self.assertRedirects(response, reverse("accounts:register"))

    def test_verified_state_expires(self):
        """وضعیت تأییدشده نباید تا ابد در Session بماند."""
        self._complete_step_one()
        self.client.post(reverse("accounts:register_verify"), {"code": self.last_code})

        session = self.client.session
        stale = timezone.now() - timedelta(hours=2)
        session["otp_verified_register"]["at"] = stale.isoformat()
        session.save()

        response = self.client.get(reverse("accounts:register_complete"))
        self.assertRedirects(response, reverse("accounts:register"))


class PasswordResetFlowTests(OtpTestMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.user = User.objects.create_user(
            mobile="09121234567", password="OldPass!2026"
        )

    def test_reset_flow_changes_password(self):
        self.client.post(reverse("accounts:password_reset"), {"mobile": "09121234567"})
        self.client.post(
            reverse("accounts:password_reset_verify"), {"code": self.last_code}
        )
        self.client.post(
            reverse("accounts:password_reset_new"),
            {"new_password1": "BrandNew!2026", "new_password2": "BrandNew!2026"},
        )

        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("BrandNew!2026"))

    def test_unknown_mobile_gets_same_response_and_no_sms(self):
        """
        نباید بتوان از این فرم فهمید چه شماره‌هایی در سایت حساب دارند.
        """
        known = self.client.post(
            reverse("accounts:password_reset"), {"mobile": "09121234567"}, follow=True
        )
        CapturingSmsProvider.sent = []
        unknown = self.client.post(
            reverse("accounts:password_reset"), {"mobile": "09129999999"}, follow=True
        )

        self.assertIn("اگر این شماره", known.content.decode())
        self.assertIn("اگر این شماره", unknown.content.decode())
        self.assertEqual(CapturingSmsProvider.sent, [])

    def test_cannot_set_new_password_without_verifying(self):
        self.client.post(reverse("accounts:password_reset"), {"mobile": "09121234567"})

        self.client.post(
            reverse("accounts:password_reset_new"),
            {"new_password1": "Hacked!2026", "new_password2": "Hacked!2026"},
        )

        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("OldPass!2026"))


class VerifyMobileTests(OtpTestMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.user = User.objects.create_user(
            mobile="09121234567", password="HseTech!2026"
        )
        self.client.force_login(self.user)
        self.url = reverse("accounts:verify_mobile")

    def test_user_can_verify_own_mobile(self):
        self.client.post(self.url, {"send": "1"})
        self.client.post(self.url, {"code": self.last_code})

        self.user.refresh_from_db()
        self.assertTrue(self.user.is_mobile_verified)

    def test_wrong_code_leaves_mobile_unverified(self):
        self.client.post(self.url, {"send": "1"})
        self.client.post(self.url, {"code": "000000"})

        self.user.refresh_from_db()
        self.assertFalse(self.user.is_mobile_verified)

    def test_already_verified_user_is_redirected(self):
        self.user.is_mobile_verified = True
        self.user.save()

        response = self.client.get(self.url)
        self.assertRedirects(response, reverse("accounts:dashboard"))

    def test_anonymous_user_cannot_access(self):
        self.client.logout()
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)


class SmsProviderSelectionTests(TestCase):
    @override_settings(USE_MOCK_SMS=True, SMS_PROVIDER="kavenegar")
    def test_mock_wins_in_development_even_with_real_provider_configured(self):
        """
        در محیط توسعه هرگز نباید به اشتباه از اعتبار پنل واقعی خرج شود.
        """
        from apps.accounts.services.sms import MockSmsProvider, get_sms_service

        self.assertIsInstance(get_sms_service(), MockSmsProvider)

    @override_settings(USE_MOCK_SMS=False, SMS_PROVIDER="does-not-exist")
    def test_unknown_provider_falls_back_to_mock_instead_of_crashing(self):
        from apps.accounts.services.sms import MockSmsProvider, get_sms_service

        self.assertIsInstance(get_sms_service(), MockSmsProvider)

    @override_settings(USE_MOCK_SMS=False, SMS_PROVIDER="kavenegar", SMS_API_KEY="test-key")
    def test_real_provider_is_selected_in_production_mode(self):
        from apps.accounts.services.sms import KavenegarSmsProvider, get_sms_service

        self.assertIsInstance(get_sms_service(), KavenegarSmsProvider)

    @override_settings(USE_MOCK_SMS=False, SMS_PROVIDER="kavenegar", SMS_API_KEY="")
    def test_real_provider_refuses_to_start_without_api_key(self):
        from apps.accounts.services.sms import get_sms_service

        with self.assertRaises(ValueError):
            get_sms_service()


class RegistrationValidationTests(OtpTestMixin, TestCase):
    """بررسی‌هایی که در گام سوم ثبت‌نام باید همچنان اعمال شوند."""

    def setUp(self):
        super().setUp()
        self.client.post(reverse("accounts:register"), {"mobile": "09121234567"})
        self.client.post(reverse("accounts:register_verify"), {"code": self.last_code})
        self.url = reverse("accounts:register_complete")
        self.valid = {
            "first_name": "نگین",
            "last_name": "هوشنگی",
            "password1": "HseTech!2026",
            "password2": "HseTech!2026",
            "accept_terms": "on",
        }

    def test_password_is_hashed_not_stored_raw(self):
        self.client.post(self.url, self.valid)

        user = User.objects.get(mobile="09121234567")
        self.assertNotIn("HseTech!2026", user.password)
        self.assertTrue(user.check_password("HseTech!2026"))

    def test_mismatched_passwords_rejected(self):
        self.client.post(self.url, {**self.valid, "password2": "Different!2026"})
        self.assertFalse(User.objects.filter(mobile="09121234567").exists())

    def test_terms_must_be_accepted(self):
        data = {k: v for k, v in self.valid.items() if k != "accept_terms"}
        self.client.post(self.url, data)
        self.assertFalse(User.objects.filter(mobile="09121234567").exists())


class PersianDigitFlowTests(OtpTestMixin, TestCase):
    def test_registration_works_with_persian_digits_end_to_end(self):
        """کاربری که با کیبورد فارسی تایپ می‌کند باید بدون مشکل ثبت‌نام کند."""
        self.client.post(reverse("accounts:register"), {"mobile": "۰۹۱۲۱۲۳۴۵۶۷"})

        # کد را هم با ارقام فارسی وارد می‌کنیم
        persian_code = self.last_code.translate(
            str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")
        )
        self.client.post(reverse("accounts:register_verify"), {"code": persian_code})

        self.client.post(
            reverse("accounts:register_complete"),
            {
                "first_name": "نگین",
                "last_name": "هوشنگی",
                "password1": "HseTech!2026",
                "password2": "HseTech!2026",
                "accept_terms": "on",
            },
        )

        self.assertTrue(User.objects.filter(mobile="09121234567").exists())
