"""
پنل مدیریت مقاله و خبر.

این پنل از همین امروز کار می‌کند — حتی وقتی صفحات عمومی خاموش‌اند. هدف
فاز ۱۹ دقیقاً همین است: تیم محتوا بتواند مطلب‌ها را وارد کند و آماده نگه
دارد، تا روزی که بخش مقالات روشن می‌شود سایت خالی نباشد.
"""

from django.contrib import admin
from django.utils import timezone
from django.utils.html import format_html

from .models import BlogCategory, BlogPost, PostStatus


@admin.register(BlogCategory)
class BlogCategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "post_count", "order", "is_active")
    list_editable = ("order", "is_active")
    list_filter = ("is_active",)
    search_fields = ("name", "description")
    prepopulated_fields = {"slug": ("name",)}
    ordering = ("order", "name")

    fieldsets = (
        ("دسته‌بندی", {"fields": ("name", "slug", "description")}),
        ("نمایش", {"fields": ("order", "is_active")}),
        ("سئو", {"fields": ("meta_title", "meta_description"), "classes": ("collapse",)}),
    )

    @admin.display(description="تعداد مطلب")
    def post_count(self, obj: BlogCategory) -> int:
        return obj.posts.count()


@admin.register(BlogPost)
class BlogPostAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "category",
        "post_type",
        "author_name",
        "published_at",
        "status_badge",
    )
    list_filter = ("status", "post_type", "category", "is_featured")
    search_fields = ("title", "summary", "content")
    prepopulated_fields = {"slug": ("title",)}
    autocomplete_fields = ("category", "author")
    date_hierarchy = "published_at"
    ordering = ("-published_at",)
    list_per_page = 30
    readonly_fields = ("created_at", "updated_at", "reading_time_display")

    fieldsets = (
        ("مطلب", {"fields": ("title", "slug", "category", "post_type", "author")}),
        (
            "محتوا",
            {
                "description": "چکیده در کارت مطلب و نتایج جست‌وجو دیده می‌شود.",
                "fields": ("summary", "content", "cover", "reading_time_display"),
            },
        ),
        (
            "انتشار",
            {
                "description": (
                    "تاریخ انتشارِ آینده یعنی مطلب زمان‌بندی شده است و تا رسیدن آن "
                    "لحظه در سایت دیده نمی‌شود."
                ),
                "fields": ("status", "published_at", "is_featured"),
            },
        ),
        ("سئو", {"fields": ("meta_title", "meta_description"), "classes": ("collapse",)}),
        ("تاریخ‌ها", {"fields": ("created_at", "updated_at"), "classes": ("collapse",)}),
    )

    @admin.display(description="زمان مطالعه")
    def reading_time_display(self, obj: BlogPost) -> str:
        if not obj.pk:
            return "بعد از ذخیره محاسبه می‌شود."
        return f"حدود {obj.reading_minutes} دقیقه ({obj.word_count} کلمه)"

    @admin.display(description="وضعیت", ordering="status")
    def status_badge(self, obj: BlogPost):
        if obj.is_scheduled:
            return format_html('<span style="color:#2471a3">زمان‌بندی‌شده</span>')

        colors = {
            PostStatus.PUBLISHED: "#1e8449",
            PostStatus.DRAFT: "#d99400",
            PostStatus.ARCHIVED: "#7f8c8d",
        }
        return format_html(
            '<span style="color:{};font-weight:600">{}</span>',
            colors.get(obj.status, "#000"),
            obj.get_status_display(),
        )

    @admin.action(description="انتشار مطالب انتخاب‌شده")
    def publish_selected(self, request, queryset):
        updated = queryset.update(status=PostStatus.PUBLISHED)
        self.message_user(request, f"{updated} مطلب منتشر شد.")

    @admin.action(description="بازگرداندن به پیش‌نویس")
    def unpublish_selected(self, request, queryset):
        updated = queryset.update(status=PostStatus.DRAFT)
        self.message_user(request, f"{updated} مطلب به پیش‌نویس برگشت.")

    actions = ("publish_selected", "unpublish_selected")

    def get_changeform_initial_data(self, request):
        """نویسنده پیش‌فرض، همان کسی است که دارد مطلب را می‌نویسد."""
        return {"author": request.user.pk, "published_at": timezone.now()}

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("category", "author")
