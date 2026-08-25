"""
پنل مدیریت کاربران.

چون مدل کاربر را سفارشی کرده‌ایم، UserAdmin پیش‌فرض Django کار نمی‌کند
(دنبال فیلد username می‌گردد) و باید فیلدها را خودمان تعریف کنیم.
"""

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.forms import AdminPasswordChangeForm

from .models import InstructorProfile, User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    change_password_form = AdminPasswordChangeForm

    list_display = (
        "mobile",
        "full_name",
        "role",
        "is_mobile_verified",
        "is_identity_verified",
        "is_active",
        "created_at",
    )
    list_filter = (
        "role",
        "is_active",
        "is_staff",
        "is_mobile_verified",
        "is_identity_verified",
        "is_vip",
    )
    search_fields = ("mobile", "national_code", "first_name", "last_name", "email")
    ordering = ("-created_at",)
    date_hierarchy = "created_at"
    list_per_page = 30
    readonly_fields = ("created_at", "updated_at", "last_login")

    fieldsets = (
        ("اطلاعات ورود", {"fields": ("mobile", "password")}),
        ("اطلاعات شخصی", {"fields": ("first_name", "last_name", "email", "national_code")}),
        (
            "وضعیت احراز هویت",
            {"fields": ("is_mobile_verified", "is_identity_verified")},
        ),
        ("اشتراک ویژه", {"fields": ("is_vip", "vip_expires_at")}),
        (
            "دسترسی‌ها",
            {
                "fields": (
                    "role",
                    "is_active",
                    "is_staff",
                    "is_superuser",
                    "groups",
                    "user_permissions",
                ),
                "classes": ("collapse",),
            },
        ),
        ("تاریخ‌ها", {"fields": ("last_login", "created_at", "updated_at")}),
    )

    # فرم ساخت کاربر جدید از داخل پنل مدیریت
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("mobile", "first_name", "last_name", "password1", "password2"),
            },
        ),
    )

    @admin.display(description="نام کامل")
    def full_name(self, obj: User) -> str:
        return obj.full_name or "—"

    @admin.action(description="تأیید دستی موبایل کاربران انتخاب‌شده")
    def mark_mobile_verified(self, request, queryset):
        updated = queryset.update(is_mobile_verified=True)
        self.message_user(request, f"{updated} کاربر تأیید شد.")

    actions = ("mark_mobile_verified",)


@admin.register(InstructorProfile)
class InstructorProfileAdmin(admin.ModelAdmin):
    list_display = ("display_name", "specialty", "course_count", "show_on_homepage", "is_active", "order")
    list_editable = ("show_on_homepage", "is_active", "order")
    list_filter = ("is_active", "show_on_homepage")
    search_fields = ("display_name", "specialty", "bio")
    ordering = ("order", "display_name")
    readonly_fields = ("created_at", "updated_at")

    fieldsets = (
        ("اطلاعات مدرس", {"fields": ("display_name", "specialty", "bio", "avatar")}),
        ("حساب کاربری", {"fields": ("user", "linkedin_url")}),
        ("نمایش", {"fields": ("show_on_homepage", "is_active", "order")}),
        ("تاریخ‌ها", {"fields": ("created_at", "updated_at")}),
    )

    @admin.display(description="تعداد دوره")
    def course_count(self, obj: "InstructorProfile") -> int:
        return obj.published_course_count
