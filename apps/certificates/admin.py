"""
پنل مدیریت گواهی‌ها.

گواهی سندی است که بیرون از سایت هم اعتبار دارد، پس اطلاعاتش در پنل
**فقط خواندنی** است. تنها کاری که مدیر می‌تواند بکند ابطال است — و آن هم
با ثبت علت، چون صفحه استعلام باید بتواند بگوید چرا این گواهی دیگر معتبر
نیست.
"""

from django.contrib import admin
from django.utils.html import format_html

from .issue import revoke_certificate
from .models import Certificate, CertificateStatus


@admin.register(Certificate)
class CertificateAdmin(admin.ModelAdmin):
    list_display = (
        "certificate_code",
        "holder_name",
        "course_title",
        "score_display",
        "issued_at",
        "status_badge",
    )
    list_filter = ("status", "issued_at", "course")
    search_fields = (
        "certificate_code",
        "holder_name",
        "course_title",
        "user__mobile",
    )
    date_hierarchy = "issued_at"
    ordering = ("-issued_at",)
    list_per_page = 50

    readonly_fields = (
        "certificate_code",
        "verification_token",
        "user",
        "course",
        "enrollment",
        "exam_attempt",
        "holder_name",
        "course_title",
        "course_hours",
        "instructor_name",
        "score",
        "issued_at",
        "created_at",
        "updated_at",
        "verification_link",
    )

    fieldsets = (
        (
            "گواهی",
            {
                "description": (
                    "این اطلاعات در لحظه صدور عکس‌برداری شده‌اند و تغییر نمی‌کنند؛ "
                    "گواهیِ چاپ‌شده در دست کارفرما باید با همین‌ها بخواند."
                ),
                "fields": (
                    "certificate_code",
                    "holder_name",
                    "course_title",
                    "course_hours",
                    "instructor_name",
                    "score",
                    "issued_at",
                ),
            },
        ),
        ("اعتبار", {"fields": ("valid_until", "status", "revoke_reason")}),
        (
            "استعلام",
            {
                "description": "آدرس داخل QR روی توکن ساخته می‌شود، نه روی کد گواهی.",
                "fields": ("verification_token", "verification_link"),
            },
        ),
        (
            "ارجاع‌ها",
            {
                "fields": ("user", "course", "enrollment", "exam_attempt"),
                "classes": ("collapse",),
            },
        ),
        ("تاریخ‌ها", {"fields": ("created_at", "updated_at"), "classes": ("collapse",)}),
    )

    def has_add_permission(self, request):
        """
        گواهی از پنل ساخته نمی‌شود.

        صدور دستی یعنی دور زدن همان شرط‌هایی (تکمیل دوره، قبولی آزمون،
        احراز هویت) که گواهی را معتبر می‌کنند.
        """
        return False

    @admin.display(description="نمره", ordering="score")
    def score_display(self, obj: Certificate) -> str:
        return f"{obj.score}٪" if obj.score is not None else "—"

    @admin.display(description="وضعیت", ordering="status")
    def status_badge(self, obj: Certificate):
        colors = {"معتبر": "#1e8449", "منقضی‌شده": "#d99400", "باطل‌شده": "#c0392b"}
        label = obj.status_label
        return format_html(
            '<span style="color:{};font-weight:600">{}</span>',
            colors.get(label, "#000"),
            label,
        )

    @admin.display(description="لینک استعلام")
    def verification_link(self, obj: Certificate):
        if not obj.pk:
            return "—"
        url = obj.get_verification_url()
        return format_html('<a href="{}" target="_blank">{}</a>', url, url)

    @admin.action(description="ابطال گواهی‌های انتخاب‌شده")
    def revoke_selected(self, request, queryset):
        count = 0
        for certificate in queryset.exclude(status=CertificateStatus.REVOKED):
            revoke_certificate(certificate, reason="ابطال از پنل مدیریت")
            count += 1
        self.message_user(request, f"{count} گواهی باطل شد.")

    actions = ("revoke_selected",)

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("user", "course")
