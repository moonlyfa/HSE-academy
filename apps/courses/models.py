"""
مدل‌های دسته‌بندی و دوره.

این مدل‌ها قلب سایت هستند: صفحه اصلی، صفحه دوره‌ها، تقویم آموزشی و بعداً
سبد خرید و گواهی همگی از همین‌ها می‌خوانند.
"""

from datetime import timedelta

from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils import timezone

from .storages import lesson_attachment_path, lesson_video_path, protected_storage


class CourseType(models.TextChoices):
    """شیوه برگزاری دوره."""

    IN_PERSON = "in_person", "حضوری"
    ONLINE_LIVE = "online_live", "آنلاین زنده"
    OFFLINE_RECORDED = "offline_recorded", "آفلاین (ضبط‌شده)"
    HYBRID = "hybrid", "ترکیبی"


def online_courses_enabled() -> bool:
    """
    آیا بخش دوره‌های غیرحضوری روشن است؟ (ONLINE_COURSES_ENABLED)

    هر بار از تنظیمات خوانده می‌شود، نه یک‌بار هنگام بارگذاری ماژول؛ وگرنه
    تغییر کلید بدون ری‌استارت کامل اثر نمی‌کرد و تست‌ها هم نمی‌توانستند
    هر دو حالت را امتحان کنند.
    """
    return settings.ONLINE_COURSES_ENABLED


def offered_course_types() -> list[str]:
    """
    شیوه‌های برگزاری‌ای که همین حالا در سایت عرضه می‌شوند.

    دوره‌ای که شیوه‌اش در این فهرست نیست حذف نمی‌شود؛ فقط مثل دوره
    منتشرنشده رفتار می‌کند: نه در فهرست‌ها می‌آید، نه صفحه‌اش باز می‌شود،
    نه به سبد خرید اضافه می‌شود.
    """
    if online_courses_enabled():
        return list(CourseType.values)
    return [CourseType.IN_PERSON]


def offered_courses_q(prefix: str = "") -> models.Q:
    """
    شرط «دوره در سایت دیده می‌شود» برای کوئری‌ها.

    برای شمارش دوره‌ها از طرف دسته‌بندی یا مدرس، prefix را "courses__"
    بدهید. یک تابع برای همه، تا هیچ شمارنده‌ای دوره‌ی پنهان را نشمارد.
    """
    return models.Q(
        **{
            f"{prefix}is_published": True,
            f"{prefix}course_type__in": offered_course_types(),
        }
    )


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
        return self.courses.filter(offered_courses_q()).count()


