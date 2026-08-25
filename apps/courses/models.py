"""
مدل‌های دسته‌بندی و دوره.

این مدل‌ها قلب سایت هستند: صفحه اصلی، صفحه دوره‌ها، تقویم آموزشی و بعداً
سبد خرید و گواهی همگی از همین‌ها می‌خوانند.
"""

from django.db import models
from django.urls import reverse
from django.utils import timezone


class CourseType(models.TextChoices):
    """شیوه برگزاری دوره."""

    ONLINE_LIVE = "online_live", "آنلاین زنده"
    OFFLINE_RECORDED = "offline_recorded", "آفلاین (ضبط‌شده)"
    HYBRID = "hybrid", "ترکیبی"


class CourseLevel(models.TextChoices):
    """سطح دوره."""

    BEGINNER = "beginner", "مقدماتی"
    INTERMEDIATE = "intermediate", "متوسط"
    ADVANCED = "advanced", "پیشرفته"


class CourseCategory(models.Model):
    """
    دسته‌بندی دوره — مثل «ایمنی صنعتی» یا «ارزیابی ریسک».

    parent اجازه می‌دهد بعداً زیردسته بسازیم بدون تغییر ساختار دیتابیس.
    """

    ICON_CHOICES = [
        ("shield", "سپر ایمنی"),
        ("chart", "ارزیابی و تحلیل"),
        ("users", "منابع انسانی"),
        ("certificate", "استاندارد و گواهی"),
        ("video", "آموزش آنلاین"),
        ("book", "آموزش عمومی"),
        ("lock", "کنترل و بازرسی"),
        ("headset", "پشتیبانی و مدیریت"),
    ]

    name = models.CharField("نام دسته‌بندی", max_length=100)
    slug = models.SlugField(
        "نشانی یکتا (اسلاگ)",
        max_length=120,
        unique=True,
        allow_unicode=True,
        help_text="در آدرس صفحه استفاده می‌شود. مثال: risk-assessment",
    )
    description = models.TextField("توضیح کوتاه", blank=True)
    icon = models.CharField("آیکون", max_length=20, choices=ICON_CHOICES, default="shield")
    image = models.ImageField("تصویر", upload_to="categories/", blank=True, null=True)

    parent = models.ForeignKey(
        "self",
        verbose_name="دسته‌بندی والد",
        on_delete=models.CASCADE,
        related_name="children",
        null=True,
        blank=True,
        help_text="برای ساخت زیردسته. برای دسته اصلی خالی بگذارید.",
    )

    is_active = models.BooleanField("فعال", default=True)
    show_on_homepage = models.BooleanField(
        "نمایش در صفحه اصلی",
        default=True,
        help_text="فقط چند دسته منتخب در صفحه اصلی نمایش داده می‌شوند.",
    )
    order = models.PositiveIntegerField("ترتیب نمایش", default=0)

    meta_title = models.CharField("عنوان سئو", max_length=70, blank=True)
    meta_description = models.CharField("توضیحات سئو", max_length=160, blank=True)

    created_at = models.DateTimeField("تاریخ ایجاد", auto_now_add=True)
    updated_at = models.DateTimeField("آخرین بروزرسانی", auto_now=True)

    class Meta:
        verbose_name = "دسته‌بندی دوره"
        verbose_name_plural = "دسته‌بندی دوره‌ها"
        ordering = ["order", "name"]

    def __str__(self) -> str:
        return self.name

    def get_absolute_url(self) -> str:
        """
        دسته‌بندی، کاربر را به صفحه دوره‌ها با فیلترِ همان دسته می‌برد.

        این‌طوری فقط یک صفحه لیست دوره داریم (نه دو صفحه موازی) و کاربر
        می‌تواند از همان‌جا فیلترها را تغییر دهد.
        """
        return f"{reverse('courses:list')}?category={self.slug}"

    @property
    def published_course_count(self) -> int:
        return self.courses.filter(is_published=True).count()


class PublishedCourseQuerySet(models.QuerySet):
    def published(self):
        return self.filter(is_published=True)

    def featured(self):
        return self.published().filter(is_featured=True)

    def upcoming(self):
        """دوره‌هایی که تاریخ شروعشان هنوز نرسیده — برای تقویم آموزشی."""
        return self.published().filter(start_date__gte=timezone.now().date())


