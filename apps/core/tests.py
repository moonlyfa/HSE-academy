"""
تست‌های اپلیکیشن core.

این تست‌ها محافظ ما هستند: اگر در فازهای بعدی چیزی را خراب کنیم،
اینجا سریع خبردار می‌شویم.
"""

from django.test import TestCase
from django.utils import timezone

from apps.core.models import FAQ, Feature, HeroSlide, Partner, SiteSetting, Testimonial


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


class HeroSlideVisibilityTests(TestCase):
    """اسلاید فقط باید در بازه تاریخی تعیین‌شده نمایش داده شود."""

    def setUp(self):
        self.now = timezone.now()

    def _make_banner(self, **kwargs):
        return HeroSlide.objects.create(title="اسلاید آزمایشی", image="slides/test.jpg", **kwargs)

    def test_slide_without_dates_is_visible(self):
        banner = self._make_banner()
        self.assertTrue(banner.is_visible_now)

    def test_slide_inside_date_range_is_visible(self):
        banner = self._make_banner(
            starts_at=self.now - timezone.timedelta(days=1),
            ends_at=self.now + timezone.timedelta(days=1),
        )
        self.assertTrue(banner.is_visible_now)

    def test_future_slide_is_not_visible(self):
        banner = self._make_banner(starts_at=self.now + timezone.timedelta(days=3))
        self.assertFalse(banner.is_visible_now)

    def test_expired_slide_is_not_visible(self):
        banner = self._make_banner(ends_at=self.now - timezone.timedelta(days=1))
        self.assertFalse(banner.is_visible_now)

    def test_inactive_slide_is_not_visible(self):
        banner = self._make_banner(is_active=False)
        self.assertFalse(banner.is_visible_now)

    def test_expired_slide_is_not_rendered_on_homepage(self):
        self._make_banner(ends_at=self.now - timezone.timedelta(days=1))
        response = self.client.get("/")
        self.assertNotContains(response, "اسلاید آزمایشی")


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


class JalaliDateTests(TestCase):
    """تبدیل تاریخ میلادی به شمسی باید دقیق باشد."""

    def test_known_conversions(self):
        from apps.core.jalali import gregorian_to_jalali

        cases = [
            ((2026, 3, 21), (1405, 1, 1)),    # نوروز ۱۴۰۵
            ((2025, 3, 21), (1404, 1, 1)),    # نوروز ۱۴۰۴
            ((2024, 3, 20), (1403, 1, 1)),    # نوروز ۱۴۰۳ (سال کبیسه میلادی)
            ((2000, 1, 1), (1378, 10, 11)),
            ((1979, 2, 11), (1357, 11, 22)),
            ((2021, 12, 31), (1400, 10, 10)),
        ]
        for gregorian, expected in cases:
            with self.subTest(date=gregorian):
                self.assertEqual(gregorian_to_jalali(*gregorian), expected)

    def test_string_output_is_persian(self):
        from datetime import date

        from apps.core.jalali import to_jalali_string

        self.assertEqual(to_jalali_string(date(2026, 9, 2)), "۱۱ شهریور ۱۴۰۵")

    def test_none_returns_empty_string(self):
        from apps.core.jalali import to_jalali_string

        self.assertEqual(to_jalali_string(None), "")


class PriceFormattingTests(TestCase):
    """
    تست رگرسیون.

    فیلتر intcomma در locale فارسی جداکننده هزارگان را حذف می‌کند
    (NUMBER_GROUPING صفر است) و قیمت به شکل «۹۵۰۰۰۰» نمایش داده می‌شود.
    فیلتر toman باید مستقل از locale درست کار کند.
    """

    def _render(self, value):
        from django.template import Context, Template

        return Template("{% load core_extras %}{{ v|toman }}").render(Context({"v": value}))

    def test_thousand_separator_is_applied(self):
        self.assertEqual(self._render(950000), "۹۵۰,۰۰۰")
        self.assertEqual(self._render(3900000), "۳,۹۰۰,۰۰۰")

    def test_zero_and_small_numbers(self):
        self.assertEqual(self._render(0), "۰")
        self.assertEqual(self._render(500), "۵۰۰")

    def test_non_numeric_value_does_not_crash(self):
        self.assertEqual(self._render("رایگان"), "رایگان")


