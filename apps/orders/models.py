"""
مدل‌های سفارش، آیتم سفارش و کد تخفیف.

قاعده اصلی این فایل: **همه مبالغ در لحظه ثبت سفارش عکس‌برداری می‌شوند.**

چرا؟ فرض کنید کاربر امروز دوره‌ای را ۳٬۹۰۰٬۰۰۰ تومان می‌خرد و ماه بعد
قیمت دوره ۵٬۵۰۰٬۰۰۰ می‌شود. اگر فاکتور قیمت را از روی خودِ دوره بخواند،
فاکتور قدیمی هم عوض می‌شود و کاربر رسیدی می‌بیند که با پولی که پرداخت
کرده جور نیست. برای همین قیمت، عنوان و مبلغ تخفیف داخل خود سفارش ذخیره
می‌شوند و دیگر هیچ‌وقت تغییر نمی‌کنند.
"""

from __future__ import annotations

import secrets
from datetime import timedelta

from django.db import models
from django.db.models.signals import post_delete
from django.dispatch import receiver
from django.urls import reverse
from django.utils import timezone

from apps.courses.storages import protected_storage

# حروف و ارقامی که در شماره سفارش استفاده می‌شوند.
# حروف مبهم (I، O، ۰، ۱) عمداً حذف شده‌اند تا وقتی کاربر شماره سفارش را
# تلفنی به پشتیبانی می‌گوید، اشتباه خوانده نشود.
ORDER_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
ORDER_CODE_LENGTH = 6


def generate_order_number() -> str:
    """
    ساخت شماره سفارش خوانا و غیرقابل حدس.

    چرا شماره ترتیبی (۱، ۲، ۳ …) نمی‌سازیم؟
    دو دلیل: اول اینکه از روی شماره سفارش خودتان، رقیب می‌فهمد ماهانه چند
    فروش دارید. دوم اینکه کاربر می‌تواند شماره را یکی‌یکی کم و زیاد کند و
    آدرس سفارش دیگران را امتحان کند. (دسترسی در View هم بررسی می‌شود؛
    این فقط لایه دوم است.)
    """
    today = timezone.now()
    suffix = "".join(secrets.choice(ORDER_CODE_ALPHABET) for _ in range(ORDER_CODE_LENGTH))
    return f"HSE-{today:%y%m}-{suffix}"


class DiscountType(models.TextChoices):
    PERCENT = "percent", "درصدی"
    FIXED = "fixed", "مبلغ ثابت"


