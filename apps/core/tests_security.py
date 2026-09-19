"""
تست‌های فاز ۲۱ — امنیت و محدودسازی نرخ درخواست.

این تست‌ها چیزهایی را نگه می‌دارند که خرابی‌شان سروصدا نمی‌کند: یک هدر
جاافتاده، یک سقف برداشته‌شده، یا اعتماد به هدری که هر کسی می‌تواند
بفرستد. هیچ‌کدام باعث نمی‌شوند صفحه‌ای خطا بدهد — فقط سایت را باز
می‌گذارند.
"""

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse

from apps.core.throttling import RateLimit, get_client_ip

User = get_user_model()


class SecurityHeaderTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_csp_is_sent_and_blocks_foreign_scripts(self):
        response = self.client.get(reverse("core:home"))
        policy = response["Content-Security-Policy"]

        self.assertIn("default-src 'self'", policy)
        self.assertIn("script-src 'self'", policy)
        self.assertIn("frame-ancestors 'none'", policy)

    def test_script_src_never_allows_inline_code(self):
        """«unsafe-inline» روی اسکریپت یعنی CSP عملاً بی‌اثر است."""
        policy = self.client.get(reverse("core:home"))["Content-Security-Policy"]

        script_directive = next(
            part for part in policy.split(";") if part.strip().startswith("script-src")
        )
        self.assertNotIn("unsafe-inline", script_directive)

    def test_structured_data_carries_the_request_nonce(self):
        response = self.client.get(reverse("core:home"))
        html = response.content.decode()
        policy = response["Content-Security-Policy"]

        nonce = policy.split("'nonce-")[1].split("'")[0]
        self.assertIn(f'nonce="{nonce}"', html)

    def test_each_response_gets_a_fresh_nonce(self):
        first = self.client.get(reverse("core:home"))["Content-Security-Policy"]
        second = self.client.get(reverse("core:home"))["Content-Security-Policy"]

        self.assertNotEqual(first, second)

    @override_settings(CSP_REPORT_ONLY=True)
    def test_report_only_mode_does_not_enforce(self):
        response = self.client.get(reverse("core:home"))

        self.assertIn("Content-Security-Policy-Report-Only", response)
        self.assertNotIn("Content-Security-Policy", response.headers)

    @override_settings(CSP_ENABLED=False)
    def test_policy_can_be_switched_off(self):
        response = self.client.get(reverse("core:home"))
        self.assertNotIn("Content-Security-Policy", response.headers)

    def test_permissions_policy_closes_device_access(self):
        policy = self.client.get(reverse("core:home"))["Permissions-Policy"]

        self.assertIn("camera=()", policy)
        self.assertIn("microphone=()", policy)
        self.assertIn("geolocation=()", policy)

    def test_clickjacking_protection_is_on(self):
        response = self.client.get(reverse("core:home"))
        self.assertEqual(response["X-Frame-Options"], "DENY")


class ClientIpTests(TestCase):
    """
    اعتماد به X-Forwarded-For فقط پشت Proxy خودمان.

    اگر همیشه باور شود، دور زدن هر سقفی به اندازه فرستادن یک هدر ساختگی
    آسان است: هر درخواست، یک IP تازه.
    """

    def setUp(self):
        self.factory = RequestFactory()

    def request_with_header(self):
        return self.factory.get(
            "/", REMOTE_ADDR="10.0.0.1", HTTP_X_FORWARDED_FOR="1.2.3.4"
        )

    @override_settings(TRUST_X_FORWARDED_FOR=False)
    def test_header_is_ignored_when_there_is_no_trusted_proxy(self):
        self.assertEqual(get_client_ip(self.request_with_header()), "10.0.0.1")

    @override_settings(TRUST_X_FORWARDED_FOR=True)
    def test_header_is_used_behind_a_trusted_proxy(self):
        self.assertEqual(get_client_ip(self.request_with_header()), "1.2.3.4")

    def test_unknown_when_there_is_no_address(self):
        request = self.factory.get("/")
        request.META.pop("REMOTE_ADDR", None)
        self.assertEqual(get_client_ip(request), "unknown")


@override_settings(TEST_LIMIT_PER_HOUR=3)
class RateLimitTests(TestCase):
    def setUp(self):
        cache.clear()
        self.limit = RateLimit("test", "TEST_LIMIT_PER_HOUR")
        self.request = RequestFactory().get("/", REMOTE_ADDR="10.0.0.1")

    def test_counts_up_to_the_limit(self):
        for _ in range(3):
            self.assertFalse(self.limit.is_exceeded(self.request))
            self.limit.record(self.request)

        self.assertTrue(self.limit.is_exceeded(self.request))

    def test_separate_ips_have_separate_counters(self):
        other = RequestFactory().get("/", REMOTE_ADDR="10.0.0.2")
        for _ in range(3):
            self.limit.record(self.request)

        self.assertTrue(self.limit.is_exceeded(self.request))
        self.assertFalse(self.limit.is_exceeded(other))

    @override_settings(TEST_LIMIT_PER_HOUR=0)
    def test_zero_means_no_limit(self):
        for _ in range(50):
            self.limit.record(self.request)

        self.assertFalse(self.limit.is_exceeded(self.request))