class PublishedCourseQuerySet(models.QuerySet):
    def published(self):
        """دوره‌هایی که در سایت دیده می‌شوند: منتشرشده و با شیوه برگزاری فعال."""
        return self.filter(offered_courses_q())

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
        default=CourseType.IN_PERSON,
        help_text=(
            "تا وقتی دوره‌های غیرحضوری خاموش‌اند (ONLINE_COURSES_ENABLED)، "
            "دوره‌ای با شیوه‌ای غیر از «حضوری» در سایت دیده نمی‌شود."
        ),
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
        help_text="نشانی یا شهر برگزاری کلاس حضوری. مثال: تهران، خیابان ولیعصر، سالن همایش",
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

    access_duration_days = models.PositiveIntegerField(
        "مدت دسترسی (روز)",
        null=True,
        blank=True,
        help_text=(
            "بعد از خرید، دانشجو چند روز به محتوای دوره دسترسی داشته باشد؟ "
            "خالی بگذارید تا دسترسی دائمی باشد."
        ),
    )
    vip_access = models.BooleanField(
        "در دسترس کاربران ویژه",
        default=True,
        help_text="اگر خاموش باشد، این دوره حتی برای کاربران ویژه هم باید جداگانه خریداری شود.",
    )

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

    # --- شیوه برگزاری ---
    @property
    def is_in_person(self) -> bool:
        return self.course_type == CourseType.IN_PERSON

    @property
    def is_offered(self) -> bool:
        """آیا این دوره همین حالا در سایت دیده می‌شود؟ (همان شرط published())"""
        return self.is_published and self.course_type in offered_course_types()

    @property
    def has_online_content(self) -> bool:
        """
        آیا صفحه دوره باید درس‌ها، ویدیوها و کلاس‌های آنلاین را نشان دهد؟

        دوره حضوری محتوای آنلاین ندارد، حتی اگر مدیر برایش فصل ساخته
        باشد؛ و وقتی بخش آنلاین خاموش است، هیچ دوره‌ای ندارد.
        """
        return online_courses_enabled() and not self.is_in_person

    # --- زمان‌بندی ---
    @property
    def is_upcoming(self) -> bool:
        return bool(self.start_date and self.start_date >= timezone.now().date())

    @property
    def registration_open(self) -> bool:
        """ثبت‌نام تا قبل از شروع دوره باز است."""
        if not self.is_offered:
            return False
        if self.start_date is None:
            return True  # دوره آفلاین بدون تاریخ شروع، همیشه باز است.
        return self.start_date >= timezone.now().date()

    @property
    def syllabus_items(self) -> list[str]:
        """سرفصل‌ها را خط‌به‌خط به لیست تبدیل می‌کند."""
        return [line.strip() for line in self.syllabus.splitlines() if line.strip()]

    # --- ساختار محتوا (فصل‌ها و درس‌ها) ---
    @property
    def visible_sections(self):
        """فصل‌های منتشرشده به‌همراه درس‌هایشان، با یک کوئری."""
        return self.sections.filter(is_published=True).prefetch_related("lessons")

    @property
    def has_curriculum(self) -> bool:
        """
        آیا این دوره محتوای ساختاریافته دارد؟

        دوره‌های قدیمی فقط فیلد متنی «سرفصل‌ها» را پر کرده‌اند. صفحه دوره اگر
        فصل واقعی موجود باشد آن را نشان می‌دهد و در غیر این صورت به همان متن
        برمی‌گردد؛ پس لازم نیست ادمین همه دوره‌ها را یک‌شبه دوباره وارد کند.
        """
        return self.sections.filter(is_published=True).exists()

    @property
    def lesson_count(self) -> int:
        return Lesson.objects.filter(
            section__course=self, section__is_published=True, is_published=True
        ).count()

    @property
    def curriculum_minutes(self) -> int:
        total = Lesson.objects.filter(
            section__course=self, section__is_published=True, is_published=True
        ).aggregate(total=models.Sum("duration_minutes"))
        return total["total"] or 0

    @property
    def preview_lesson(self):
        """اولین درس رایگان دوره — برای دکمه «مشاهده پیش‌نمایش»."""
        return (
            Lesson.objects.filter(
                section__course=self,
                section__is_published=True,
                is_published=True,
                is_free_preview=True,
            )
            .order_by("section__order", "order")
            .first()
        )


class Section(models.Model):
    """
    یک فصل از دوره — مثل «مبانی ایمنی» یا «ارزیابی ریسک».

    چرا بین دوره و درس یک لایه اضافه کردیم؟
    چون یک دوره چهل ساعته ممکن است سی درس داشته باشد. نمایش سی درس پشت‌سرهم
    برای دانشجو گیج‌کننده است؛ اما همان سی درس داخل شش فصل، ساختار دوره را
    در یک نگاه نشان می‌دهد.
    """

    course = models.ForeignKey(
        Course,
        verbose_name="دوره",
        on_delete=models.CASCADE,
        related_name="sections",
    )
    title = models.CharField("عنوان فصل", max_length=200)
    description = models.TextField("توضیح کوتاه", blank=True)
    order = models.PositiveIntegerField("ترتیب نمایش", default=0)
    is_published = models.BooleanField(
        "منتشر شده",
        default=True,
        help_text="تا وقتی خاموش باشد، این فصل و درس‌هایش در سایت دیده نمی‌شوند.",
    )

    created_at = models.DateTimeField("تاریخ ایجاد", auto_now_add=True)
    updated_at = models.DateTimeField("آخرین بروزرسانی", auto_now=True)

    class Meta:
        verbose_name = "فصل دوره"
        verbose_name_plural = "فصل‌های دوره"
        ordering = ["order", "id"]
        indexes = [models.Index(fields=["course", "order"])]

    def __str__(self) -> str:
        return f"{self.course.title} — {self.title}"

    @property
    def visible_lessons(self):
        return self.lessons.filter(is_published=True)

    @property
    def lesson_count(self) -> int:
        return self.visible_lessons.count()

    @property
    def total_minutes(self) -> int:
        total = self.visible_lessons.aggregate(total=models.Sum("duration_minutes"))
        return total["total"] or 0


