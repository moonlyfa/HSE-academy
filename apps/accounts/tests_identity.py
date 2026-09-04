"""تست‌های استعلام تطبیق شماره موبایل و کد ملی."""

from unittest.mock import patch

import requests
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import IdentityStatus, IdentityVerification, OtpPurpose
from apps.accounts.services.identity import IdentityResult, verify_identity
from apps.accounts.tests_otp import OtpTestMixin

User = get_user_model()

# کد ملی معتبر (رقم کنترلی درست) برای استفاده در تست‌ها
VALID_NATIONAL_CODE = "0499370899"


class IdentityServiceTests(TestCase):
    """رفتار سرویس در سه حالت ممکن."""

    @override_settings(MOCK_IDENTITY_RESULT="matched")
    def test_matched_result(self):
        result = verify_identity("09121234567", VALID_NATIONAL_CODE)

        self.assertTrue(result.success)
        self.assertTrue(result.matched)
        self.assertEqual(
            IdentityVerification.objects.get().status, IdentityStatus.MATCHED
        )

    @override_settings(MOCK_IDENTITY_RESULT="not_matched")
    def test_not_matched_result(self):
        result = verify_identity("09121234567", VALID_NATIONAL_CODE)

        self.assertTrue(result.success)   # با سرویس حرف زدیم
        self.assertFalse(result.matched)  # ولی تطبیق نداشت
        self.assertEqual(
            IdentityVerification.objects.get().status, IdentityStatus.NOT_MATCHED
        )

    @override_settings(MOCK_IDENTITY_RESULT="failed")
    def test_service_failure_is_distinct_from_mismatch(self):
        """
        مهم‌ترین تمایز این فاز: «سرویس قطع است» با «هویت تطبیق ندارد»
        یکی نیست. اگر قاطی شوند، هنگام قطعی سرویس کاربران بی‌گناه رد
        می‌شوند.
        """
        result = verify_identity("09121234567", VALID_NATIONAL_CODE)

        self.assertFalse(result.success)
        self.assertFalse(result.matched)
        self.assertEqual(
            IdentityVerification.objects.get().status, IdentityStatus.FAILED
        )

    def test_every_attempt_is_recorded(self):
        """هر استعلام هزینه دارد؛ همه باید ثبت شوند."""
        for _ in range(3):
            verify_identity("09121234567", VALID_NATIONAL_CODE)

        self.assertEqual(IdentityVerification.objects.count(), 3)

    def test_national_code_is_masked_for_display(self):
        verify_identity("09121234567", VALID_NATIONAL_CODE)
        record = IdentityVerification.objects.get()

        self.assertEqual(record.masked_national_code, "049***0899")
        self.assertEqual(record.masked_mobile, "0912***4567")

    def test_full_national_code_not_written_to_log(self):
        with self.assertLogs("hse.identity", level="INFO") as captured:
            verify_identity("09121234567", VALID_NATIONAL_CODE)

        joined = "\n".join(captured.output)
        self.assertNotIn(VALID_NATIONAL_CODE, joined)
        self.assertNotIn("09121234567", joined)


class IdentityProviderSelectionTests(TestCase):
    @override_settings(USE_MOCK_IDENTITY=True, IDENTITY_PROVIDER="shahkar")
    def test_mock_wins_in_development(self):
        """هر استعلام واقعی هزینه دارد و نباید هنگام تست خرج شود."""
        from apps.accounts.services.identity import (
            MockIdentityProvider,
            get_identity_service,
        )

        self.assertIsInstance(get_identity_service(), MockIdentityProvider)

    @override_settings(USE_MOCK_IDENTITY=False, IDENTITY_PROVIDER="unknown-service")
    def test_unknown_provider_falls_back_to_mock(self):
        from apps.accounts.services.identity import (
            MockIdentityProvider,
            get_identity_service,
        )

        self.assertIsInstance(get_identity_service(), MockIdentityProvider)

    @override_settings(
        USE_MOCK_IDENTITY=False,
        IDENTITY_PROVIDER="shahkar",
        IDENTITY_API_BASE_URL="",
        IDENTITY_API_KEY="",
    )
    def test_real_provider_refuses_to_start_without_credentials(self):
        from apps.accounts.services.identity import get_identity_service

        with self.assertRaises(ValueError):
            get_identity_service()