class PublicFormThrottleTests(TestCase):
    """فرم‌های عمومی سایت باید سقف داشته باشند."""

    def setUp(self):
        cache.clear()

    @override_settings(CONTACT_MAX_PER_HOUR=2)
    def test_contact_form_is_throttled(self):
        from apps.core.models import ContactMessage

        payload = {
            "full_name": "سارا محمدی",
            "mobile": "09121234567",
            "subject": "سؤال",
            "message": "متن پیام آزمایشی برای تست محدودیت.",
        }

        for _ in range(2):
            self.client.post(reverse("core:contact"), payload)

        response = self.client.post(reverse("core:contact"), payload, follow=True)

        self.assertContains(response, "تعداد پیام‌های ارسالی شما زیاد بوده است")
        self.assertEqual(ContactMessage.objects.count(), 2)

    @override_settings(REGISTRATION_MAX_PER_HOUR=2)
    def test_registration_is_throttled_per_ip(self):
        """سقف پیامک روی هر شماره است؛ این سقف جلوی کار با هزار شماره را می‌گیرد."""
        for index in range(2):
            self.client.post(
                reverse("accounts:register"), {"mobile": f"0912000000{index}"}
            )

        response = self.client.post(
            reverse("accounts:register"), {"mobile": "09129999999"}
        )

        self.assertContains(response, "تعداد تلاش‌های ثبت‌نام از این دستگاه زیاد بوده")

    @override_settings(PASSWORD_RESET_MAX_PER_HOUR=2)
    def test_password_reset_is_throttled_per_ip(self):
        for index in range(2):
            self.client.post(
                reverse("accounts:password_reset"), {"mobile": f"0912000000{index}"}
            )

        response = self.client.post(
            reverse("accounts:password_reset"), {"mobile": "09129999999"}
        )

        self.assertContains(response, "تعداد درخواست‌های بازیابی از این دستگاه زیاد بوده")


class AdminLoginThrottleTests(TestCase):
    """پنل مدیریت، ارزشمندترین هدف سایت است."""

    def setUp(self):
        cache.clear()
        self.url = "/admin/login/"

    @override_settings(ADMIN_LOGIN_MAX_PER_HOUR=3)
    def test_repeated_password_guesses_are_blocked(self):
        for _ in range(3):
            self.client.post(self.url, {"username": "09120000000", "password": "x"})

        response = self.client.post(
            self.url, {"username": "09120000000", "password": "x"}
        )

        self.assertEqual(response.status_code, 429)

    @override_settings(ADMIN_LOGIN_MAX_PER_HOUR=3)
    def test_opening_the_login_page_is_not_limited(self):
        for _ in range(10):
            self.assertEqual(self.client.get(self.url).status_code, 200)


class ProtectedMediaTests(TestCase):
    """فایل‌های محافظت‌شده دوره‌ها."""

    def setUp(self):
        cache.clear()
        self.staff = User.objects.create_user(mobile="09120000000", is_staff=True)

    def test_anonymous_visitor_is_sent_to_login(self):
        response = self.client.get("/protected-media/lesson.mp4")

        self.assertEqual(response.status_code, 302)
        self.assertIn("login", response["Location"])

    def test_path_traversal_is_refused(self):
        """آدرس نباید بتواند از پوشه محافظت‌شده بیرون برود."""
        self.client.force_login(self.staff)

        response = self.client.get("/protected-media/subdir/../../../etc/hosts")

        self.assertEqual(response.status_code, 400)


class SensitiveDataTests(TestCase):
    """آنچه نباید بیرون برود."""

    def setUp(self):
        cache.clear()

    def test_password_reset_does_not_reveal_whether_a_mobile_exists(self):
        User.objects.create_user(mobile="09121234567", password="HseTech!2026")

        known = self.client.post(
            reverse("accounts:password_reset"), {"mobile": "09121234567"}, follow=True
        )
        unknown = self.client.post(
            reverse("accounts:password_reset"), {"mobile": "09127654321"}, follow=True
        )

        self.assertContains(known, "اگر این شماره در سایت ثبت شده باشد")
        self.assertContains(unknown, "اگر این شماره در سایت ثبت شده باشد")

    def test_login_error_does_not_say_which_field_was_wrong(self):
        User.objects.create_user(mobile="09121234567", password="HseTech!2026")

        response = self.client.post(
            reverse("accounts:login"),
            {"mobile": "09121234567", "password": "wrong-password"},
        )

        self.assertContains(response, "شماره موبایل یا رمز عبور اشتباه است")
