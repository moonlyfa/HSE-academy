"""
Viewهای مقاله و خبر.

همه صفحه‌های این اپ پشت یک کلید هستند: تا وقتی `BLOG_ENABLED=False` است،
هر آدرس این بخش ۴۰۴ می‌دهد — نه صفحه «به‌زودی».

چرا ۴۰۴ و نه «به‌زودی»؟ چون صفحه «به‌زودی» به گوگل می‌گوید این آدرس وجود
دارد و ایندکسش می‌کند؛ بعداً باید همان آدرسِ ایندکس‌شده را با محتوای
واقعی جایگزین کنیم. تا وقتی مطلبی برای نشان دادن نیست، بهتر است این
بخش اصلاً وجود نداشته باشد.
"""

from __future__ import annotations

from django.conf import settings
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, render
from django.urls import reverse

from apps.core.seo import listing_seo
from django.utils import timezone

from .models import BlogCategory, BlogPost, PostStatus, PostType

PAGE_SIZE = 9


def _require_blog() -> None:
    if not settings.BLOG_ENABLED:
        raise Http404("بخش مقالات فعال نیست.")


def _sidebar_context() -> dict:
    """
    داده‌های مشترک ستون کناری: دسته‌بندی‌ها و مطالب منتخب.

    شمارنده کنار هر دسته باید دقیقاً همان چیزی را بشمارد که کاربر با
    کلیک روی آن می‌بیند؛ وگرنه روی «۲ مطلب» کلیک می‌کند و یک مطلب
    می‌بیند. پس شرط تاریخ انتشار هم — مثل `published()` — اینجا هست.
    """
    return {
        "categories": BlogCategory.objects.filter(is_active=True).annotate(
            num_posts=Count(
                "posts",
                filter=Q(
                    posts__status=PostStatus.PUBLISHED,
                    posts__published_at__lte=timezone.now(),
                ),
            )
        ),
        "featured_posts": BlogPost.objects.published().filter(is_featured=True)[:4],
    }


def post_list(request: HttpRequest) -> HttpResponse:
    """فهرست مقاله‌ها و خبرها با فیلتر دسته‌بندی، نوع و جست‌وجو."""
    _require_blog()

    posts = BlogPost.objects.published()

    category_slug = request.GET.get("category", "")
    if category_slug:
        posts = posts.filter(category__slug=category_slug)

    post_type = request.GET.get("type", "")
    if post_type in PostType.values:
        posts = posts.filter(post_type=post_type)

    query = request.GET.get("q", "").strip()
    if query:
        posts = posts.filter(
            Q(title__icontains=query)
            | Q(summary__icontains=query)
            | Q(content__icontains=query)
        )

    paginator = Paginator(posts, PAGE_SIZE)
    page = paginator.get_page(request.GET.get("page"))

    params = request.GET.copy()
    params.pop("page", None)

    active_category = None
    if category_slug:
        active_category = BlogCategory.objects.filter(
            slug=category_slug, is_active=True
        ).first()

    seo = listing_seo(request, reverse("blog:list"))

    return render(
        request,
        "blog/post_list.html",
        {
            "page_obj": page,
            "posts": page.object_list,
            "total_count": paginator.count,
            "querystring": params.urlencode(),
            "active_category": active_category,
            "post_types": PostType.choices,
            "selected_type": post_type,
            "query": query,
            "breadcrumb_current": active_category.name if active_category else "مقالات و اخبار",
            "breadcrumb_items": (
                [{"label": "مقالات و اخبار", "url": reverse("blog:list")}]
                if active_category
                else []
            ),
            "nav_active": "blog",
            "seo_canonical": seo["canonical"],
            "page_noindex": seo["noindex"],
            **_sidebar_context(),
        },
    )


def post_detail(request: HttpRequest, slug: str) -> HttpResponse:
    """
    یک مطلب.

    مدیر سایت پیش‌نویس و مطلب زمان‌بندی‌شده را هم می‌بیند تا بتواند پیش از
    انتشار بازبینی کند؛ برای بقیه، چنین مطلبی وجود ندارد.
    """
    _require_blog()

    post = get_object_or_404(
        BlogPost.objects.select_related("category", "author"), slug=slug
    )

    if not post.is_visible and not request.user.is_staff:
        raise Http404("این مطلب منتشر نشده است.")

    related = (
        BlogPost.objects.published()
        .filter(category=post.category)
        .exclude(pk=post.pk)[:3]
    )

    return render(
        request,
        "blog/post_detail.html",
        {
            "post": post,
            "related_posts": related,
            "is_preview": not post.is_visible,
            "breadcrumb_items": [
                {"label": "مقالات و اخبار", "url": reverse("blog:list")},
                {"label": post.category.name, "url": post.category.get_absolute_url()},
            ],
            "breadcrumb_current": post.title,
            "nav_active": "blog",
            **_sidebar_context(),
        },
    )
