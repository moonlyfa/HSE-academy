"""
تست‌های فاز ۱۹ — زیرساخت مقاله و خبر.

دو چیز را نگه می‌دارند:

۱. **تا وقتی کلید خاموش است، این بخش اصلاً وجود ندارد** — نه صفحه
   «به‌زودی»، نه لینکی در منو.
۲. **«منتشر شده» یعنی هر سه شرط با هم**: وضعیت منتشرشده، تاریخ انتشار
   رسیده، و دسته‌بندی فعال. پیش‌نویس و مطلب زمان‌بندی‌شده نباید از هیچ
   مسیری به بازدیدکننده برسند.
"""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.blog.models import BlogCategory, BlogPost, PostStatus, PostType

User = get_user_model()


class BlogTestMixin:
    @classmethod
    def setUpTestData(cls):
        cls.category = BlogCategory.objects.create(name="دانش فنی", slug="knowledge")
        cls.other_category = BlogCategory.objects.create(name="اخبار", slug="news")

        cls.author = User.objects.create_user(
            mobile="09121234567", first_name="سارا", last_name="محمدی"
        )
        cls.staff = User.objects.create_user(mobile="09120000000", is_staff=True)

        cls.published = cls.make_post("مطلب منتشرشده", slug="published")
        cls.draft = cls.make_post(
            "مطلب پیش‌نویس", slug="draft", status=PostStatus.DRAFT
        )
        cls.scheduled = cls.make_post(
            "مطلب زمان‌بندی‌شده",
            slug="scheduled",
            published_at=timezone.now() + timedelta(days=3),
        )

    @classmethod
    def make_post(cls, title, *, slug="", category=None, **kwargs):
        defaults = {
            "title": title,
            "slug": slug,
            "category": category or cls.category,
            "author": cls.author,
            "summary": "چکیده نمونه",
            "content": "متن نمونه " * 50,
            "status": PostStatus.PUBLISHED,
            "published_at": timezone.now() - timedelta(days=1),
        }
        defaults.update(kwargs)
        return BlogPost.objects.create(**defaults)


class BlogModelTests(BlogTestMixin, TestCase):
    def test_only_published_and_due_posts_are_visible(self):
        visible = list(BlogPost.objects.published())

        self.assertIn(self.published, visible)
        self.assertNotIn(self.draft, visible)
        self.assertNotIn(self.scheduled, visible)

    def test_scheduled_post_knows_it_is_waiting(self):
        self.assertTrue(self.scheduled.is_scheduled)
        self.assertFalse(self.scheduled.is_visible)
        self.assertFalse(self.published.is_scheduled)

    def test_deactivating_a_category_hides_its_posts(self):
        """دسته‌بندی خاموش‌شده نباید مطلبش از جای دیگری بیرون بزند."""
        self.category.is_active = False
        self.category.save(update_fields=["is_active"])

        self.assertNotIn(self.published, BlogPost.objects.published())
        self.assertFalse(BlogPost.objects.get(pk=self.published.pk).is_visible)

    def test_slug_is_built_from_the_persian_title(self):
        post = self.make_post("ایمنی کار در ارتفاع")
        self.assertEqual(post.slug, "ایمنی-کار-در-ارتفاع")

    def test_reading_time_is_never_zero(self):
        post = self.make_post("مطلب کوتاه", slug="short", content="دو کلمه")
        self.assertEqual(post.reading_minutes, 1)

    def test_reading_time_grows_with_the_text(self):
        post = self.make_post("مطلب بلند", slug="long", content="کلمه " * 1000)
        self.assertEqual(post.reading_minutes, 5)

    def test_post_without_an_author_is_published_under_the_site_name(self):
        from django.conf import settings

        post = self.make_post("بدون نویسنده", slug="anonymous", author=None)
        self.assertEqual(post.author_name, settings.SITE_NAME)

    def test_author_name_uses_the_real_name(self):
        self.assertEqual(self.published.author_name, "سارا محمدی")


