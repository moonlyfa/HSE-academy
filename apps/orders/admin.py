"""پنل مدیریت سفارش‌ها و کدهای تخفیف."""

from django.contrib import admin
from django.utils.html import format_html

from .models import Coupon, Order, OrderItem, OrderStatus, Payment, PaymentStatus


@admin.register(Coupon)
class CouponAdmin(admin.ModelAdmin):
    list_display = (
        "code",
        "discount_display",
        "used_count",
        "max_uses",
        "valid_until",
        "is_active",
    )
    list_editable = ("is_active",)
    list_filter = ("is_active", "discount_type")
    search_fields = ("code", "description")
    filter_horizontal = ("courses",)
    readonly_fields = ("used_count", "created_at")
    ordering = ("-created_at",)

    fieldsets = (
        ("کد", {"fields": ("code", "description", "is_active")}),
        (
            "مقدار تخفیف",
            {
                "description": "برای تخفیف درصدی، «مقدار» عددی بین ۱ تا ۱۰۰ است.",
                "fields": ("discount_type", "value", "max_discount_amount", "min_order_amount"),
            },
        ),
        ("محدودیت زمانی", {"fields": ("valid_from", "valid_until")}),
        ("محدودیت تعداد", {"fields": ("max_uses", "per_user_limit", "used_count")}),
        (
            "محدود به دوره‌های خاص",
            {
                "description": "اگر چیزی انتخاب نکنید، کد برای همه دوره‌ها معتبر است.",
                "fields": ("courses",),
                "classes": ("collapse",),
            },
        ),
        ("تاریخ‌ها", {"fields": ("created_at",), "classes": ("collapse",)}),
    )

    @admin.display(description="تخفیف")
    def discount_display(self, obj: Coupon) -> str:
        if obj.discount_type == "percent":
            return f"{obj.value}٪"
        return f"{obj.value:,} تومان"


class OrderItemInline(admin.TabularInline):
    """
    اقلام سفارش فقط‌خواندنی هستند.

    قیمت داخل سفارش عکس لحظه خرید است؛ اگر از پنل قابل ویرایش باشد،
    فاکتوری که کاربر پرداخت کرده با چیزی که ثبت شده جور درنمی‌آید.
    """

    model = OrderItem
    extra = 0
    can_delete = False
    fields = ("course", "title", "unit_price", "final_price", "quantity")
    readonly_fields = fields

    def has_add_permission(self, request, obj=None) -> bool:
        return False


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = (
        "order_number",
        "user",
        "item_count_display",
        "total_display",
        "status_badge",
        "created_at",
        "paid_at",
    )
    list_filter = ("status", "created_at", "paid_at")
    search_fields = (
        "order_number",
        "user__mobile",
        "user__first_name",
        "user__last_name",
        "items__title",
    )
    date_hierarchy = "created_at"
    ordering = ("-created_at",)
    inlines = (OrderItemInline,)
    list_per_page = 30

    readonly_fields = (
        "order_number",
        "user",
        "subtotal",
        "discount_amount",
        "total",
        "coupon",
        "coupon_code",
        "full_name",
        "mobile",
        "note",
        "created_at",
        "updated_at",
        "paid_at",
    )

    fieldsets = (
        ("سفارش", {"fields": ("order_number", "user", "status")}),
        ("مبالغ", {"fields": ("subtotal", "discount_amount", "total", "coupon", "coupon_code")}),
        ("خریدار", {"fields": ("full_name", "mobile", "note")}),
        ("یادداشت داخلی", {"fields": ("admin_note",)}),
        ("تاریخ‌ها", {"fields": ("created_at", "updated_at", "paid_at")}),
    )

    def has_add_permission(self, request) -> bool:
        # سفارش را کاربر از سایت ثبت می‌کند، نه ادمین از پنل.
        return False

    @admin.display(description="تعداد")
    def item_count_display(self, obj: Order) -> int:
        return obj.item_count

    @admin.display(description="مبلغ", ordering="total")
    def total_display(self, obj: Order) -> str:
        return f"{obj.total:,}"

    @admin.display(description="وضعیت", ordering="status")
    def status_badge(self, obj: Order):
        colors = {
            OrderStatus.PAID: "#1e8449",
            OrderStatus.PENDING: "#d99400",
            OrderStatus.FAILED: "#c0392b",
            OrderStatus.CANCELED: "#7f8c8d",
            OrderStatus.REFUNDED: "#1d5a7d",
        }
        return format_html(
            '<span style="color:{};font-weight:600">{}</span>',
            colors.get(obj.status, "#000"),
            obj.get_status_display(),
        )

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("user", "coupon")


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    """
    تراکنش‌های پرداخت — کاملاً فقط‌خواندنی.

    این جدول سند مالی است. اگر از پنل قابل ویرایش باشد، هنگام اختلاف با
    بانک یا کاربر، هیچ‌کس نمی‌تواند به آن استناد کند.
    """

    list_display = (
        "order",
        "gateway",
        "amount_display",
        "status_badge",
        "ref_id",
        "created_at",
        "verified_at",
    )
    list_filter = ("status", "gateway", "created_at")
    search_fields = ("order__order_number", "authority", "ref_id", "order__user__mobile")
    date_hierarchy = "created_at"
    ordering = ("-created_at",)
    list_per_page = 50

    def has_add_permission(self, request) -> bool:
        return False

    def has_change_permission(self, request, obj=None) -> bool:
        return False

    def has_delete_permission(self, request, obj=None) -> bool:
        return False

    def get_readonly_fields(self, request, obj=None):
        return [field.name for field in self.model._meta.fields]

    @admin.display(description="مبلغ", ordering="amount")
    def amount_display(self, obj: Payment) -> str:
        return f"{obj.amount:,}"

    @admin.display(description="وضعیت", ordering="status")
    def status_badge(self, obj: Payment):
        colors = {
            PaymentStatus.SUCCESS: "#1e8449",
            PaymentStatus.PENDING: "#d99400",
            PaymentStatus.FAILED: "#c0392b",
            PaymentStatus.CANCELED: "#7f8c8d",
        }
        return format_html(
            '<span style="color:{};font-weight:600">{}</span>',
            colors.get(obj.status, "#000"),
            obj.get_status_display(),
        )

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("order", "order__user")
