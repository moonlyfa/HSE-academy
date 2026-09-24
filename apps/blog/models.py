"""
مدل‌های مقاله و خبر.

**این بخش در نسخه اول منتشر نمی‌شود.** زیرساختش کامل ساخته می‌شود و پنل
مدیریتش کار می‌کند، اما صفحات عمومی‌اش با یک کلید در فایل `.env` خاموش
است (`BLOG_ENABLED=False`).

چرا این‌طور؟ چون نوشتن ده مقاله خوب، کار چند هفته‌ی یک نویسنده است نه کار
برنامه‌نویس. با این ساختار، تیم محتوا از همین حالا می‌تواند مقاله‌ها را
وارد کند و ببیند، و روزی که به اندازه کافی مطلب آماده شد، بخش مقالات با
عوض کردن **یک خط** روشن می‌شود — بدون اینکه کدی تغییر کند یا مهاجرت
تازه‌ای لازم باشد.

قاعده‌ای که این مدل‌ها را شکل داده: **«منتشر شده» یعنی سه شرط با هم.**
وضعیت روی «منتشرشده» باشد، تاریخ انتشارش رسیده باشد، و دسته‌بندی‌اش فعال
باشد. تاریخ انتشار آینده یعنی مقاله زمان‌بندی‌شده است — نویسنده می‌تواند
پنج مقاله را جمعه بنویسد و برای پنج هفته بعد تنظیم کند.
"""

from __future__ import annotations

import re

from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils import timezone
from django.utils.text import slugify

# سرعت تقریبی مطالعه فارسی برای تخمین «زمان مطالعه».
WORDS_PER_MINUTE = 200


class BlogCategory(models.Model):
    """دسته‌بندی مقاله‌ها و خبرها."""

    name = models.CharField("نام دسته‌بندی", max_length=100)
    slug = models.SlugField(
        "نامک (آدرس)",
        max_length=120,
        unique=True,
        allow_unicode=True,
        help_text="در آدرس صفحه استفاده می‌شود. خالی بگذارید تا از روی نام ساخته شود.",
    )
    description = models.TextField("توضیح کوتاه", blank=True)
    order = models.PositiveIntegerField("ترتیب نمایش", default=0)
    is_active = models.BooleanField("فعال", default=True)

    meta_title = models.CharField("عنوان سئو", max_length=70, blank=True)
    meta_description = models.CharField("توضیحات سئو", max_length=160, blank=True)

    created_at = models.DateTimeField("تاریخ ایجاد", auto_now_add=True)

    class Meta:
        verbose_name = "دسته‌بندی مقاله"
        verbose_name_plural = "دسته‌بندی‌های مقاله"
        ordering = ["order", "name"]

    def __str__(self) -> str:
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name, allow_unicode=True)
        super().save(*args, **kwargs)

    def get_absolute_url(self) -> str:
        return f"{reverse('blog:list')}?category={self.slug}"

    @property
    def published_post_count(self) -> int:
        return self.posts.published().count()


class PostType(models.TextChoices):
    """
    مقاله و خبر در یک جدول‌اند، نه دو تا.

    ساختارشان یکی است (عنوان، متن، تصویر، نویسنده) و تفاوتشان فقط در
    نحوه نمایش است. دو جدول جدا یعنی دو پنل مدیریت، دو صفحه فهرست و دو
    نسخه از هر تغییر آینده.
    """

    ARTICLE = "article", "مقاله"
    NEWS = "news", "خبر"


class PostStatus(models.TextChoices):
    DRAFT = "draft", "پیش‌نویس"
    PUBLISHED = "published", "منتشرشده"
    ARCHIVED = "archived", "بایگانی‌شده"


class PostQuerySet(models.QuerySet):
    def published(self):
        """
        مطالبی که همین حالا باید در سایت دیده شوند.

        شرط تاریخ، زمان‌بندی انتشار را ممکن می‌کند: مقاله‌ای با تاریخ
        آینده نوشته و ذخیره می‌شود اما تا رسیدن آن لحظه در سایت نیست.
        """
        return self.filter(
            status=PostStatus.PUBLISHED,
            published_at__lte=timezone.now(),
            category__is_active=True,
        ).select_related("category", "author")

    def articles(self):
        return self.filter(post_type=PostType.ARTICLE)

    def news(self):
        return self.filter(post_type=PostType.NEWS)


