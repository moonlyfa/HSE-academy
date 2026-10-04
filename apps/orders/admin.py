"""پنل مدیریت سفارش‌ها و کدهای تخفیف."""

from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied
from django.db.models import Count
from django.http import HttpResponseRedirect
from django.urls import reverse
from django.utils.html import format_html, format_html_join

from apps.core.jalali import to_persian_digits

from .models import (
    CardTransfer,
    CardTransferStatus,
    Coupon,
    Order,
    OrderItem,
    OrderStatus,
    Payment,
    PaymentStatus,
)
from .services import approve_card_transfer, reject_card_transfer


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


@admin.register(CardTransfer)
class CardTransferAdmin(admin.ModelAdmin):
    """
    بررسی رسیدهای کارت به کارت.

    مدیر عکس رسید را می‌بیند، واریز را در حساب بانکی چک می‌کند و با یک
    دکمه تأیید یا رد می‌کند. هیچ فیلدی دستی قابل ویرایش نیست: تأیید باید
    از مسیر سرویس برود تا تراکنش ثبت، دوره باز و عکس پاک شود. اگر وضعیت
    دستی عوض می‌شد، هیچ‌کدام از این سه اتفاق نمی‌افتاد.
    """

    change_form_template = "admin/orders/cardtransfer/change_form.html"

    list_display = (
        "order",
        "buyer_display",
        "amount_display",
        "payer_card_last4",
        "receipt_count",
        "status_badge",
        "created_at",
        "reviewed_by",
    )
    list_display_links = ("order",)
    list_filter = ("status", "created_at")
    search_fields = (
        "order__order_number",
        "order__user__mobile",
        "order__mobile",
        "tracking_code",
        "payer_card_last4",
    )
    date_hierarchy = "created_at"
    ordering = ("-created_at",)
    list_per_page = 30

    fieldsets = (
        ("عکس رسید", {"fields": ("receipts_preview",)}),
        (
            "سفارش",
            {"fields": ("order_link", "buyer_info", "amount_display", "order_total", "courses_info")},
        ),
        (
            "اطلاعاتی که خریدار وارد کرده",
            {"fields": ("payer_card_last4", "tracking_code", "payer_note", "created_at")},
        ),
        (
            "بررسی",
            {
                "fields": (
                    "status",
                    "reviewed_by",
                    "reviewed_at",
                    "reject_reason",
                    "payment",
                    "receipts_deleted_at",
                )
            },
        ),
    )

    def get_readonly_fields(self, request, obj=None):
        return [
            "receipts_preview",
            "amount_display",
            "order_link",
            "buyer_info",
            "order_total",
            "courses_info",
            *(field.name for field in self.model._meta.fields),
        ]

    def has_add_permission(self, request) -> bool:
        # رسید را خریدار از سایت می‌فرستد.
        return False

    def has_delete_permission(self, request, obj=None) -> bool:
        # رد مالی است و باید بماند؛ عکس‌ها خودشان بعد از بررسی پاک می‌شوند.
        return False

    def save_model(self, request, obj, form, change) -> None:
        # ذخیره معمولی پنل چیزی را عوض نمی‌کند؛ تنها راه تغییر، دکمه‌های
        # تأیید و رد است.
        return None

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .select_related("order", "order__user", "reviewed_by")
            .annotate(_receipt_count=Count("receipts"))
        )

    # --- فهرست ---

    def changelist_view(self, request, extra_context=None):
        pending = CardTransfer.objects.filter(status=CardTransferStatus.SUBMITTED).count()
        title = self.model._meta.verbose_name_plural
        if pending:
            title = f"{title} — {to_persian_digits(pending)} رسید در انتظار بررسی"
        extra_context = {**(extra_context or {}), "title": title}
        return super().changelist_view(request, extra_context)

    @admin.display(description="خریدار")
    def buyer_display(self, obj: CardTransfer) -> str:
        order = obj.order
        return order.full_name or order.mobile or str(order.user)

    @admin.display(description="مبلغ رسید (تومان)", ordering="amount")
    def amount_display(self, obj: CardTransfer) -> str:
        return f"{obj.amount:,}"

    @admin.display(description="عکس")
    def receipt_count(self, obj: CardTransfer) -> str:
        if obj.receipts_deleted_at:
            return "پاک شده"
        return to_persian_digits(getattr(obj, "_receipt_count", 0))

    @admin.display(description="وضعیت", ordering="status")
    def status_badge(self, obj: CardTransfer):
        colors = {
            CardTransferStatus.SUBMITTED: "#d99400",
            CardTransferStatus.APPROVED: "#1e8449",
            CardTransferStatus.REJECTED: "#c0392b",
        }
        return format_html(
            '<span style="color:{};font-weight:600">{}</span>',
            colors.get(obj.status, "#000"),
            obj.get_status_display(),
        )

    # --- صفحه بررسی ---

    @admin.display(description="عکس‌ها")
    def receipts_preview(self, obj: CardTransfer):
        receipts = list(obj.receipts.all())
        if not receipts:
            if obj.receipts_deleted_at:
                return "عکس رسید پس از بررسی از سرور پاک شده است."
            return "عکسی ثبت نشده است."
        return format_html_join(
            "",
            '<a href="{0}" target="_blank" rel="noopener" '
            'style="display:inline-block;margin:0 0 12px 12px">'
            '<img src="{0}" alt="رسید" '
            'style="max-width:min(100%,520px);max-height:75vh;border:1px solid #ccc;'
            'border-radius:6px"></a>',
            ((receipt.image.url,) for receipt in receipts),
        )

    @admin.display(description="سفارش")
    def order_link(self, obj: CardTransfer):
        url = reverse("admin:orders_order_change", args=[obj.order_id])
        return format_html(
            '<a href="{}">{}</a> — {}',
            url,
            obj.order.order_number,
            obj.order.get_status_display(),
        )

    @admin.display(description="خریدار")
    def buyer_info(self, obj: CardTransfer):
        order = obj.order
        return format_html(
            '{} — <span dir="ltr">{}</span>',
            order.full_name or str(order.user),
            order.mobile or getattr(order.user, "mobile", ""),
        )

    @admin.display(description="مبلغ فعلی سفارش (تومان)")
    def order_total(self, obj: CardTransfer):
        if obj.order.total != obj.amount:
            return format_html(
                '<strong style="color:#c0392b">{:,} — با مبلغ رسید یکی نیست</strong>',
                obj.order.total,
            )
        return f"{obj.order.total:,}"

    @admin.display(description="دوره‌ها و ظرفیت")
    def courses_info(self, obj: CardTransfer):
        from apps.courses.capacity import seats_left

        rows = []
        for item in obj.order.items.select_related("course"):
            left = seats_left(item.course)
            seats = "بدون محدودیت" if left is None else f"{to_persian_digits(left)} صندلی خالی"
            rows.append((item.title, seats))
        return format_html_join(
            "", '<div>{} <span style="color:#666">({})</span></div>', rows
        )

    def change_view(self, request, object_id, form_url="", extra_context=None):
        if request.method == "POST" and (
            "_approve_transfer" in request.POST or "_reject_transfer" in request.POST
        ):
            return self._review(request, object_id)

        obj = self.get_object(request, object_id)
        extra_context = {
            **(extra_context or {}),
            "title": "بررسی رسید کارت به کارت",
            "can_review": bool(
                obj and obj.is_pending and self.has_change_permission(request, obj)
            ),
        }
        return super().change_view(request, object_id, form_url, extra_context)

    def _review(self, request, object_id):
        transfer = self.get_object(request, object_id)
        if transfer is None:
            return HttpResponseRedirect(reverse("admin:orders_cardtransfer_changelist"))
        if not self.has_change_permission(request, transfer):
            raise PermissionDenied

        if "_approve_transfer" in request.POST:
            result = approve_card_transfer(transfer, request.user)
        else:
            result = reject_card_transfer(
                transfer, request.user, request.POST.get("reject_reason", "")
            )

        if not result.success:
            messages.error(request, result.message)
            return HttpResponseRedirect(request.path)

        messages.success(request, result.message)
        return HttpResponseRedirect(reverse("admin:orders_cardtransfer_changelist"))