class Coupon(models.Model):
    """کد تخفیف."""

    code = models.CharField(
        "کد تخفیف",
        max_length=40,
        unique=True,
        help_text="کاربر همین عبارت را وارد می‌کند. بزرگی و کوچکی حروف مهم نیست.",
    )
    description = models.CharField("توضیح داخلی", max_length=200, blank=True)

    discount_type = models.CharField(
        "نوع تخفیف",
        max_length=10,
        choices=DiscountType.choices,
        default=DiscountType.PERCENT,
    )
    value = models.PositiveIntegerField(
        "مقدار",
        help_text="برای تخفیف درصدی عددی بین ۱ تا ۱۰۰، و برای مبلغ ثابت، مبلغ به تومان.",
    )
    max_discount_amount = models.PositiveIntegerField(
        "سقف تخفیف (تومان)",
        null=True,
        blank=True,
        help_text="فقط برای تخفیف درصدی. خالی یعنی بدون سقف.",
    )
    min_order_amount = models.PositiveIntegerField(
        "حداقل مبلغ سفارش (تومان)",
        default=0,
        help_text="اگر جمع سبد کمتر از این مبلغ باشد، کد اعمال نمی‌شود.",
    )

    valid_from = models.DateTimeField("معتبر از", null=True, blank=True)
    valid_until = models.DateTimeField("معتبر تا", null=True, blank=True)

    max_uses = models.PositiveIntegerField(
        "حداکثر تعداد استفاده",
        null=True,
        blank=True,
        help_text="خالی یعنی نامحدود.",
    )
    used_count = models.PositiveIntegerField("تعداد استفاده‌شده", default=0)
    per_user_limit = models.PositiveIntegerField(
        "حداکثر استفاده هر کاربر",
        default=1,
        help_text="صفر یعنی نامحدود.",
    )

    courses = models.ManyToManyField(
        "courses.Course",
        verbose_name="محدود به دوره‌های",
        blank=True,
        related_name="coupons",
        help_text="خالی بگذارید تا برای همه دوره‌ها معتبر باشد.",
    )

    is_active = models.BooleanField("فعال", default=True)
    created_at = models.DateTimeField("تاریخ ایجاد", auto_now_add=True)

    class Meta:
        verbose_name = "کد تخفیف"
        verbose_name_plural = "کدهای تخفیف"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return self.code

    def save(self, *args, **kwargs):
        # کد همیشه با حروف بزرگ ذخیره می‌شود تا مقایسه ساده و بدون ابهام باشد.
        self.code = self.code.strip().upper()
        super().save(*args, **kwargs)

    @property
    def is_expired(self) -> bool:
        now = timezone.now()
        if self.valid_from and now < self.valid_from:
            return True
        return bool(self.valid_until and now > self.valid_until)

    @property
    def is_exhausted(self) -> bool:
        return self.max_uses is not None and self.used_count >= self.max_uses

    def discount_for(self, amount: int) -> int:
        """
        مبلغ تخفیف روی یک مبلغ مشخص.

        خروجی هرگز از خود مبلغ بیشتر نمی‌شود؛ وگرنه جمع فاکتور منفی می‌شد.
        """
        if self.discount_type == DiscountType.PERCENT:
            discount = amount * self.value // 100
            if self.max_discount_amount is not None:
                discount = min(discount, self.max_discount_amount)
        else:
            discount = self.value

        return min(discount, amount)


class OrderStatus(models.TextChoices):
    """
    وضعیت سفارش.

    تنها وضعیتی که دسترسی به دوره می‌دهد PAID است، و تنها راه رسیدن به آن
    تأیید سمت سرور از سوی درگاه پرداخت است (فاز ۱۲ و ۱۳).
    """

    PENDING = "pending", "در انتظار پرداخت"
    PAID = "paid", "پرداخت شده"
    FAILED = "failed", "پرداخت ناموفق"
    CANCELED = "canceled", "لغو شده"
    REFUNDED = "refunded", "بازگشت وجه"