class LessonType(models.TextChoices):
    """نوع محتوای درس."""

    VIDEO = "video", "ویدیو"
    TEXT = "text", "متن آموزشی"
    FILE = "file", "فایل و جزوه"
    LIVE = "live", "جلسه آنلاین زنده"


class Lesson(models.Model):
    """
    یک درس (جلسه) از یک فصل.

    نکته امنیتی مهم: فایل ویدیو و جزوه در پوشه محافظت‌شده ذخیره می‌شوند، نه
    داخل media/. هیچ‌کس نمی‌تواند با کپی کردن آدرس، محتوای دوره پولی را
    ببیند؛ تحویل فایل فقط از راه Viewهایی انجام می‌شود که مجوز را بررسی
    می‌کنند. توضیح کامل در apps/courses/storages.py آمده است.
    """

    section = models.ForeignKey(
        Section,
        verbose_name="فصل",
        on_delete=models.CASCADE,
        related_name="lessons",
    )
    title = models.CharField("عنوان درس", max_length=200)
    summary = models.TextField("توضیح کوتاه", max_length=400, blank=True)
    lesson_type = models.CharField(
        "نوع محتوا",
        max_length=20,
        choices=LessonType.choices,
        default=LessonType.VIDEO,
    )
    order = models.PositiveIntegerField("ترتیب نمایش", default=0)
    duration_minutes = models.PositiveIntegerField(
        "مدت (دقیقه)",
        default=0,
        help_text="برای درس‌های متنی می‌توانید زمان تقریبی مطالعه را بنویسید.",
    )

    # --- محتوا ---
    content = models.TextField(
        "متن درس",
        blank=True,
        help_text="برای درس‌های متنی. برای ویدیو می‌توانید خلاصه یا نکات مهم را بنویسید.",
    )
    video_file = models.FileField(
        "فایل ویدیو",
        upload_to=lesson_video_path,
        storage=protected_storage,
        blank=True,
        null=True,
        help_text="فایل روی سرور خودتان و خارج از دسترس مستقیم ذخیره می‌شود.",
    )
    video_external_url = models.URLField(
        "آدرس مستقیم ویدیو",
        blank=True,
        help_text=(
            "اگر ویدیو روی سرور دیگری از خودتان است، آدرس مستقیم فایل را بگذارید. "
            "برای پایداری در زمان اختلال اینترنت، از سرویس‌های خارجی استفاده نکنید."
        ),
    )
    scheduled_at = models.DateTimeField(
        "زمان برگزاری",
        null=True,
        blank=True,
        help_text="فقط برای جلسه‌های آنلاین زنده.",
    )

    # --- دسترسی ---
    is_free_preview = models.BooleanField(
        "پیش‌نمایش رایگان",
        default=False,
        help_text="اگر روشن باشد، این درس برای همه بازدیدکنندگان باز است.",
    )
    is_published = models.BooleanField("منتشر شده", default=True)

    created_at = models.DateTimeField("تاریخ ایجاد", auto_now_add=True)
    updated_at = models.DateTimeField("آخرین بروزرسانی", auto_now=True)

    class Meta:
        verbose_name = "درس"
        verbose_name_plural = "درس‌ها"
        ordering = ["order", "id"]
        indexes = [models.Index(fields=["section", "order"])]

    def __str__(self) -> str:
        return self.title

    def get_absolute_url(self) -> str:
        return reverse(
            "courses:lesson",
            kwargs={"slug": self.section.course.slug, "pk": self.pk},
        )

    @property
    def course(self) -> Course:
        return self.section.course

    @property
    def has_video(self) -> bool:
        return bool(self.video_file or self.video_external_url)

    @property
    def is_visible(self) -> bool:
        """درس فقط وقتی در سایت دیده می‌شود که خودش و فصلش منتشر شده باشند."""
        return self.is_published and self.section.is_published