class Course(models.Model):
    """یک دوره آموزشی."""

    # --- شناسه و متن ---
    title = models.CharField("عنوان دوره", max_length=200)
    slug = models.SlugField(
        "نشانی یکتا (اسلاگ)",
        max_length=220,
        unique=True,
        allow_unicode=True,
        help_text="در آدرس دوره استفاده می‌شود. مثال: hse-officer",
    )
    short_description = models.TextField(
        "توضیح کوتاه",
        max_length=300,
        blank=True,
        help_text="روی کارت دوره نمایش داده می‌شود.",
    )
    full_description = models.TextField("توضیح کامل", blank=True)

    # --- ارتباط‌ها ---
    category = models.ForeignKey(
        CourseCategory,
        verbose_name="دسته‌بندی",
        on_delete=models.PROTECT,
        related_name="courses",
    )
    instructor = models.ForeignKey(
        "accounts.InstructorProfile",
        verbose_name="مدرس",
        on_delete=models.SET_NULL,
        related_name="courses",
        null=True,
        blank=True,
    )

    # --- نوع و سطح ---
    course_type = models.CharField(
        "شیوه برگزاری",
        max_length=20,
        choices=CourseType.choices,
        default=CourseType.ONLINE_LIVE,
    )
    level = models.CharField(
        "سطح",
        max_length=20,
        choices=CourseLevel.choices,
        default=CourseLevel.BEGINNER,
    )

    # --- قیمت (به تومان) ---
    price = models.PositiveIntegerField(
        "قیمت (تومان)",
        default=0,
        help_text="صفر یعنی دوره رایگان است.",
    )
    discount_price = models.PositiveIntegerField(
        "قیمت با تخفیف (تومان)",
        null=True,
        blank=True,
        help_text="اگر پر شود، قیمت اصلی خط‌خورده نمایش داده می‌شود.",
    )

    # --- تصاویر ---
    thumbnail = models.ImageField("تصویر کارت دوره", upload_to="courses/", blank=True, null=True)
    hero_image = models.ImageField("تصویر بزرگ دوره", upload_to="courses/", blank=True, null=True)

    # --- زمان‌بندی ---
    start_date = models.DateField("تاریخ شروع", null=True, blank=True)
    end_date = models.DateField("تاریخ پایان", null=True, blank=True)
    duration_hours = models.PositiveIntegerField("مدت دوره (ساعت)", default=0)
    capacity = models.PositiveIntegerField(
        "ظرفیت",
        null=True,
        blank=True,
        help_text="خالی یعنی بدون محدودیت.",
    )
    location = models.CharField(
        "محل برگزاری",
        max_length=120,
        blank=True,
        help_text="برای دوره‌های آنلاین می‌توانید «آنلاین» بنویسید.",
    )

    # --- محتوای آموزشی ---
    prerequisites = models.TextField("پیش‌نیازها", blank=True)
    target_audience = models.TextField("مخاطبان دوره", blank=True)
    syllabus = models.TextField(
        "سرفصل‌ها",
        blank=True,
        help_text="هر سرفصل را در یک خط بنویسید.",
    )

    # --- امکانات ---
    certificate_available = models.BooleanField("دارای گواهی", default=True)
    exam_available = models.BooleanField("دارای آزمون", default=True)

    # --- وضعیت ---
    is_featured = models.BooleanField("دوره منتخب", default=False)
    is_published = models.BooleanField(
        "منتشر شده",
        default=False,
        help_text="تا وقتی خاموش باشد، دوره در سایت دیده نمی‌شود.",
    )

    # --- سئو ---
    meta_title = models.CharField("عنوان سئو", max_length=70, blank=True)
    meta_description = models.CharField("توضیحات سئو", max_length=160, blank=True)

    created_at = models.DateTimeField("تاریخ ایجاد", auto_now_add=True)
    updated_at = models.DateTimeField("آخرین بروزرسانی", auto_now=True)

    objects = PublishedCourseQuerySet.as_manager()

    class Meta:
        verbose_name = "دوره"
        verbose_name_plural = "دوره‌ها"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["is_published", "is_featured"]),
            models.Index(fields=["start_date"]),
        ]

    def __str__(self) -> str:
        return self.title

    def get_absolute_url(self) -> str:
        return reverse("courses:detail", kwargs={"slug": self.slug})

    # --- قیمت ---
    @property
    def is_free(self) -> bool:
        return self.final_price == 0

    @property
    def final_price(self) -> int:
        """قیمتی که کاربر واقعاً پرداخت می‌کند."""
        if self.discount_price is not None and self.discount_price < self.price:
            return self.discount_price
        return self.price

    @property
    def has_discount(self) -> bool:
        return self.discount_price is not None and self.discount_price < self.price

    @property
    def discount_percent(self) -> int:
        if not self.has_discount or self.price == 0:
            return 0
        return round((self.price - self.discount_price) / self.price * 100)

    # --- زمان‌بندی ---
    @property
    def is_upcoming(self) -> bool:
        return bool(self.start_date and self.start_date >= timezone.now().date())

    @property
    def registration_open(self) -> bool:
        """ثبت‌نام تا قبل از شروع دوره باز است."""
        if not self.is_published:
            return False
        if self.start_date is None:
            return True  # دوره آفلاین بدون تاریخ شروع، همیشه باز است.
        return self.start_date >= timezone.now().date()

    @property
    def syllabus_items(self) -> list[str]:
        """سرفصل‌ها را خط‌به‌خط به لیست تبدیل می‌کند."""
        return [line.strip() for line in self.syllabus.splitlines() if line.strip()]