class Order(models.Model):
    """یک سفارش — سبد خریدی که کاربر آن را نهایی کرده است."""

    order_number = models.CharField(
        "شماره سفارش",
        max_length=20,
        unique=True,
        default=generate_order_number,
        editable=False,
    )
    user = models.ForeignKey(
        "accounts.User",
        verbose_name="کاربر",
        on_delete=models.PROTECT,
        related_name="orders",
    )
    status = models.CharField(
        "وضعیت",
        max_length=20,
        choices=OrderStatus.choices,
        default=OrderStatus.PENDING,
    )

    # --- مبالغ، همه به تومان و همه عکس لحظه ثبت سفارش ---
    subtotal = models.PositiveIntegerField("جمع اقلام", default=0)
    discount_amount = models.PositiveIntegerField("مبلغ تخفیف", default=0)
    total = models.PositiveIntegerField("مبلغ قابل پرداخت", default=0)

    coupon = models.ForeignKey(
        Coupon,
        verbose_name="کد تخفیف",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="orders",
    )
    coupon_code = models.CharField(
        "کد تخفیف واردشده",
        max_length=40,
        blank=True,
        help_text="عکس متن کد در لحظه ثبت سفارش؛ حتی اگر بعداً کد حذف شود باقی می‌ماند.",
    )

    # --- اطلاعات تماس در لحظه خرید (کاربر ممکن است بعداً پروفایلش را عوض کند) ---
    full_name = models.CharField("نام خریدار", max_length=150, blank=True)
    mobile = models.CharField("شماره تماس", max_length=20, blank=True)

    note = models.TextField("یادداشت خریدار", blank=True)
    admin_note = models.TextField("یادداشت داخلی", blank=True)

    created_at = models.DateTimeField("تاریخ ثبت", auto_now_add=True)
    updated_at = models.DateTimeField("آخرین تغییر", auto_now=True)
    paid_at = models.DateTimeField("زمان پرداخت", null=True, blank=True)

    class Meta:
        verbose_name = "سفارش"
        verbose_name_plural = "سفارش‌ها"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "-created_at"]),
            models.Index(fields=["status"]),
        ]

    def __str__(self) -> str:
        return self.order_number

    def get_absolute_url(self) -> str:
        return reverse("orders:detail", kwargs={"order_number": self.order_number})

    @property
    def is_paid(self) -> bool:
        return self.status == OrderStatus.PAID

    @property
    def is_payable(self) -> bool:
        """
        آیا هنوز می‌شود این سفارش را پرداخت کرد؟

        سفارش پرداخت‌شده دوباره پرداخت نمی‌شود و سفارش لغوشده هم نه.
        سفارش ناموفق قابل تلاش دوباره است.
        """
        return self.status in (OrderStatus.PENDING, OrderStatus.FAILED)

    @property
    def item_count(self) -> int:
        return self.items.count()

    def recalculate(self, *, save: bool = True) -> None:
        """
        محاسبه دوباره مبالغ از روی آیتم‌های ذخیره‌شده.

        هیچ‌وقت مبلغ را از سمت مرورگر نمی‌گیریم؛ همیشه از روی داده‌ای که
        خودمان در دیتابیس نوشته‌ایم دوباره حساب می‌شود.
        """
        self.subtotal = sum(item.line_total for item in self.items.all())

        if self.coupon:
            self.discount_amount = self.coupon.discount_for(self.subtotal)
        else:
            self.discount_amount = 0

        self.total = max(self.subtotal - self.discount_amount, 0)

        if save:
            self.save(update_fields=["subtotal", "discount_amount", "total", "updated_at"])

    def mark_paid(self) -> None:
        """
        سفارش را پرداخت‌شده علامت می‌زند.

        این متد عمداً کاری جز تغییر وضعیت انجام نمی‌دهد و هیچ Viewی مستقیماً
        صدایش نمی‌زند؛ فقط لایه پرداخت (فاز ۱۲ و ۱۳) بعد از تأیید سمت سرورِ
        درگاه آن را فراخوانی می‌کند. باز کردن دسترسی دوره از روی پارامتر
        آدرس بازگشتی درگاه، رایج‌ترین راه کلاهبرداری در سایت‌های فروش است.
        """
        if self.is_paid:
            return

        self.status = OrderStatus.PAID
        self.paid_at = timezone.now()
        self.save(update_fields=["status", "paid_at", "updated_at"])


class OrderItem(models.Model):
    """
    یک ردیف از سفارش — یعنی یک دوره.

    عنوان و قیمت اینجا دوباره ذخیره می‌شوند (نه فقط ارجاع به دوره) تا
    فاکتور کاربر با گذشت زمان و تغییر قیمت‌ها دست‌نخورده بماند.
    """

    order = models.ForeignKey(
        Order,
        verbose_name="سفارش",
        on_delete=models.CASCADE,
        related_name="items",
    )
    course = models.ForeignKey(
        "courses.Course",
        verbose_name="دوره",
        # PROTECT یعنی دوره‌ای که فروخته شده را نمی‌شود حذف کرد؛ حذفش
        # فاکتورهای پرداخت‌شده را بی‌معنا می‌کرد.
        on_delete=models.PROTECT,
        related_name="order_items",
    )

    title = models.CharField("عنوان دوره (در لحظه خرید)", max_length=200)
    unit_price = models.PositiveIntegerField("قیمت اصلی")
    final_price = models.PositiveIntegerField("قیمت پرداختی")
    quantity = models.PositiveSmallIntegerField("تعداد", default=1)

    class Meta:
        verbose_name = "قلم سفارش"
        verbose_name_plural = "اقلام سفارش"
        constraints = [
            # یک دوره در یک سفارش فقط یک‌بار می‌آید؛ دوره آموزشی مثل کالا
            # نیست که دو تا از آن بخرید.
            models.UniqueConstraint(
                fields=["order", "course"], name="unique_course_per_order"
            )
        ]

    def __str__(self) -> str:
        return self.title

    @property
    def line_total(self) -> int:
        return self.final_price * self.quantity

    @property
    def has_discount(self) -> bool:
        return self.final_price < self.unit_price


