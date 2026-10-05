"""
تست‌های برند «سپر آکادمی»: نام، لوگو، رنگ‌ها و تصویرهای نمونه.
"""

import importlib
import shutil
import tempfile
from io import StringIO
from pathlib import Path

from django.apps import apps as django_apps
from django.contrib.staticfiles import finders
from django.core.files.base import ContentFile
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.core.models import HeroSlide, SiteSetting
from apps.courses.models import Course, CourseCategory

BRAND_RED = "#88261B"
BRAND_INK = "#231F20"

TEMP_MEDIA = Path(tempfile.mkdtemp(prefix="hse-brand-media-"))


@override_settings(MEDIA_ROOT=TEMP_MEDIA)
class BrandIdentityTests(TestCase):
    def test_default_site_name_is_separ_academy(self):
        self.assertEqual(SiteSetting.load().site_name, "سپر آکادمی")

    def test_header_and_footer_show_the_brand_logo(self):
        response = self.client.get(reverse("core:home"))

        self.assertContains(response, "img/brand/separ-logo.svg")
        self.assertContains(response, "img/brand/separ-logo-light.svg")
        self.assertNotContains(response, "HSE Tech")

    def test_an_uploaded_logo_still_wins(self):
        site = SiteSetting.load()
        site.logo.save("custom.png", ContentFile(b"\x89PNG"), save=True)
        self.addCleanup(site.logo.delete, save=False)

        response = self.client.get(reverse("core:home"))

        self.assertContains(response, site.logo.url)
        self.assertNotContains(response, "img/brand/separ-logo.svg")

    def test_head_has_brand_icons_and_share_image(self):
        response = self.client.get(reverse("core:home"))

        self.assertContains(response, "img/brand/separ-mark.svg")
        self.assertContains(response, "img/apple-touch-icon.png")
        self.assertContains(response, "img/brand/separ-og.png")
        self.assertContains(response, f'<meta name="theme-color" content="{BRAND_RED}">')

    def test_brand_files_exist(self):
        for name in (
            "img/brand/separ-logo.svg",
            "img/brand/separ-logo-light.svg",
            "img/brand/separ-mark.svg",
            "img/brand/separ-og.png",
            "img/favicon.png",
            "img/apple-touch-icon.png",
            "css/admin-brand.css",
        ):
            self.assertIsNotNone(finders.find(name), name)

    def test_logo_uses_the_brandbook_colors(self):
        logo = Path(finders.find("img/brand/separ-logo.svg")).read_text()
        self.assertIn(BRAND_RED, logo)
        self.assertIn(BRAND_INK, logo)

    def test_stylesheet_uses_the_brandbook_colors(self):
        css = Path(finders.find("css/main.css")).read_text()
        self.assertIn(f"--color-primary: {BRAND_RED};", css)
        self.assertIn(f"--color-secondary: {BRAND_INK};", css)

    def test_admin_uses_brand_header(self):
        from django.contrib import admin

        self.assertEqual(admin.site.site_header, "پنل مدیریت سپر آکادمی")
        response = self.client.get(reverse("admin:login"))
        self.assertContains(response, "css/admin-brand.css")


class RenameMigrationTests(TestCase):
    """مهاجرت ۰۰۰۶ نام قدیمی را عوض می‌کند ولی نام دلخواه مدیر را نه."""

    def run_migration(self):
        module = importlib.import_module("apps.core.migrations.0006_sitesetting_separ_name")
        module.rename_site(django_apps, None)

    def test_old_name_is_replaced(self):
        SiteSetting.objects.update_or_create(pk=1, defaults={"site_name": "HSE Tech"})
        self.run_migration()
        self.assertEqual(SiteSetting.load().site_name, "سپر آکادمی")

    def test_custom_name_is_kept(self):
        SiteSetting.objects.update_or_create(pk=1, defaults={"site_name": "آکادمی من"})
        self.run_migration()
        self.assertEqual(SiteSetting.load().site_name, "آکادمی من")


@override_settings(MEDIA_ROOT=TEMP_MEDIA)
class RefreshDemoImagesTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(TEMP_MEDIA, ignore_errors=True)

    def setUp(self):
        category = CourseCategory.objects.create(name="ایمنی", slug="industrial-safety")
        self.course = Course.objects.create(
            title="دوره نمونه", slug="sample-course", category=category, price=0
        )
        self.slide = HeroSlide.objects.create(title="اسلاید", order=0)

    def refresh(self) -> str:
        out = StringIO()
        call_command("refresh_demo_images", stdout=out)
        return out.getvalue()

    def test_old_placeholders_are_repainted(self):
        self.course.thumbnail.save("demo-sample-course.jpg", ContentFile(b"old"), save=True)
        self.slide.image.save("demo-slide-1.jpg", ContentFile(b"old"), save=True)
        old_paths = [Path(self.course.thumbnail.path), Path(self.slide.image.path)]

        self.refresh()

        self.course.refresh_from_db()
        self.slide.refresh_from_db()
        self.assertTrue(Path(self.course.thumbnail.name).name.startswith("demo-separ-"))
        self.assertTrue(Path(self.slide.image.name).name.startswith("demo-separ-"))
        for path in old_paths:
            self.assertFalse(path.exists())

    def test_uploaded_images_are_never_touched(self):
        self.course.thumbnail.save("my-real-photo.jpg", ContentFile(b"real"), save=True)
        name = self.course.thumbnail.name

        self.refresh()

        self.course.refresh_from_db()
        self.assertEqual(self.course.thumbnail.name, name)

    def test_running_twice_does_nothing_the_second_time(self):
        self.course.thumbnail.save("demo-sample-course.jpg", ContentFile(b"old"), save=True)
        self.refresh()
        self.course.refresh_from_db()
        name = self.course.thumbnail.name

        output = self.refresh()

        self.course.refresh_from_db()
        self.assertEqual(self.course.thumbnail.name, name)
        self.assertIn("پیدا نشد", output)


class CertificateBrandTests(TestCase):
    def test_certificate_uses_brand_colors(self):
        from apps.certificates import pdf

        self.assertEqual(pdf.COLOR_BRAND.hexval().upper(), "0X" + BRAND_RED[1:].upper())
        self.assertEqual(pdf.COLOR_SECONDARY.hexval().upper(), "0X" + BRAND_INK[1:].upper())