class LessonAttachment(models.Model):
    """
    فایل ضمیمه یک درس — جزوه، چک‌لیست، فرم یا اسلاید.

    چرا مدل جداست و یک فیلد ساده روی درس نیست؟
    چون یک جلسه معمولاً بیش از یک پیوست دارد (اسلاید + چک‌لیست + نمونه فرم)
    و با یک فیلد ثابت، مدرس مجبور می‌شد همه را در یک فایل زیپ بگذارد.
    """

    lesson = models.ForeignKey(
        Lesson,
        verbose_name="درس",
        on_delete=models.CASCADE,
        related_name="attachments",
    )
    title = models.CharField("عنوان فایل", max_length=200)
    file = models.FileField(
        "فایل",
        upload_to=lesson_attachment_path,
        storage=protected_storage,
    )
    order = models.PositiveIntegerField("ترتیب نمایش", default=0)
    created_at = models.DateTimeField("تاریخ افزودن", auto_now_add=True)

    class Meta:
        verbose_name = "پیوست درس"
        verbose_name_plural = "پیوست‌های درس"
        ordering = ["order", "id"]

    def __str__(self) -> str:
        return self.title

    def get_absolute_url(self) -> str:
        return reverse(
            "courses:lesson_attachment",
            kwargs={
                "slug": self.lesson.section.course.slug,
                "pk": self.lesson_id,
                "attachment_pk": self.pk,
            },
        )

    @property
    def size_display(self) -> str:
        """حجم فایل به شکل خوانا؛ اگر فایل روی دیسک نبود، خطا نمی‌دهد."""
        try:
            size = self.file.size
        except (OSError, ValueError):
            return ""

        for unit in ("بایت", "کیلوبایت", "مگابایت"):
            if size < 1024:
                return f"{size:.0f} {unit}"
            size /= 1024
        return f"{size:.1f} گیگابایت"


class LessonProgress(models.Model):
    """
    پیشرفت یک کاربر در یک درس.

    چرا یک ردیف به‌ازای هر «کاربر × درس»؟
    چون این ریزترین واحدی است که سؤال‌های واقعی را جواب می‌دهد: «چند درصد
    دوره را گذرانده‌ام؟»، «کجا بودم؟»، «کدام درس را ندیده‌ام؟». اگر فقط یک
    عدد درصد روی دوره نگه می‌داشتیم، هیچ‌کدام از این‌ها را نمی‌شد بازسازی کرد.

    ردیف وقتی ساخته می‌شود که کاربر درس را باز کند؛ یعنی «دیده شده» با
    «تکمیل شده» فرق دارد. تکمیل شدن را خود کاربر اعلام می‌کند.
    """

    user = models.ForeignKey(
        "accounts.User",
        verbose_name="کاربر",
        on_delete=models.CASCADE,
        related_name="lesson_progress",
    )
    lesson = models.ForeignKey(
        Lesson,
        verbose_name="درس",
        on_delete=models.CASCADE,
        related_name="progress_records",
    )

    is_completed = models.BooleanField("تکمیل شده", default=False)
    completed_at = models.DateTimeField("زمان تکمیل", null=True, blank=True)

    last_position_seconds = models.PositiveIntegerField(
        "آخرین ثانیه تماشا",
        default=0,
        help_text="برای ادامه دادن ویدیو از همان جایی که کاربر رها کرده بود.",
    )

    first_viewed_at = models.DateTimeField("اولین بازدید", auto_now_add=True)
    last_viewed_at = models.DateTimeField("آخرین بازدید", auto_now=True)

    class Meta:
        verbose_name = "پیشرفت درس"
        verbose_name_plural = "پیشرفت درس‌ها"
        # یک کاربر برای هر درس فقط یک ردیف دارد؛ دیتابیس خودش این را
        # تضمین می‌کند تا حتی دو درخواست هم‌زمان هم ردیف تکراری نسازند.
        constraints = [
            models.UniqueConstraint(
                fields=["user", "lesson"], name="unique_progress_per_user_lesson"
            )
        ]
        indexes = [models.Index(fields=["user", "-last_viewed_at"])]
        ordering = ["-last_viewed_at"]

    def __str__(self) -> str:
        return f"{self.user} — {self.lesson}"


class EnrollmentSource(models.TextChoices):
    """
    ثبت‌نام از کجا آمده است؟

    نگه داشتن این اطلاعات برای گزارش‌گیری لازم است: چند نفر خریده‌اند،
    چند نفر دوره رایگان را برداشته‌اند، و چند نفر را پشتیبانی دستی
    اضافه کرده است.
    """

    PURCHASE = "purchase", "خرید"
    FREE = "free", "دوره رایگان"
    MANUAL = "manual", "افزودن دستی توسط مدیر"
    VIP = "vip", "اشتراک ویژه"
    GIFT = "gift", "هدیه"


class EnrollmentStatus(models.TextChoices):
    ACTIVE = "active", "فعال"
    SUSPENDED = "suspended", "تعلیق‌شده"
    REFUNDED = "refunded", "بازگشت وجه"