class PaymentStatus(models.TextChoices):
    """
    وضعیت یک تراکنش پرداخت.

    توجه: وضعیت تراکنش با وضعیت سفارش یکی نیست. یک سفارش می‌تواند چند
    تراکنش داشته باشد (کاربر یک‌بار ناموفق باشد و دوباره تلاش کند)، اما
    فقط یکی از آن‌ها موفق می‌شود.
    """

    PENDING = "pending", "در انتظار پرداخت"
    SUCCESS = "success", "موفق"
    FAILED = "failed", "ناموفق"
    CANCELED = "canceled", "انصراف کاربر"


class Payment(models.Model):
    """
    یک تلاش پرداخت.

    چرا جدا از سفارش؟
    چون پرداخت ممکن است چند بار تکرار شود: کارت کاربر موجودی ندارد، از
    درگاه برمی‌گردد، دوباره تلاش می‌کند. اگر همه اطلاعات پرداخت روی خود
    سفارش بود، هر تلاش تازه، رد تلاش قبلی را پاک می‌کرد و دیگر نمی‌شد
    فهمید چه اتفاقی افتاده — همان چیزی که هنگام اختلاف مالی لازم است.
    """

    order = models.ForeignKey(
        Order,
        verbose_name="سفارش",
        on_delete=models.PROTECT,
        related_name="payments",
    )
    gateway = models.CharField("درگاه", max_length=30, default="mock")

    # مبلغ اینجا هم ذخیره می‌شود تا هنگام تأیید بشود بررسی کرد که مبلغ
    # اعلامی درگاه دقیقاً با همان مبلغی که فرستادیم یکی است.
    amount = models.PositiveIntegerField("مبلغ (تومان)")

    status = models.CharField(
        "وضعیت",
        max_length=20,
        choices=PaymentStatus.choices,
        default=PaymentStatus.PENDING,
    )

    # --- شناسه‌های درگاه ---
    authority = models.CharField(
        "شناسه تراکنش درگاه",
        max_length=100,
        blank=True,
        db_index=True,
        help_text="کدی که درگاه هنگام شروع پرداخت می‌دهد و در بازگشت با آن شناسایی می‌شود.",
    )
    ref_id = models.CharField(
        "شماره پیگیری بانک",
        max_length=100,
        blank=True,
        help_text="فقط بعد از تأیید موفق پرداخت پر می‌شود.",
    )
    card_pan = models.CharField(
        "چهار رقم آخر کارت",
        max_length=20,
        blank=True,
        help_text="هرگز شماره کامل کارت ذخیره نمی‌شود.",
    )

    error_code = models.CharField("کد خطا", max_length=50, blank=True)
    error_message = models.CharField("پیام خطا", max_length=300, blank=True)

    # پاسخ خام درگاه برای پیگیری اختلاف‌های مالی نگه داشته می‌شود.
    raw_response = models.JSONField("پاسخ درگاه", default=dict, blank=True)

    created_at = models.DateTimeField("زمان شروع", auto_now_add=True)
    updated_at = models.DateTimeField("آخرین تغییر", auto_now=True)
    verified_at = models.DateTimeField("زمان تأیید", null=True, blank=True)

    class Meta:
        verbose_name = "تراکنش پرداخت"
        verbose_name_plural = "تراکنش‌های پرداخت"
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["order", "-created_at"])]

    def __str__(self) -> str:
        return f"{self.order.order_number} — {self.get_status_display()}"

    @property
    def is_successful(self) -> bool:
        return self.status == PaymentStatus.SUCCESS

    @property
    def is_pending(self) -> bool:
        return self.status == PaymentStatus.PENDING

    def is_expired(self, minutes: int | None = None) -> bool:
        """
        آیا مهلت این تراکنش تمام شده است؟

        کاربری که صفحه درگاه را باز گذاشته و یک ساعت بعد برگشته، نباید
        تراکنشی را تأیید کند که سفارشش شاید در این فاصله لغو شده باشد.
        """
        from django.conf import settings

        limit = minutes if minutes is not None else settings.PAYMENT_EXPIRY_MINUTES
        return timezone.now() > self.created_at + timedelta(minutes=limit)

    @property
    def masked_card(self) -> str:
        """نمایش امن شماره کارت — فقط چهار رقم آخر."""
        if not self.card_pan:
            return ""
        return f"**** **** **** {self.card_pan[-4:]}"


