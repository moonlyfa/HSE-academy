"""پنل مدیریت دسته‌بندی‌ها و دوره‌ها."""

from django.contrib import admin
from django.utils.html import format_html

from .models import Course, CourseCategory


@admin.register(CourseCategory)
class CourseCategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "parent", "course_count", "show_on_homepage", "is_active", "order")
    list_editable = ("show_on_homepage", "is_active", "order")
    list_filter = ("is_active", "show_on_homepage", "parent")
    search_fields = ("name", "description")
    # اسلاگ به‌صورت خودکار از روی نام پر می‌شود.
    prepopulated_fields = {"slug": ("name",)}
    ordering = ("order", "name")
    list_per_page = 30

    fieldsets = (
        ("اطلاعات اصلی", {"fields": ("name", "slug", "description", "parent")}),
        ("نمایش", {"fields": ("icon", "image", "show_on_homepage", "is_active", "order")}),
        ("سئو", {"fields": ("meta_title", "meta_description"), "classes": ("collapse",)}),
    )

    @admin.display(description="تعداد دوره")
    def course_count(self, obj: CourseCategory) -> int:
        return obj.published_course_count


@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "category",
        "instructor",
        "course_type",
        "start_date",
        "price_display",
        "is_featured",
        "is_published",
    )
    list_editable = ("is_featured", "is_published")
    list_filter = (
        "is_published",
        "is_featured",
        "course_type",
        "level",
        "category",
        "certificate_available",
        "start_date",
    )
    search_fields = ("title", "short_description", "full_description")
    prepopulated_fields = {"slug": ("title",)}
    date_hierarchy = "start_date"
    autocomplete_fields = ("category",)
    ordering = ("-created_at",)
    list_per_page = 25
    readonly_fields = ("created_at", "updated_at", "thumbnail_preview")

    fieldsets = (
        (
            "اطلاعات اصلی",
            {"fields": ("title", "slug", "category", "instructor", "short_description")},
        ),
        ("توضیحات", {"fields": ("full_description", "target_audience", "prerequisites", "syllabus")}),
        ("شیوه برگزاری", {"fields": ("course_type", "level", "location")}),
        (
            "زمان‌بندی و ظرفیت",
            {"fields": ("start_date", "end_date", "duration_hours", "capacity")},
        ),
        (
            "قیمت",
            {
                "description": "قیمت‌ها به تومان وارد شوند. صفر یعنی دوره رایگان است.",
                "fields": ("price", "discount_price"),
            },
        ),
        ("تصاویر", {"fields": ("thumbnail", "thumbnail_preview", "hero_image")}),
        ("امکانات", {"fields": ("certificate_available", "exam_available")}),
        ("وضعیت انتشار", {"fields": ("is_featured", "is_published", "created_at", "updated_at")}),
        ("سئو", {"fields": ("meta_title", "meta_description"), "classes": ("collapse",)}),
    )

    @admin.display(description="قیمت")
    def price_display(self, obj: Course) -> str:
        if obj.is_free:
            return "رایگان"
        if obj.has_discount:
            return f"{obj.final_price:,} ({obj.discount_percent}٪ تخفیف)"
        return f"{obj.price:,}"

    @admin.display(description="پیش‌نمایش تصویر")
    def thumbnail_preview(self, obj: Course):
        if obj.thumbnail:
            return format_html(
                '<img src="{}" style="max-height:100px;border-radius:8px;">', obj.thumbnail.url
            )
        return "—"

    @admin.action(description="انتشار دوره‌های انتخاب‌شده")
    def publish_courses(self, request, queryset):
        updated = queryset.update(is_published=True)
        self.message_user(request, f"{updated} دوره منتشر شد.")

    @admin.action(description="لغو انتشار دوره‌های انتخاب‌شده")
    def unpublish_courses(self, request, queryset):
        updated = queryset.update(is_published=False)
        self.message_user(request, f"{updated} دوره از انتشار خارج شد.")

    actions = ("publish_courses", "unpublish_courses")