class Enrollment(models.Model):
    """
    ثبت‌نام یک کاربر در یک دوره — یعنی «این شخص به این دوره دسترسی دارد».

    چرا مدل جدا لازم بود، وقتی سفارش پرداخت‌شده هم همین را می‌گفت؟
    چون دسترسی همیشه از خرید نمی‌آید: دوره رایگان، دانشجویی که سازمانش
    ثبت‌نامش کرده، شرکت‌کننده‌ای که پشتیبانی دستی اضافه کرده، و اشتراک
    ویژه. اگر دسترسی را از روی سفارش می‌خواندیم، هیچ‌کدام از این‌ها جا
    نمی‌شدند.

    ضمناً دسترسی می‌تواند مدت‌دار باشد یا تعلیق شود — چیزی که یک سفارشِ
    پرداخت‌شده به تنهایی نمی‌تواند بیان کند.
    """

    user = models.ForeignKey(
        "accounts.User",
        verbose_name="کاربر",
        on_delete=models.CASCADE,
        related_name="enrollments",
    )
    course = models.ForeignKey(
        Course,
        verbose_name="دوره",
        on_delete=models.CASCADE,
        related_name="enrollments",
    )

    source = models.CharField(
        "منبع ثبت‌نام",
        max_length=20,
        choices=EnrollmentSource.choices,
        default=EnrollmentSource.PURCHASE,
    )
    status = models.CharField(
        "وضعیت",
        max_length=20,
        choices=EnrollmentStatus.choices,
        default=EnrollmentStatus.ACTIVE,
    )

    order = models.ForeignKey(
        "orders.Order",
        verbose_name="سفارش",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="enrollments",
        help_text="اگر ثبت‌نام از راه خرید بوده، سفارش مربوطه.",
    )

    starts_at = models.DateTimeField("شروع دسترسی", default=timezone.now)
    expires_at = models.DateTimeField(
        "پایان دسترسی",
        null=True,
        blank=True,
        help_text="خالی یعنی دسترسی دائمی است.",
    )

    # دوره حضوری درسِ آنلاینی ندارد که دانشجو «تکمیل» کند؛ گذراندن آن را
    # آکادمی بعد از برگزاری کلاس تأیید می‌کند. همین تاریخ برای دوره حضوری
    # نقش «همه درس‌ها تکمیل شد» را دارد و آزمون و گواهی از روی آن باز
    # می‌شوند.
    completed_at = models.DateTimeField(
        "تأیید گذراندن دوره",
        null=True,
        blank=True,
        help_text=(
            "برای دوره حضوری: بعد از اینکه دانشجو در کلاس شرکت کرد و دوره را "
            "گذراند، این تاریخ را پر کنید (یا از عملیات «تأیید گذراندن دوره» در "
            "فهرست ثبت‌نام‌ها استفاده کنید). تا خالی است، آزمون پایانی (اگر "
            "«فقط پس از تکمیل دوره» باشد) و گواهی باز نمی‌شوند."
        ),
    )

    note = models.CharField("یادداشت", max_length=300, blank=True)

    created_at = models.DateTimeField("تاریخ ثبت‌نام", auto_now_add=True)
    updated_at = models.DateTimeField("آخرین تغییر", auto_now=True)

    class Meta:
        verbose_name = "ثبت‌نام"
        verbose_name_plural = "ثبت‌نام‌ها"
        ordering = ["-created_at"]
        constraints = [
            # یک کاربر در یک دوره فقط یک‌بار ثبت‌نام دارد. اگر دوباره
            # بخرد، همان ردیف تمدید می‌شود نه اینکه ردیف دوم ساخته شود.
            models.UniqueConstraint(
                fields=["user", "course"], name="unique_enrollment_per_user_course"
            )
        ]
        indexes = [
            models.Index(fields=["user", "status"]),
            models.Index(fields=["course", "status"]),
        ]

    def __str__(self) -> str:
        return f"{self.user} — {self.course}"

    @property
    def is_expired(self) -> bool:
        return bool(self.expires_at and timezone.now() > self.expires_at)

    @property
    def has_started(self) -> bool:
        return timezone.now() >= self.starts_at

    @property
    def is_active(self) -> bool:
        """
        آیا این ثبت‌نام هم‌اکنون دسترسی می‌دهد؟

        انقضا هربار محاسبه می‌شود، نه اینکه در فیلد status ذخیره شود.
        اگر ذخیره می‌شد، دسترسی تا اجرای بعدی یک دستور زمان‌بندی‌شده باز
        می‌ماند — یعنی ساعت‌ها بعد از تمام شدن مهلت.
        """
        return (
            self.status == EnrollmentStatus.ACTIVE
            and self.has_started
            and not self.is_expired
        )

    @property
    def days_remaining(self) -> int | None:
        """چند روز تا پایان دسترسی؟ None یعنی دسترسی دائمی."""
        if not self.expires_at:
            return None
        remaining = self.expires_at - timezone.now()
        return max(remaining.days, 0)

    @property
    def is_expiring_soon(self) -> bool:
        """کمتر از یک هفته تا پایان دسترسی."""
        days = self.days_remaining
        return days is not None and days <= 7