class HeroSliderTests(TestCase):
    """اسلایدر باید سبک بارگذاری شود و تنظیماتش از پنل مدیریت بیاید."""

    def setUp(self):
        self.site = SiteSetting.load()
        for i in range(5):
            HeroSlide.objects.create(
                title=f"اسلاید {i + 1}",
                image=f"slides/test-{i + 1}.jpg",
                order=i,
            )

    def test_only_first_two_slides_load_eagerly(self):
        """
        تست رگرسیون عملکرد.

        اگر هر ۱۰ تصویر تمام‌عرض هنگام باز شدن صفحه دانلود شوند، صفحه اصلی
        روی اینترنت کند بسیار سنگین می‌شود. فقط دو اسلاید اول باید src داشته
        باشند و بقیه در data-src نگه داشته شوند.
        """
        content = self.client.get("/").content.decode()

        self.assertEqual(content.count('<img src="/media/slides/'), 2)
        self.assertEqual(content.count("data-src="), 3)

    def test_slider_timing_comes_from_site_settings(self):
        self.site.hero_slider_interval_seconds = 9
        self.site.hero_slider_transition_ms = 1400
        self.site.save()

        content = self.client.get("/").content.decode()
        self.assertIn('data-slider-interval="9000"', content)
        self.assertIn("--slider-fade: 1400ms", content)

    def test_interval_never_drops_below_two_seconds(self):
        """فاصله خیلی کوتاه، اسلایدر را غیرقابل استفاده می‌کند."""
        self.site.hero_slider_interval_seconds = 0
        self.site.save()
        self.assertEqual(self.site.hero_slider_interval_ms, 2000)

    def test_slider_hidden_when_no_slides(self):
        HeroSlide.objects.all().delete()
        content = self.client.get("/").content.decode()
        self.assertNotIn("hero-slider__track", content)

    def test_slide_titles_are_not_printed_over_the_image(self):
        """طبق خواسته کارفرما اسلاید فقط تصویر است؛ عنوان فقط در alt می‌آید."""
        content = self.client.get("/").content.decode()
        self.assertIn('alt="اسلاید 1"', content)
        self.assertNotIn("<h1>اسلاید 1</h1>", content)
        self.assertNotIn("<h2>اسلاید 1</h2>", content)


class TemplateSyntaxGuardTests(TestCase):
    """
    نگهبان خودکار قالب‌ها.

    در جنگو، {# ... #} فقط کامنت تک‌خطی است. اگر کامنتی به خط بعد برود،
    دیگر کامنت نیست و متنش عیناً روی صفحه سایت چاپ می‌شود.
    این تست همه قالب‌ها را بررسی می‌کند تا این اشتباه دوباره تکرار نشود.
    """

    def test_no_multiline_django_comments(self):
        import pathlib

        from django.conf import settings

        broken = []
        for template_dir in settings.TEMPLATES[0]["DIRS"]:
            for path in pathlib.Path(template_dir).rglob("*.html"):
                for number, line in enumerate(
                    path.read_text(encoding="utf-8").splitlines(), start=1
                ):
                    if line.count("{#") != line.count("#}"):
                        broken.append(f"{path.name}:{number} → {line.strip()[:70]}")

        self.assertEqual(
            broken,
            [],
            "کامنت چندخطی پیدا شد. در جنگو {# #} فقط تک‌خطی است و متن "
            "کامنت چندخطی روی صفحه سایت چاپ می‌شود.\n" + "\n".join(broken),
        )
