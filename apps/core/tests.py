"""
تست‌های اپلیکیشن core.

این تست‌ها محافظ ما هستند: اگر در فازهای بعدی چیزی را خراب کنیم،
اینجا سریع خبردار می‌شویم.
"""

from django.test import TestCase
from django.utils import timezone

from apps.core.models import FAQ, Banner, Feature, Partner, SiteSetting, Testimonial


class HealthAndHomeTests(TestCase):
    def test_health_returns_ok(self):
        response = self.client.get("/health/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")

    def test_home_page_loads(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "core/home.html")

    def test_home_page_is_rtl_and_persian(self):
        response = self.client.get("/")
        self.assertContains(response, 'lang="fa"')
        self.assertContains(response, 'dir="rtl"')

    def test_home_page_works_on_empty_database(self):
        """سایت باید روی دیتابیس خالی هم بدون خطا بالا بیاید."""
        SiteSetting.objects.all().delete()
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)

    def test_404_page_uses_custom_template(self):
        response = self.client.get("/this-page-does-not-exist/")
        self.assertEqual(response.status_code, 404)


class SiteSettingTests(TestCase):
    def test_load_creates_row_when_missing(self):
        SiteSetting.objects.all().delete()
        self.assertEqual(SiteSetting.objects.count(), 0)

        setting = SiteSetting.load()
        self.assertEqual(SiteSetting.objects.count(), 1)
        self.assertEqual(setting.pk, 1)

    def test_load_is_idempotent(self):
        first = SiteSetting.load()
        second = SiteSetting.load()
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(SiteSetting.objects.count(), 1)

    def test_site_context_is_available_in_templates(self):
        setting = SiteSetting.load()
        setting.site_name = "آکادمی تست"
        setting.save()

        response = self.client.get("/")
        self.assertContains(response, "آکادمی تست")


class SectionToggleTests(TestCase):
    """ادمین باید بتواند هر بخش صفحه اصلی را بدون تغییر کد خاموش کند."""

    def setUp(self):
        self.setting = SiteSetting.load()
        Feature.objects.create(title="مزیت-یکتای-تستی", icon="certificate", description="توضیح")

    def test_features_section_visible_when_enabled(self):
        response = self.client.get("/")
        self.assertContains(response, "مزیت-یکتای-تستی")

    def test_features_section_hidden_when_disabled(self):
        self.setting.show_features_section = False
        self.setting.save()

        response = self.client.get("/")
        self.assertNotContains(response, "مزیت-یکتای-تستی")

    def test_inactive_feature_is_not_shown(self):
        Feature.objects.update(is_active=False)
        response = self.client.get("/")
        self.assertNotContains(response, "مزیت-یکتای-تستی")


class BannerVisibilityTests(TestCase):
    """بنر فقط باید در بازه تاریخی تعیین‌شده نمایش داده شود."""

    def setUp(self):
        self.now = timezone.now()

    def _make_banner(self, **kwargs):
        return Banner.objects.create(title="بنر آزمایشی", **kwargs)

    def test_banner_without_dates_is_visible(self):
        banner = self._make_banner()
        self.assertTrue(banner.is_visible_now)

    def test_banner_inside_date_range_is_visible(self):
        banner = self._make_banner(
            starts_at=self.now - timezone.timedelta(days=1),
            ends_at=self.now + timezone.timedelta(days=1),
        )
        self.assertTrue(banner.is_visible_now)

    def test_future_banner_is_not_visible(self):
        banner = self._make_banner(starts_at=self.now + timezone.timedelta(days=3))
        self.assertFalse(banner.is_visible_now)

    def test_expired_banner_is_not_visible(self):
        banner = self._make_banner(ends_at=self.now - timezone.timedelta(days=1))
        self.assertFalse(banner.is_visible_now)

    def test_inactive_banner_is_not_visible(self):
        banner = self._make_banner(is_active=False)
        self.assertFalse(banner.is_visible_now)

    def test_expired_banner_is_not_rendered_on_homepage(self):
        self._make_banner(ends_at=self.now - timezone.timedelta(days=1))
        response = self.client.get("/")
        self.assertNotContains(response, "بنر آزمایشی")


class OrderingTests(TestCase):
    """موارد با ترتیب کوچک‌تر باید بالاتر نمایش داده شوند."""

    def test_features_are_ordered_by_order_field(self):
        Feature.objects.create(title="دوم", order=2)
        Feature.objects.create(title="اول", order=1)

        titles = list(Feature.objects.active().values_list("title", flat=True))
        self.assertEqual(titles, ["اول", "دوم"])

    def test_active_manager_filters_inactive_items(self):
        Partner.objects.create(name="فعال", is_active=True)
        Partner.objects.create(name="غیرفعال", is_active=False)

        names = list(Partner.objects.active().values_list("name", flat=True))
        self.assertEqual(names, ["فعال"])


class FAQTests(TestCase):
    def test_only_homepage_faqs_are_shown_on_home(self):
        FAQ.objects.create(question="سؤال صفحه اصلی", answer="پاسخ", show_on_homepage=True)
        FAQ.objects.create(question="سؤال داخلی", answer="پاسخ", show_on_homepage=False)

        response = self.client.get("/")
        self.assertContains(response, "سؤال صفحه اصلی")
        self.assertNotContains(response, "سؤال داخلی")


class IconTagTests(TestCase):
    def test_known_icon_renders_svg(self):
        from apps.core.templatetags.core_extras import icon

        output = icon("shield")
        self.assertIn("<svg", output)
        self.assertIn('stroke="currentColor"', output)

    def test_unknown_icon_renders_nothing(self):
        from apps.core.templatetags.core_extras import icon

        self.assertEqual(icon("this-icon-does-not-exist"), "")


class TemplateRenderingTests(TestCase):
    """قالب نباید کامنت‌های داخلی را به کاربر نشان بدهد."""

    def test_template_comments_are_not_rendered(self):
        Testimonial.objects.create(full_name="تست", quote="متن")
        response = self.client.get("/")
        content = response.content.decode()

        self.assertNotIn("{#", content)
        self.assertNotIn("#}", content)
        # خط‌های تزئینی کامنت نباید در خروجی باشند
        self.assertNotIn("==================", content)