class BlogPost(models.Model):
    """یک مقاله یا خبر."""

    title = models.CharField("عنوان", max_length=200)
    slug = models.SlugField(
        "نامک (آدرس)",
        max_length=220,
        unique=True,
        allow_unicode=True,
        help_text="خالی بگذارید تا از روی عنوان ساخته شود.",
    )
    category = models.ForeignKey(
        BlogCategory,
        verbose_name="دسته‌بندی",
        on_delete=models.PROTECT,
        related_name="posts",
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="نویسنده",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="blog_posts",
        help_text="خالی یعنی مطلب به نام خود آکادمی منتشر می‌شود.",
    )
    post_type = models.CharField(
        "نوع مطلب",
        max_length=20,
        choices=PostType.choices,
        default=PostType.ARTICLE,
    )

    summary = models.TextField(
        "چکیده",
        max_length=400,
        help_text="در کارت مطلب و نتایج جست‌وجو نمایش داده می‌شود.",
    )
    content = models.TextField("متن مطلب")
    cover = models.ImageField(
        "تصویر شاخص",
        upload_to="blog/",
        blank=True,
        null=True,
        help_text="اندازه پیشنهادی ۱۲۰۰×۶۳۰ پیکسل.",
    )

    status = models.CharField(
        "وضعیت",
        max_length=20,
        choices=PostStatus.choices,
        default=PostStatus.DRAFT,
    )
    published_at = models.DateTimeField(
        "تاریخ انتشار",
        default=timezone.now,
        help_text="تاریخ آینده یعنی مطلب زمان‌بندی شده و تا آن لحظه در سایت دیده نمی‌شود.",
    )
    is_featured = models.BooleanField("مطلب منتخب", default=False)

    meta_title = models.CharField("عنوان سئو", max_length=70, blank=True)
    meta_description = models.CharField("توضیحات سئو", max_length=160, blank=True)

    created_at = models.DateTimeField("تاریخ ایجاد", auto_now_add=True)
    updated_at = models.DateTimeField("آخرین ویرایش", auto_now=True)

    objects = PostQuerySet.as_manager()

    class Meta:
        verbose_name = "مقاله و خبر"
        verbose_name_plural = "مقاله‌ها و خبرها"
        ordering = ["-published_at", "-id"]
        indexes = [
            models.Index(fields=["status", "published_at"]),
            models.Index(fields=["post_type", "status"]),
        ]

    def __str__(self) -> str:
        return self.title

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.title, allow_unicode=True)
        super().save(*args, **kwargs)

    def get_absolute_url(self) -> str:
        return reverse("blog:detail", kwargs={"slug": self.slug})

    @property
    def is_scheduled(self) -> bool:
        """منتشرشده اما تاریخش هنوز نرسیده است."""
        return self.status == PostStatus.PUBLISHED and self.published_at > timezone.now()

    @property
    def is_visible(self) -> bool:
        """
        آیا این مطلب همین حالا در سایت دیده می‌شود؟

        همان سه شرط `published()` است، اما برای یک ردیفِ در دست — تا
        View لازم نباشد برای یک مطلب دوباره به دیتابیس برود.
        """
        return (
            self.status == PostStatus.PUBLISHED
            and self.published_at <= timezone.now()
            and self.category.is_active
        )

    @property
    def author_name(self) -> str:
        """نام نویسنده برای نمایش؛ اگر نویسنده‌ای ثبت نشده، نام آکادمی."""
        if self.author and self.author.full_name:
            return self.author.full_name
        return settings.SITE_NAME

    @property
    def word_count(self) -> int:
        return len(re.findall(r"\S+", self.content))

    @property
    def reading_minutes(self) -> int:
        """زمان تقریبی مطالعه — حداقل یک دقیقه، تا «۰ دقیقه» ننویسیم."""
        return max(round(self.word_count / WORDS_PER_MINUTE), 1)
