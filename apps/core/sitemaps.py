"""
نقشه سایت (sitemap.xml).

نقشه سایت فهرستی از آدرس‌های قابل ایندکس است که به موتور جست‌وجو می‌گوید
«اینها صفحه‌های واقعی سایت‌اند و هرکدام آخرین بار کِی عوض شده‌اند». بدون
آن، گوگل باید صفحه‌ها را فقط از راه دنبال‌کردن لینک‌ها پیدا کند و
صفحه‌های تازه دیرتر دیده می‌شوند.

دو قاعده در کل این فایل رعایت شده است:

**۱. فقط چیزی که واقعاً عمومی است.** دوره منتشرنشده، مقاله پیش‌نویس،
دسته‌بندی غیرفعال و هر صفحه‌ای که ورود می‌خواهد (داشبورد، سبد خرید،
آزمون، گواهی) در نقشه سایت نمی‌آید. آدرس خصوصی در نقشه سایت یعنی دعوت
مستقیم از خزنده‌ها به جایی که نباید بروند.

**۲. `lastmod` از خود داده می‌آید،** نه از تاریخ امروز. اگر هر بار
«همین حالا» بفرستیم، گوگل بعد از چند بار می‌فهمد این عدد بی‌معنی است و
دیگر به آن اعتماد نمی‌کند.
"""

from __future__ import annotations

from django.conf import settings
from django.contrib.sitemaps import Sitemap
from django.urls import reverse

from apps.accounts.models import InstructorProfile
from apps.blog.models import BlogCategory, BlogPost
from apps.courses.models import Course, CourseCategory


class StaticViewSitemap(Sitemap):
    """صفحه‌های ثابت سایت."""

    changefreq = "weekly"
    protocol = "https"

    # اولویت‌ها نسبی‌اند: صفحه اصلی و فهرست دوره‌ها مهم‌ترین‌اند، و
    # صفحه‌های قانونی کمترین اهمیت را دارند.
    PAGES = {
        "core:home": 1.0,
        "courses:list": 0.9,
        "core:calendar": 0.8,
        "core:instructors": 0.7,
        "core:certificate_verify": 0.6,
        "core:about": 0.5,
        "core:contact": 0.5,
        "core:faq": 0.5,
        "core:privacy": 0.3,
        "core:terms": 0.3,
    }

    def items(self) -> list[str]:
        return list(self.PAGES)

    def location(self, item: str) -> str:
        return reverse(item)

    def priority(self, item: str) -> float:
        return self.PAGES[item]


class CourseSitemap(Sitemap):
    """دوره‌های منتشرشده — مهم‌ترین صفحه‌های سایت برای جست‌وجو."""

    changefreq = "weekly"
    priority = 0.9
    protocol = "https"

    def items(self):
        return Course.objects.published().order_by("-updated_at")

    def lastmod(self, item: Course):
        return item.updated_at


class CourseCategorySitemap(Sitemap):
    changefreq = "weekly"
    priority = 0.6
    protocol = "https"

    def items(self):
        return CourseCategory.objects.filter(is_active=True)

    def lastmod(self, item: CourseCategory):
        return item.updated_at


class InstructorSitemap(Sitemap):
    changefreq = "monthly"
    priority = 0.5
    protocol = "https"

    def items(self):
        return InstructorProfile.objects.filter(is_active=True)


class BlogPostSitemap(Sitemap):
    """
    مقاله‌ها — فقط وقتی بخش مقالات روشن باشد.

    اگر خاموش است، آدرس‌هایش ۴۰۴ می‌دهند؛ فرستادن آدرس ۴۰۴ به گوگل
    اعتبار سایت را پایین می‌آورد.
    """

    changefreq = "monthly"
    priority = 0.7
    protocol = "https"

    def items(self):
        if not settings.BLOG_ENABLED:
            return BlogPost.objects.none()
        return BlogPost.objects.published()

    def lastmod(self, item: BlogPost):
        return item.updated_at


class BlogCategorySitemap(Sitemap):
    changefreq = "monthly"
    priority = 0.4
    protocol = "https"

    def items(self):
        if not settings.BLOG_ENABLED:
            return BlogCategory.objects.none()
        return BlogCategory.objects.filter(is_active=True)


SITEMAPS = {
    "static": StaticViewSitemap,
    "courses": CourseSitemap,
    "categories": CourseCategorySitemap,
    "instructors": InstructorSitemap,
    "posts": BlogPostSitemap,
    "post-categories": BlogCategorySitemap,
}