@override_settings(
    USE_MOCK_IDENTITY=False,
    IDENTITY_PROVIDER="shahkar",
    IDENTITY_API_BASE_URL="https://api.example.test",
    IDENTITY_API_KEY="test-key",
)
class RealProviderErrorHandlingTests(TestCase):
    """
    هیچ خطای شبکه‌ای نباید به شکل خام به کاربر برسد.

    این تست‌ها بدون تماس واقعی با اینترنت اجرا می‌شوند: کتابخانه شبکه
    را جایگزین می‌کنیم و خطاهای مختلف را شبیه‌سازی می‌کنیم.
    """

    def _verify_with(self, side_effect) -> IdentityResult:
        with patch("apps.accounts.services.identity.requests.post", side_effect=side_effect):
            return verify_identity("09121234567", VALID_NATIONAL_CODE)

    def test_timeout_gives_persian_message(self):
        result = self._verify_with(requests.Timeout())

        self.assertFalse(result.success)
        self.assertIn("چند دقیقه دیگر", result.message)

    def test_connection_error_gives_persian_message(self):
        result = self._verify_with(requests.ConnectionError())

        self.assertFalse(result.success)
        self.assertIn("ارتباط", result.message)

    def test_invalid_json_is_handled(self):
        class BadResponse:
            status_code = 200

            def raise_for_status(self):
                return None

            def json(self):
                raise ValueError("not json")

        with patch(
            "apps.accounts.services.identity.requests.post", return_value=BadResponse()
        ):
            result = verify_identity("09121234567", VALID_NATIONAL_CODE)

        self.assertFalse(result.success)
        self.assertIn("نامعتبر", result.message)

    def test_failures_are_still_recorded(self):
        self._verify_with(requests.Timeout())

        self.assertEqual(
            IdentityVerification.objects.get().status, IdentityStatus.FAILED
        )


