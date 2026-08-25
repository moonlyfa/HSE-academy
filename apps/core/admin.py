"""
پنل مدیریت بخش‌های عمومی سایت.

هدف: ادمین بتواند کل صفحه اصلی را بدون یک خط کد مدیریت کند.
"""

from django.contrib import admin
from django.utils.html import format_html

from .models import (
    FAQ,
    ContactMessage,
    Feature,
    HeroSlide,
    Partner,
    SiteSetting,
    Testimonial,
)


class ActiveOrderAdminMixin:
    """تنظیمات مشترک بخش‌های قابل مرتب‌سازی صفحه اصلی."""

    list_editable = ("is_active", "order")
    list_filter = ("is_active",)
    ordering = ("order",)
    list_per_page = 30


@admin.register(SiteSetting)
class SiteSettingAdmin(admin.ModelAdmin):
    """تنظیمات سایت فقط یک ردیف دارد، پس دکمه افزودن و حذف را برمی‌داریم."""

    fieldsets = (
        ("هویت سایت", {"fields": ("site_name", "site_tagline", "logo", "favicon")}),
        (
            "اطلاعات تماس",
            {"fields": ("phone", "mobile", "email", "address", "working_hours")},
        ),
        (
            "شبکه‌های اجتماعی",
            {
                "fields": ("instagram_url", "telegram_url", "linkedin_url", "whatsapp_url"),
                "classes": ("collapse",),
            },
        ),
        ("درباره ما", {"fields": ("about_short", "about_full")}),
        (
            "تنظیمات اسلایدر صفحه اصلی",
            {
                "description": "سرعت چرخش و نرمی جابه‌جایی اسلایدها از اینجا کنترل می‌شود.",
                "fields": ("hero_slider_interval_seconds", "hero_slider_transition_ms"),
            },
        ),
        (
            "نمایش بخش‌های صفحه اصلی",
            {
                "description": "با خاموش کردن هر گزینه، آن بخش از صفحه اصلی حذف می‌شود.",
                "fields": (
                    "show_hero_slider",
                    "show_calendar_section",
                    "show_categories_section",
                    "show_featured_courses",
                    "show_features_section",
                    "show_instructors_section",
                    "show_testimonials_section",
                    "show_partners_section",
                    "show_faq_section",
                    "show_articles_section",
                    "homepage_calendar_count",
                    "homepage_category_count",
                ),
            },
        ),
        ("سئو", {"fields": ("meta_title", "meta_description"), "classes": ("collapse",)}),
    )
    readonly_fields = ("updated_at",)

    def has_add_permission(self, request) -> bool:
        # فقط یک ردیف مجاز است.
        return not SiteSetting.objects.exists()

    def has_delete_permission(self, request, obj=None) -> bool:
        return False


@admin.register(HeroSlide)
class HeroSlideAdmin(ActiveOrderAdminMixin, admin.ModelAdmin):
    list_display = ("title", "preview", "visible_now", "is_active", "order")
    search_fields = ("title",)
    list_filter = ("is_active", "starts_at", "ends_at")
    readonly_fields = ("created_at", "updated_at", "preview")

    fieldsets = (
        (
            "تصویر اسلاید",
            {
                "description": "روی اسلاید هیچ متنی نوشته نمی‌شود؛ کل پیام باید داخل خود تصویر باشد.",
                "fields": ("title", "image", "preview", "image_mobile"),
            },
        ),
        ("لینک", {"fields": ("link_url",)}),
        (
            "زمان‌بندی نمایش",
            {
                "description": "برای بنر مناسبتی می‌توانید بازه نمایش تعیین کنید.",
                "fields": ("starts_at", "ends_at"),
            },
        ),
        ("وضعیت", {"fields": ("is_active", "order", "created_at", "updated_at")}),
    )

    @admin.display(description="پیش‌نمایش")
    def preview(self, obj: HeroSlide):
        if obj.image:
            return format_html(
                '<img src="{}" style="max-height:80px;border-radius:8px;">', obj.image.url
            )
        return "—"

    @admin.display(boolean=True, description="الان نمایش داده می‌شود؟")
    def visible_now(self, obj: HeroSlide) -> bool:
        return obj.is_visible_now


@admin.register(Feature)
class FeatureAdmin(ActiveOrderAdminMixin, admin.ModelAdmin):
    list_display = ("title", "icon", "is_active", "order")
    search_fields = ("title", "description")
    list_filter = ("is_active", "icon")


@admin.register(Testimonial)
class TestimonialAdmin(ActiveOrderAdminMixin, admin.ModelAdmin):
    list_display = ("full_name", "job_title", "is_active", "order")
    search_fields = ("full_name", "job_title", "quote")


@admin.register(Partner)
class PartnerAdmin(ActiveOrderAdminMixin, admin.ModelAdmin):
    list_display = ("name", "logo_preview", "website", "is_active", "order")
    search_fields = ("name",)
    readonly_fields = ("logo_preview",)

    @admin.display(description="لوگو")
    def logo_preview(self, obj: Partner):
        if obj.logo:
            return format_html('<img src="{}" style="max-height:40px;">', obj.logo.url)
        return "—"


@admin.register(FAQ)
class FAQAdmin(ActiveOrderAdminMixin, admin.ModelAdmin):
    list_display = ("question", "show_on_homepage", "is_active", "order")
    list_editable = ("show_on_homepage", "is_active", "order")
    search_fields = ("question", "answer")
    list_filter = ("is_active", "show_on_homepage")


@admin.register(ContactMessage)
class ContactMessageAdmin(admin.ModelAdmin):
    list_display = ("full_name", "subject", "mobile", "is_read", "created_at")
    list_filter = ("is_read", "created_at")
    search_fields = ("full_name", "mobile", "email", "subject", "message")
    date_hierarchy = "created_at"
    list_per_page = 30

    # پیام کاربر نباید توسط ادمین ویرایش شود؛ فقط خوانده و یادداشت‌گذاری می‌شود.
    readonly_fields = ("full_name", "mobile", "email", "subject", "message", "created_at")
    fieldsets = (
        ("پیام کاربر", {"fields": ("full_name", "mobile", "email", "subject", "message", "created_at")}),
        ("پیگیری", {"fields": ("is_read", "admin_note")}),
    )

    def has_add_permission(self, request) -> bool:
        # پیام فقط از فرم سایت ساخته می‌شود.
        return False

    @admin.action(description="علامت‌گذاری به عنوان خوانده‌شده")
    def mark_as_read(self, request, queryset):
        updated = queryset.update(is_read=True)
        self.message_user(request, f"{updated} پیام خوانده‌شده علامت خورد.")

    @admin.action(description="علامت‌گذاری به عنوان خوانده‌نشده")
    def mark_as_unread(self, request, queryset):
        updated = queryset.update(is_read=False)
        self.message_user(request, f"{updated} پیام خوانده‌نشده علامت خورد.")

    actions = ("mark_as_read", "mark_as_unread")


# --- شخصی‌سازی عنوان‌های پنل مدیریت ---
admin.site.site_header = "پنل مدیریت HSE Tech"
admin.site.site_title = "HSE Tech"
admin.site.index_title = "مدیریت سایت"