class OnlineSessionStatus(models.TextChoices):
    SCHEDULED = "scheduled", "برنامه‌ریزی‌شده"
    CANCELLED = "cancelled", "لغو شده"


class OnlineSessionQuerySet(models.QuerySet):
    """کوئری‌های پرتکرار جلسه‌های آنلاین."""

    def scheduled(self):
        return self.filter(status=OnlineSessionStatus.SCHEDULED)

    def upcoming(self):
        """
        جلسه‌هایی که هنوز تمام نشده‌اند — از نزدیک‌ترین.

        جلسه لغوشده هم در این فهرست می‌ماند (و با برچسب «لغو شده» دیده
        می‌شود). حذفش از فهرست یعنی دانشجویی که منتظر کلاس فردا بوده،
        فردا فقط یک جای خالی می‌بیند و نمی‌فهمد چه شده است.
        """
        return self.filter(ends_at__gte=timezone.now()).order_by("starts_at")

    def past(self):
        """جلسه‌های برگزارشده — از تازه‌ترین."""
        return self.filter(ends_at__lt=timezone.now()).order_by("-starts_at")


class OnlineSession(models.Model):
    """
    یک جلسه کلاس آنلاین زنده (اسکای‌روم یا هر سامانه مشابه).

    چرا جلسه به دوره وصل است و نه به فصل؟ چون جلسه آنلاین یک **رویداد
    زمان‌دار** است: ساعت مشخصی شروع می‌شود و تمام می‌شود. فصل‌ها ترتیب
    محتوا را می‌گویند، نه تقویم را. اگر جلسه را داخل فصل می‌گذاشتیم،
    برای ساده‌ترین سؤال دانشجو — «کلاس بعدی من کِی است؟» — باید کل
    درس‌های همه دوره‌ها را می‌گشتیم.

    فیلد اختیاری `lesson` برای وقتی است که همین جلسه در سرفصل هم یک
    ردیف دارد (درس از نوع «جلسه آنلاین زنده»)؛ آن‌وقت دکمه ورود در
    صفحه همان درس هم دیده می‌شود.

    **آدرس کلاس هیچ‌وقت داخل HTML قرار نمی‌گیرد.** صفحه فقط به
    `courses:session_join` لینک می‌دهد و آن View پیش از هدایت کاربر،
    ثبت‌نامش را بررسی می‌کند. اگر آدرس را مستقیم در صفحه می‌گذاشتیم،
    هر بازدیدکننده‌ای می‌توانست با دیدن سورس صفحه وارد کلاسی شود که
    پولش را نداده است.
    """

    course = models.ForeignKey(
        Course,
        verbose_name="دوره",
        on_delete=models.CASCADE,
        related_name="online_sessions",
    )
    lesson = models.ForeignKey(
        Lesson,
        verbose_name="درس مرتبط",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="online_sessions",
        help_text="اختیاری. اگر این جلسه در سرفصل دوره هم یک درس دارد، آن را انتخاب کنید.",
    )

    title = models.CharField("عنوان جلسه", max_length=200)
    description = models.TextField("توضیح کوتاه", blank=True)

    starts_at = models.DateTimeField("زمان شروع")
    duration_minutes = models.PositiveIntegerField("مدت (دقیقه)", default=90)

    # زمان پایان از شروع و مدت ساخته می‌شود و در save() بروز می‌ماند.
    # برخلاف «وضعیت انقضا» که با گذر زمان کهنه می‌شود، این مقدار فقط به
    # دو فیلد دیگر وابسته است؛ پس ذخیره‌اش بی‌خطر است و در عوض اجازه
    # می‌دهد «جلسه‌های تمام‌نشده» را با یک کوئری ساده بگیریم.
    ends_at = models.DateTimeField("زمان پایان", editable=False, db_index=True)

    meeting_url = models.URLField(
        "آدرس ورود به کلاس",
        blank=True,
        help_text=(
            "لینکی که از پنل اسکای‌روم کپی می‌کنید. این آدرس هرگز در صفحه سایت "
            "نمایش داده نمی‌شود و فقط به کاربر ثبت‌نام‌شده تحویل می‌شود."
        ),
    )
    room_id = models.CharField(
        "شناسه کلاس در اسکای‌روم",
        max_length=50,
        blank=True,
        help_text="فقط برای حالت اتصال خودکار به API اسکای‌روم لازم است.",
    )

    status = models.CharField(
        "وضعیت",
        max_length=20,
        choices=OnlineSessionStatus.choices,
        default=OnlineSessionStatus.SCHEDULED,
    )
    cancel_reason = models.CharField("علت لغو", max_length=300, blank=True)

    created_at = models.DateTimeField("تاریخ ایجاد", auto_now_add=True)
    updated_at = models.DateTimeField("آخرین بروزرسانی", auto_now=True)

    objects = OnlineSessionQuerySet.as_manager()

    class Meta:
        verbose_name = "جلسه آنلاین"
        verbose_name_plural = "جلسه‌های آنلاین"
        ordering = ["starts_at", "id"]
        indexes = [models.Index(fields=["course", "starts_at"])]

    def __str__(self) -> str:
        return f"{self.title} — {self.course.title}"

    def clean(self) -> None:
        """درس انتخاب‌شده باید از همین دوره باشد."""
        from django.core.exceptions import ValidationError

        if self.lesson_id and self.lesson.section.course_id != self.course_id:
            raise ValidationError(
                {"lesson": "این درس متعلق به دوره انتخاب‌شده نیست."}
            )

    def save(self, *args, **kwargs):
        self.ends_at = self.starts_at + timedelta(minutes=self.duration_minutes or 0)
        super().save(*args, **kwargs)

    # --- زمان‌بندی ---

    @property
    def join_opens_at(self):
        """
        از چه لحظه‌ای دکمه ورود فعال می‌شود؟

        کمی زودتر از شروع کلاس، چون دانشجو معمولاً چند دقیقه قبل پشت
        سیستم می‌نشیند و نباید پشت یک دکمه خاکستری بماند.
        """
        return self.starts_at - timedelta(minutes=settings.ONLINE_SESSION_JOIN_LEAD_MINUTES)

    @property
    def join_closes_at(self):
        """کلاس‌ها گاهی طول می‌کشند؛ لینک کمی بعد از زمان پایان هم باز می‌ماند."""
        return self.ends_at + timedelta(minutes=settings.ONLINE_SESSION_GRACE_MINUTES)

    @property
    def is_cancelled(self) -> bool:
        return self.status == OnlineSessionStatus.CANCELLED

    @property
    def is_finished(self) -> bool:
        return not self.is_cancelled and timezone.now() > self.join_closes_at

    @property
    def is_running(self) -> bool:
        """الان زمان ورود به کلاس است."""
        if self.is_cancelled:
            return False
        return self.join_opens_at <= timezone.now() <= self.join_closes_at

    @property
    def is_upcoming(self) -> bool:
        return not self.is_cancelled and timezone.now() < self.join_opens_at

    @property
    def has_link(self) -> bool:
        return bool(self.meeting_url or self.room_id)

    @property
    def is_joinable(self) -> bool:
        """آیا همین حالا می‌شود وارد کلاس شد؟ (جدا از اینکه چه کسی)"""
        return self.is_running and self.has_link

    @property
    def state(self) -> str:
        """وضعیت جلسه برای نمایش: cancelled | finished | live | upcoming"""
        if self.is_cancelled:
            return "cancelled"
        if self.is_finished:
            return "finished"
        if self.is_running:
            return "live"
        return "upcoming"

    @property
    def state_label(self) -> str:
        return {
            "cancelled": "لغو شده",
            "finished": "برگزار شده",
            "live": "در حال برگزاری",
            "upcoming": "برگزار نشده",
        }[self.state]

    def get_join_url(self) -> str:
        return reverse(
            "courses:session_join",
            kwargs={"slug": self.course.slug, "pk": self.pk},
        )
