"""
تست‌های فاز ۲۰ — سئو.

سئو چیزی است که هیچ‌کس در کار روزمره نمی‌بیند، پس بی‌سروصدا خراب می‌شود:
یک فیلتر تازه، ده نسخه تکراری از یک صفحه می‌سازد؛ یک آدرس خصوصی در نقشه
سایت، خزنده را به داشبورد کاربران می‌فرستد. این تست‌ها همان‌ها را
می‌گیرند.
"""

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import InstructorProfile
from apps.blog.models import BlogCategory, BlogPost, PostStatus
from apps.core.seo import listing_seo
from apps.courses.models import Course, CourseCategory

User = get_user_model()


class SeoTestMixin:
    @classmethod
    def setUpTestData(cls):
        cls.category = CourseCategory.objects.create(name="ایمنی صنعتی", slug="safety")
        cls.published = Course.objects.create(
            title="دوره منتشرشده",
            slug="published-course",
            category=cls.category,
            price=1_000_000,
            is_published=True,
        )
        cls.draft = Course.objects.create(
            title="دوره منتشرنشده",
            slug="draft-course",
            category=cls.category,
            is_published=False,
        )
        cls.instructor = InstructorProfile.objects.create(
            display_name="مهندس سعید کاظمی",
            specialty="ایمنی صنعتی",
            bio="بیست سال سابقه اجرایی",
            is_active=True,
        )


class RobotsTests(SeoTestMixin, TestCase):
    def test_robots_is_plain_text(self):
        response = self.client.get("/robots.txt")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response["Content-Type"].startswith("text/plain"))

    def test_robots_points_to_the_sitemap_with_a_full_url(self):
        body = self.client.get("/robots.txt").content.decode()
        self.assertIn("Sitemap: http://testserver/sitemap.xml", body)

    def test_private_areas_are_disallowed(self):
        """آدرس‌های شخصی و خرید نباید خزیده شوند."""
        body = self.client.get("/robots.txt").content.decode()

        for path in ["/accounts/", "/cart/", "/orders/", "/exam/", "/certificates/"]:
            self.assertIn(f"Disallow: {path}", body)

    def test_public_pages_are_not_disallowed(self):
        body = self.client.get("/robots.txt").content.decode()

        self.assertNotIn("Disallow: /courses/", body)
        self.assertNotIn("Disallow: /\n", body)

    @override_settings(SEO_ALLOW_INDEXING=False)
    def test_staging_server_closes_everything(self):
        body = self.client.get("/robots.txt").content.decode()

        self.assertIn("Disallow: /", body)
        self.assertNotIn("Sitemap:", body)

    @override_settings(SEO_ALLOW_INDEXING=False)
    def test_staging_server_also_marks_pages_noindex(self):
        """robots.txt به تنهایی کافی نیست؛ صفحه‌ای که از جای دیگر لینک شده هم باید بسته باشد."""
        response = self.client.get(reverse("core:home"))
        self.assertContains(response, 'content="noindex, nofollow"')


class SitemapTests(SeoTestMixin, TestCase):
    def test_sitemap_lists_public_pages(self):
        body = self.client.get("/sitemap.xml").content.decode()

        self.assertIn("/courses/", body)
        self.assertIn(self.published.get_absolute_url(), body)
        self.assertIn(self.instructor.get_absolute_url(), body)

    def test_unpublished_course_is_not_listed(self):
        body = self.client.get("/sitemap.xml").content.decode()
        self.assertNotIn(self.draft.get_absolute_url(), body)

    def test_private_pages_are_not_listed(self):
        body = self.client.get("/sitemap.xml").content.decode()

        for path in ["/accounts/", "/cart/", "/orders/", "/exam/", "/certificates/"]:
            self.assertNotIn(f"<loc>https://testserver{path}", body)

    def test_lastmod_comes_from_the_data(self):
        body = self.client.get("/sitemap.xml").content.decode()
        self.assertIn("<lastmod>", body)

    def test_blog_urls_stay_out_while_the_section_is_off(self):
        """آدرسی که ۴۰۴ می‌دهد نباید به گوگل معرفی شود."""
        category = BlogCategory.objects.create(name="دانش فنی", slug="knowledge")
        post = BlogPost.objects.create(
            title="مطلب",
            slug="post",
            category=category,
            summary="چکیده",
            content="متن",
            status=PostStatus.PUBLISHED,
            published_at=timezone.now(),
        )

        body = self.client.get("/sitemap.xml").content.decode()
        self.assertNotIn(post.get_absolute_url(), body)

        with self.settings(BLOG_ENABLED=True):
            body = self.client.get("/sitemap.xml").content.decode()
            self.assertIn(post.get_absolute_url(), body)