class RegistrationIdentityStepTests(OtpTestMixin, TestCase):
    """گام سوم ثبت‌نام: استعلام هویت."""

    def _reach_identity_step(self, mobile="09121234567"):
        self.client.post(reverse("accounts:register"), {"mobile": mobile})
        self.client.post(reverse("accounts:register_verify"), {"code": self.last_code})

    def _complete_registration(self):
        return self.client.post(
            reverse("accounts:register_complete"),
            {
                "first_name": "نگین",
                "last_name": "هوشنگی",
                "password1": "HseTech!2026",
                "password2": "HseTech!2026",
                "accept_terms": "on",
            },
        )

    @override_settings(MOCK_IDENTITY_RESULT="matched")
    def test_successful_identity_allows_completing_registration(self):
        self._reach_identity_step()
        self.client.post(
            reverse("accounts:register_identity"),
            {"national_code": VALID_NATIONAL_CODE},
        )
        self._complete_registration()

        user = User.objects.get(mobile="09121234567")
        self.assertTrue(user.is_identity_verified)
        self.assertEqual(user.national_code, VALID_NATIONAL_CODE)

    @override_settings(MOCK_IDENTITY_RESULT="not_matched")
    def test_mismatch_blocks_registration(self):
        """طبق خواسته کارفرما: بدون تطبیق هویت، حساب ساخته نمی‌شود."""
        self._reach_identity_step()

        response = self.client.post(
            reverse("accounts:register_identity"),
            {"national_code": VALID_NATIONAL_CODE},
        )
        self.assertContains(response, "مطابقت ندارد")

        self._complete_registration()
        self.assertFalse(User.objects.filter(mobile="09121234567").exists())

    @override_settings(MOCK_IDENTITY_RESULT="failed")
    def test_service_outage_does_not_create_account_but_allows_retry(self):
        self._reach_identity_step()

        response = self.client.post(
            reverse("accounts:register_identity"),
            {"national_code": VALID_NATIONAL_CODE},
            follow=True,
        )
        # کاربر پیام فارسی می‌بیند، نه خطای فنی
        self.assertContains(response, "احراز هویت")
        self.assertFalse(User.objects.filter(mobile="09121234567").exists())

    def test_cannot_skip_identity_step(self):
        """رفتن مستقیم به گام آخر نباید حساب بسازد."""
        self._reach_identity_step()

        response = self.client.get(reverse("accounts:register_complete"))
        self.assertRedirects(response, reverse("accounts:register_identity"))

        self._complete_registration()
        self.assertFalse(User.objects.filter(mobile="09121234567").exists())

    def test_identity_step_requires_verified_mobile(self):
        response = self.client.get(reverse("accounts:register_identity"))
        self.assertRedirects(response, reverse("accounts:register"))

    def test_invalid_national_code_never_reaches_the_paid_service(self):
        """
        اعتبارسنجی رقم کنترلی پیش از تماس با سرویس انجام می‌شود، تا برای
        کد ملی آشکارا اشتباه، هزینه استعلام پرداخت نشود.
        """
        self._reach_identity_step()

        self.client.post(
            reverse("accounts:register_identity"), {"national_code": "1234567890"}
        )
        self.assertEqual(IdentityVerification.objects.count(), 0)

    @override_settings(
        MOCK_IDENTITY_RESULT="matched", IDENTITY_REQUIRED_FOR_REGISTRATION=False
    )
    def test_optional_mode_allows_registration_without_identity(self):
        """
        اگر کارفرما تصمیم بگیرد احراز هویت اجباری نباشد، ثبت‌نام کامل
        می‌شود اما حساب به‌عنوان تأییدنشده باقی می‌ماند.
        """
        self._reach_identity_step()
        self._complete_registration()

        user = User.objects.get(mobile="09121234567")
        self.assertFalse(user.is_identity_verified)


class StandaloneIdentityVerificationTests(TestCase):
    """احراز هویت برای کاربری که قبلاً ثبت‌نام کرده است."""

    def setUp(self):
        self.user = User.objects.create_user(
            mobile="09121234567", password="HseTech!2026"
        )
        self.client.force_login(self.user)
        self.url = reverse("accounts:verify_identity")

    @override_settings(MOCK_IDENTITY_RESULT="matched")
    def test_user_can_verify_identity(self):
        self.client.post(self.url, {"national_code": VALID_NATIONAL_CODE})

        self.user.refresh_from_db()
        self.assertTrue(self.user.is_identity_verified)
        self.assertEqual(self.user.national_code, VALID_NATIONAL_CODE)

    @override_settings(MOCK_IDENTITY_RESULT="not_matched")
    def test_mismatch_leaves_user_unverified(self):
        self.client.post(self.url, {"national_code": VALID_NATIONAL_CODE})

        self.user.refresh_from_db()
        self.assertFalse(self.user.is_identity_verified)
        self.assertIsNone(self.user.national_code)

    @override_settings(MOCK_IDENTITY_RESULT="matched")
    def test_attempt_is_linked_to_the_user(self):
        self.client.post(self.url, {"national_code": VALID_NATIONAL_CODE})

        self.assertEqual(IdentityVerification.objects.get().user, self.user)

    def test_already_verified_user_is_redirected(self):
        self.user.is_identity_verified = True
        self.user.save()

        response = self.client.get(self.url)
        self.assertRedirects(response, reverse("accounts:dashboard"))

    def test_anonymous_visitor_cannot_access(self):
        self.client.logout()
        self.assertEqual(self.client.get(self.url).status_code, 302)