class BlogDisabledTests(BlogTestMixin, TestCase):
    """حالت پیش‌فرض پروژه: بخش مقالات خاموش است."""

    def test_list_is_not_found(self):
        self.assertEqual(self.client.get(reverse("blog:list")).status_code, 404)

    def test_detail_is_not_found(self):
        response = self.client.get(self.published.get_absolute_url())
        self.assertEqual(response.status_code, 404)

    def test_staff_does_not_get_a_back_door(self):
        """کلید خاموش برای همه خاموش است، حتی برای مدیر."""
        self.client.force_login(self.staff)
        self.assertEqual(self.client.get(reverse("blog:list")).status_code, 404)

    def test_menu_does_not_link_to_it(self):
        response = self.client.get(reverse("core:home"))
        self.assertNotContains(response, "مقالات و اخبار")


@override_settings(BLOG_ENABLED=True)
class BlogEnabledTests(BlogTestMixin, TestCase):
    """همان کد، با کلید روشن — بدون هیچ تغییر دیگری در پروژه."""

    def test_menu_links_to_the_blog(self):
        response = self.client.get(reverse("core:home"))
        self.assertContains(response, "مقالات و اخبار")

    def test_list_shows_published_posts_only(self):
        response = self.client.get(reverse("blog:list"))

        self.assertContains(response, self.published.title)
        self.assertNotContains(response, self.draft.title)
        self.assertNotContains(response, self.scheduled.title)

    def test_detail_page_opens(self):
        response = self.client.get(self.published.get_absolute_url())

        self.assertContains(response, self.published.title)
        self.assertContains(response, "دقیقه مطالعه")

    def test_draft_is_404_for_visitors(self):
        response = self.client.get(self.draft.get_absolute_url())
        self.assertEqual(response.status_code, 404)

    def test_scheduled_post_is_404_before_its_date(self):
        response = self.client.get(self.scheduled.get_absolute_url())
        self.assertEqual(response.status_code, 404)

    def test_staff_can_preview_a_draft(self):
        self.client.force_login(self.staff)
        response = self.client.get(self.draft.get_absolute_url())

        self.assertContains(response, "پیش‌نمایش مدیر")
        self.assertContains(response, 'name="robots" content="noindex"')

    def test_category_filter(self):
        in_news = self.make_post(
            "خبر تازه", slug="fresh-news", category=self.other_category
        )

        response = self.client.get(reverse("blog:list"), {"category": "news"})

        self.assertContains(response, in_news.title)
        self.assertNotContains(response, self.published.title)

    def test_type_filter(self):
        news = self.make_post("خبر", slug="a-news", post_type=PostType.NEWS)

        response = self.client.get(reverse("blog:list"), {"type": "news"})

        self.assertContains(response, news.title)
        self.assertNotContains(response, self.published.title)

    def test_search_looks_inside_the_text(self):
        post = self.make_post(
            "مطلب ویژه", slug="special", content="سکوی کار در ارتفاع و داربست"
        )

        response = self.client.get(reverse("blog:list"), {"q": "داربست"})

        self.assertContains(response, post.title)
        self.assertNotContains(response, self.published.title)

    def test_sidebar_count_matches_what_the_category_page_shows(self):
        """شمارنده نباید مطلب زمان‌بندی‌شده را بشمارد."""
        response = self.client.get(reverse("blog:list"))

        counts = {c.slug: c.num_posts for c in response.context["categories"]}
        self.assertEqual(counts["knowledge"], 1)

    def test_related_posts_come_from_the_same_category(self):
        sibling = self.make_post("هم‌دسته", slug="sibling")
        self.make_post("دسته دیگر", slug="elsewhere", category=self.other_category)

        response = self.client.get(self.published.get_absolute_url())

        self.assertContains(response, sibling.title)
        self.assertNotContains(response, "دسته دیگر")