class ListingSeoTests(TestCase):
    """قاعده آدرس اصلی و ایندکس در صفحه‌های فیلتردار."""

    def setUp(self):
        self.base = reverse("courses:list")

    def result(self, query=""):
        request = self.client.request(PATH_INFO=self.base, QUERY_STRING=query).wsgi_request
        return listing_seo(request, self.base)

    def test_clean_listing_is_indexable(self):
        seo = self.result()
        self.assertFalse(seo["noindex"])
        self.assertTrue(seo["canonical"].endswith(self.base))

    def test_category_page_is_a_real_page(self):
        seo = self.result("category=safety")

        self.assertFalse(seo["noindex"])
        self.assertTrue(seo["canonical"].endswith("?category=safety"))

    def test_sort_and_filters_are_not_pages(self):
        seo = self.result("sort=cheapest&level=advanced")

        self.assertTrue(seo["noindex"])
        self.assertTrue(seo["canonical"].endswith(self.base))

    def test_pagination_keeps_its_own_canonical(self):
        """صفحه دوم محتوای دیگری دارد؛ نباید خودش را صفحه اول جا بزند."""
        seo = self.result("page=2")

        self.assertFalse(seo["noindex"])
        self.assertTrue(seo["canonical"].endswith("?page=2"))

    def test_category_plus_filter_falls_back_to_the_clean_url(self):
        seo = self.result("category=safety&sort=cheapest")

        self.assertTrue(seo["noindex"])
        self.assertTrue(seo["canonical"].endswith(self.base))


class PageSeoTests(SeoTestMixin, TestCase):
    """آنچه در <head> هر صفحه می‌نشیند."""

    def test_filtered_listing_is_noindex_but_still_followed(self):
        response = self.client.get(reverse("courses:list"), {"sort": "cheapest"})
        self.assertContains(response, 'content="noindex, follow"')

    def test_category_listing_is_indexable(self):
        response = self.client.get(reverse("courses:list"), {"category": "safety"})
        self.assertNotContains(response, "noindex")

    def test_search_results_are_never_indexed(self):
        response = self.client.get(reverse("core:search"), {"q": "ایمنی"})
        self.assertContains(response, "noindex")

    def test_every_page_declares_its_language_and_share_card(self):
        response = self.client.get(reverse("core:home"))

        self.assertContains(response, 'property="og:locale" content="fa_IR"')
        self.assertContains(response, 'name="twitter:card"')
        self.assertContains(response, 'property="og:url"')


class StructuredDataTests(SeoTestMixin, TestCase):
    """داده ساختاریافته فقط چیزی را می‌گوید که روی صفحه هم هست."""

    def test_home_introduces_the_organization_and_the_site(self):
        response = self.client.get(reverse("core:home"))

        self.assertContains(response, '"@type": "EducationalOrganization"')
        self.assertContains(response, '"@type": "WebSite"')
        self.assertContains(response, '"@type": "SearchAction"')

    def test_course_page_describes_the_course(self):
        response = self.client.get(self.published.get_absolute_url())

        self.assertContains(response, '"@type": "Course"')
        self.assertContains(response, '"priceCurrency": "IRR"')

    def test_instructor_page_describes_the_person(self):
        response = self.client.get(self.instructor.get_absolute_url())

        self.assertContains(response, '"@type": "Person"')
        self.assertContains(response, "مهندس سعید کاظمی")

    def test_faq_page_marks_up_its_questions(self):
        from apps.core.models import FAQ

        FAQ.objects.create(question="گواهی چطور صادر می‌شود؟", answer="پس از آزمون.")

        response = self.client.get(reverse("core:faq"))

        self.assertContains(response, '"@type": "FAQPage"')
        self.assertContains(response, '"@type": "Question"')

    def test_faq_markup_is_skipped_when_there_are_no_questions(self):
        response = self.client.get(reverse("core:faq"))
        self.assertNotContains(response, "FAQPage")

    @override_settings(BLOG_ENABLED=True)
    def test_article_page_marks_up_the_article(self):
        category = BlogCategory.objects.create(name="دانش فنی", slug="knowledge")
        post = BlogPost.objects.create(
            title="مطلب نمونه",
            slug="sample",
            category=category,
            summary="چکیده",
            content="متن",
            status=PostStatus.PUBLISHED,
            published_at=timezone.now(),
        )

        response = self.client.get(post.get_absolute_url())

        self.assertContains(response, '"@type": "Article"')
        self.assertContains(response, '"datePublished"')

    @override_settings(BLOG_ENABLED=True)
    def test_unpublished_article_gets_no_markup(self):
        """پیش‌نمایش مدیر نباید به گوگل معرفی شود."""
        category = BlogCategory.objects.create(name="دانش فنی", slug="knowledge")
        post = BlogPost.objects.create(
            title="پیش‌نویس",
            slug="draft-post",
            category=category,
            summary="چکیده",
            content="متن",
            status=PostStatus.DRAFT,
        )
        staff = User.objects.create_user(mobile="09120000000", is_staff=True)
        self.client.force_login(staff)

        response = self.client.get(post.get_absolute_url())

        self.assertContains(response, "noindex")
        self.assertNotContains(response, '"@type": "Article"')
