"""
تست‌های فاز ۲۲ — پنل مدیریت.

پنل مدیریت، ابزار روزمره کارفرماست و شکستنش ساده است: کافی است فیلدی از
مدل حذف شود و نامش در `list_display` یا `fieldsets` بماند. آن‌وقت همه
تست‌های دیگر سبز می‌مانند و فقط وقتی معلوم می‌شود که مدیر صفحه را باز
می‌کند و خطای ۵۰۰ می‌بیند.

این فایل دو کار می‌کند:

۱. **جاروی خودکار:** همه مدل‌های ثبت‌شده در پنل را پیدا می‌کند و صفحه
   فهرست، افزودن و ویرایش هرکدام را باز می‌کند. مدل تازه‌ای که ثبت شود،
   خودکار وارد این جارو می‌شود و لازم نیست کسی یادش بماند تستش کند.

۲. **عملیات گروهی:** دکمه‌هایی مثل «انتشار دوره‌ها» یا «ابطال گواهی» که
   داده را تغییر می‌دهند و اگر خراب باشند، خرابی‌شان ماندگار است.
"""

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.certificates.models import Certificate, CertificateStatus
from apps.courses.models import (
    Course,
    CourseCategory,
    OnlineSession,
    OnlineSessionStatus,
)

User = get_user_model()


class AdminSmokeTests(TestCase):
    """
    همه صفحه‌های پنل باید باز شوند.

    برای هر مدل یک نمونه هم ساخته نمی‌شود؛ صفحه فهرستِ خالی هم همان
    `list_display` را ارزیابی می‌کند و همان خطا را می‌دهد.
    """

    @classmethod
    def setUpTestData(cls):
        cls.superuser = User.objects.create_superuser(
            mobile="09120000000", password="HseTech!2026"
        )

    def setUp(self):
        cache.clear()
        self.client.force_login(self.superuser)

    def test_every_registered_model_has_a_working_changelist(self):
        for model, model_admin in admin.site._registry.items():
            url = reverse(
                f"admin:{model._meta.app_label}_{model._meta.model_name}_changelist"
            )
            with self.subTest(model=model._meta.label):
                self.assertEqual(self.client.get(url).status_code, 200)

    def test_every_addable_model_has_a_working_add_page(self):
        """
        مدل‌هایی که عمداً از پنل ساخته نمی‌شوند (گواهی، کارنامه آزمون)
        باید ۴۰۳ بدهند — و همین هم بخشی از انتظار ماست.
        """
        request = self.client.get(reverse("admin:index")).wsgi_request

        for model, model_admin in admin.site._registry.items():
            url = reverse(f"admin:{model._meta.app_label}_{model._meta.model_name}_add")
            expected = 200 if model_admin.has_add_permission(request) else 403

            with self.subTest(model=model._meta.label):
                self.assertEqual(self.client.get(url).status_code, expected)

    def test_admin_index_lists_the_project_apps(self):
        response = self.client.get(reverse("admin:index"))

        for label in ("دوره", "آزمون", "گواهی", "سفارش"):
            self.assertContains(response, label)


class AdminChangePageTests(TestCase):
    """صفحه ویرایش، جایی است که `fieldsets` ارزیابی می‌شود."""

    @classmethod
    def setUpTestData(cls):
        cls.superuser = User.objects.create_superuser(
            mobile="09120000000", password="HseTech!2026"
        )
        cls.category = CourseCategory.objects.create(name="ایمنی", slug="safety")
        cls.course = Course.objects.create(
            title="دوره",
            slug="course",
            category=cls.category,
            price=1_000_000,
            is_published=True,
        )
        cls.session = OnlineSession.objects.create(
            course=cls.course,
            title="کلاس",
            starts_at=timezone.now() + timezone.timedelta(days=1),
        )

    def setUp(self):
        cache.clear()
        self.client.force_login(self.superuser)

    def change_url(self, obj) -> str:
        meta = obj._meta
        return reverse(f"admin:{meta.app_label}_{meta.model_name}_change", args=[obj.pk])

    def test_course_change_page_opens(self):
        self.assertEqual(self.client.get(self.change_url(self.course)).status_code, 200)

    def test_course_form_exposes_the_access_fields(self):
        """
        این دو فیلد در فاز ۱۴ به مدل اضافه شدند اما در فرم نبودند؛
        یعنی مدیر راهی برای تنظیم «مدت دسترسی» نداشت.
        """
        response = self.client.get(self.change_url(self.course))

        self.assertContains(response, "access_duration_days")
        self.assertContains(response, "vip_access")

    def test_online_session_change_page_opens(self):
        self.assertEqual(self.client.get(self.change_url(self.session)).status_code, 200)

    def test_category_change_page_opens(self):
        self.assertEqual(
            self.client.get(self.change_url(self.category)).status_code, 200
        )


class AdminActionTests(TestCase):
    """دکمه‌های عملیات گروهی، داده را عوض می‌کنند."""

    @classmethod
    def setUpTestData(cls):
        cls.superuser = User.objects.create_superuser(
            mobile="09120000000", password="HseTech!2026"
        )
        cls.category = CourseCategory.objects.create(name="ایمنی", slug="safety")
        cls.course = Course.objects.create(
            title="دوره", slug="course", category=cls.category, is_published=False
        )
        cls.session = OnlineSession.objects.create(
            course=cls.course,
            title="کلاس",
            starts_at=timezone.now() + timezone.timedelta(days=1),
        )

    def setUp(self):
        cache.clear()
        self.client.force_login(self.superuser)

    def run_action(self, obj, action: str):
        meta = obj._meta
        url = reverse(f"admin:{meta.app_label}_{meta.model_name}_changelist")
        return self.client.post(
            url, {"action": action, "_selected_action": [str(obj.pk)]}, follow=True
        )

    def test_publishing_courses_from_the_list(self):
        self.run_action(self.course, "publish_courses")

        self.course.refresh_from_db()
        self.assertTrue(self.course.is_published)

    def test_cancelling_an_online_session_from_the_list(self):
        self.run_action(self.session, "cancel_selected")

        self.session.refresh_from_db()
        self.assertEqual(self.session.status, OnlineSessionStatus.CANCELLED)

    def test_revoking_a_certificate_from_the_list(self):
        certificate = Certificate.objects.create(
            user=self.superuser,
            course=self.course,
            certificate_code="HSE-1405-00001",
            holder_name="مدیر سایت",
            course_title=self.course.title,
        )

        self.run_action(certificate, "revoke_selected")

        certificate.refresh_from_db()
        self.assertEqual(certificate.status, CertificateStatus.REVOKED)
        self.assertTrue(certificate.revoke_reason)