# ---------------------------------------------------------------------------
# پرداخت کارت به کارت
# ---------------------------------------------------------------------------


class CardTransferStatus(models.TextChoices):
    SUBMITTED = "submitted", "در انتظار بررسی"
    APPROVED = "approved", "تأیید شده"
    REJECTED = "rejected", "رد شده"


def card_receipt_path(instance, filename: str) -> str:
    """
    نام فایل رسید تصادفی است، نه نام فایلی که کاربر فرستاده.

    نام اصلی ممکن است اطلاعات شخصی داشته باشد (مثلاً «رسید-علی-رضایی.jpg»)
    و قابل حدس هم هست.
    """
    return f"card-receipts/{secrets.token_hex(16)}.jpg"


class CardTransfer(models.Model):
    """
    یک پرداخت کارت به کارت که خریدار رسیدش را فرستاده است.

    چرخه:
        خریدار مبلغ را واریز می‌کند و عکس رسید را می‌فرستد (SUBMITTED)
        ← مدیر عکس را می‌بیند و تأیید یا رد می‌کند
        ← با تأیید، یک Payment موفق ثبت و دوره‌ها باز می‌شوند
        ← در هر دو حالت، عکس رسید همان لحظه از سرور پاک می‌شود.

    چرا عکس پاک می‌شود ولی این ردیف نه؟ عکس فقط برای همان یک بار دیدن لازم
    است و نگه داشتنش فضای سرور را پر می‌کند. اما رد مالی (مبلغ، چهار رقم
    آخر کارت پرداخت‌کننده، شماره پیگیری، چه کسی و کِی تأیید کرد) باید
    بماند تا اگر روزی اختلافی پیش آمد، بشود پیگیری کرد.
    """

    order = models.ForeignKey(
        Order,
        verbose_name="سفارش",
        on_delete=models.PROTECT,
        related_name="card_transfers",
    )
    amount = models.PositiveIntegerField(
        "مبلغ سفارش در لحظه ارسال رسید (تومان)",
        help_text="اگر مبلغ سفارش بعداً عوض شود، تأیید انجام نمی‌شود.",
    )
    status = models.CharField(
        "وضعیت",
        max_length=20,
        choices=CardTransferStatus.choices,
        default=CardTransferStatus.SUBMITTED,
        db_index=True,
    )

    # --- اطلاعاتی که خریدار وارد می‌کند ---
    payer_card_last4 = models.CharField("چهار رقم آخر کارت پرداخت‌کننده", max_length=4)
    tracking_code = models.CharField("شماره پیگیری / مرجع", max_length=40, blank=True)
    payer_note = models.CharField("توضیح خریدار", max_length=300, blank=True)

    # --- بررسی مدیر ---
    reviewed_by = models.ForeignKey(
        "accounts.User",
        verbose_name="بررسی‌کننده",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    reviewed_at = models.DateTimeField("زمان بررسی", null=True, blank=True)
    reject_reason = models.CharField(
        "دلیل رد",
        max_length=300,
        blank=True,
        help_text="برای خریدار نمایش داده و پیامک می‌شود.",
    )
    payment = models.OneToOneField(
        Payment,
        verbose_name="تراکنش ثبت‌شده",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="card_transfer",
    )
    receipts_deleted_at = models.DateTimeField(
        "زمان پاک شدن عکس رسید", null=True, blank=True
    )

    created_at = models.DateTimeField("زمان ارسال رسید", auto_now_add=True)
    updated_at = models.DateTimeField("آخرین تغییر", auto_now=True)

    class Meta:
        verbose_name = "پرداخت کارت به کارت"
        verbose_name_plural = "پرداخت‌های کارت به کارت"
        ordering = ["-created_at"]
        constraints = [
            # هر سفارش در هر لحظه فقط یک رسید در انتظار بررسی دارد؛ وگرنه
            # ممکن بود دو رسید یک واریز، دو بار تأیید شوند.
            models.UniqueConstraint(
                fields=["order"],
                condition=models.Q(status="submitted"),
                name="one_pending_card_transfer_per_order",
            )
        ]

    def __str__(self) -> str:
        return f"{self.order.order_number} — {self.get_status_display()}"

    @property
    def is_pending(self) -> bool:
        return self.status == CardTransferStatus.SUBMITTED

    def delete_receipt_files(self) -> int:
        """
        عکس‌های رسید را از دیسک و دیتابیس پاک می‌کند.

        فایلی که قبلاً دستی پاک شده خطا نمی‌دهد (FileSystemStorage آن را
        نادیده می‌گیرد). خروجی: تعداد رسیدهای پاک‌شده.
        """
        deleted = 0
        for receipt in self.receipts.all():
            receipt.delete()  # فایل را سیگنال post_delete پاک می‌کند
            deleted += 1

        if self.receipts_deleted_at is None:
            self.receipts_deleted_at = timezone.now()
            self.save(update_fields=["receipts_deleted_at", "updated_at"])
        return deleted


class CardTransferReceipt(models.Model):
    """
    عکس رسید. موقت است: بعد از بررسی مدیر، فایل و همین ردیف پاک می‌شوند.

    کاربر می‌تواند تا سه عکس بفرستد؛ مبلغ بیشتر از سقف روزانه کارت به
    کارت معمولاً در چند واریز جدا پرداخت می‌شود.
    """

    transfer = models.ForeignKey(
        CardTransfer,
        verbose_name="پرداخت",
        on_delete=models.CASCADE,
        related_name="receipts",
    )
    # فایل بیرون از پوشه عمومی ذخیره می‌شود و فقط مدیر از راه نمای
    # مخصوص می‌تواند آن را ببیند.
    image = models.FileField(
        "عکس رسید",
        storage=protected_storage,
        upload_to=card_receipt_path,
    )
    size_bytes = models.PositiveIntegerField("حجم پس از فشرده‌سازی (بایت)", default=0)
    created_at = models.DateTimeField("زمان ارسال", auto_now_add=True)

    class Meta:
        verbose_name = "عکس رسید"
        verbose_name_plural = "عکس‌های رسید"
        ordering = ["pk"]

    def __str__(self) -> str:
        return f"رسید {self.pk}"


@receiver(post_delete, sender=CardTransferReceipt)
def _delete_receipt_file(sender, instance: CardTransferReceipt, **kwargs) -> None:
    """
    پاک شدن ردیف رسید، از هر راهی (مثلاً حذف آبشاری)، فایلش را هم پاک کند.

    جنگو فایل FileField را با حذف ردیف پاک نمی‌کند؛ بدون این، فایل یتیم
    روی دیسک می‌ماند — همان چیزی که این قابلیت قرار است جلویش را بگیرد.
    """
    if instance.image:
        instance.image.storage.delete(instance.image.name)
