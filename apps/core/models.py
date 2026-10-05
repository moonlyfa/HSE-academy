"""
مدل‌های عمومی سایت.

همه محتوای صفحه اصلی از این مدل‌ها خوانده می‌شود تا ادمین بتواند بدون
دست‌زدن به کد، متن‌ها، بنرها و بخش‌های سایت را تغییر دهد.
"""

from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


class ActiveOrderedQuerySet(models.QuerySet):
    """کوئری‌ست مشترک: فقط موارد فعال، مرتب‌شده بر اساس ترتیب نمایش."""

    def active(self):
        return self.filter(is_active=True)


class BaseContentBlock(models.Model):
    """
    فیلدهای مشترک همه بخش‌های قابل مدیریت صفحه اصلی.

    مدل Abstract یعنی برای خودش جدول نمی‌سازد؛ فقط فیلدهایش را به
    مدل‌های فرزند قرض می‌دهد تا کد تکراری ننویسیم.
    """

    is_active = models.BooleanField(
        "فعال",
        default=True,
        help_text="اگر خاموش باشد، در سایت نمایش داده نمی‌شود.",
    )
    order = models.PositiveIntegerField(
        "ترتیب نمایش",
        default=0,
        help_text="عدد کوچک‌تر بالاتر نمایش داده می‌شود.",
    )
    created_at = models.DateTimeField("تاریخ ایجاد", auto_now_add=True)
    updated_at = models.DateTimeField("آخرین بروزرسانی", auto_now=True)

    objects = ActiveOrderedQuerySet.as_manager()

    class Meta:
        abstract = True
        ordering = ["order", "-created_at"]


class SiteSetting(models.Model):
    """
    تنظیمات کلی سایت — فقط یک ردیف در دیتابیس دارد.

    چرا مدل و نه فایل settings.py؟ چون ادمین باید بتواند شماره تماس یا متن
    Hero را از پنل عوض کند، بدون اینکه به کد و ری‌استارت سرور نیاز باشد.
    """

    # --- هویت سایت ---
    site_name = models.CharField("نام سایت", max_length=100, default="سپر آکادمی")
    site_tagline = models.CharField(
        "شعار سایت",
        max_length=200,
        blank=True,
        default="آموزش تخصصی ایمنی، بهداشت و محیط زیست",
    )
    logo = models.ImageField("لوگو", upload_to="site/", blank=True, null=True)
    favicon = models.ImageField("آیکون مرورگر", upload_to="site/", blank=True, null=True)

    # --- اطلاعات تماس ---
    phone = models.CharField("تلفن تماس", max_length=30, blank=True, default="021-00000000")
    mobile = models.CharField("موبایل پشتیبانی", max_length=30, blank=True)
    email = models.EmailField("ایمیل", blank=True, default="info@example.com")
    address = models.TextField("آدرس", blank=True)
    working_hours = models.CharField(
        "ساعات کاری",
        max_length=120,
        blank=True,
        default="شنبه تا چهارشنبه، ۹ تا ۱۷",
    )

    # --- شبکه‌های اجتماعی ---
    instagram_url = models.URLField("اینستاگرام", blank=True)
    telegram_url = models.URLField("تلگرام", blank=True)
    linkedin_url = models.URLField("لینکدین", blank=True)
    whatsapp_url = models.URLField("واتساپ", blank=True)

    # --- درباره ما ---
    about_short = models.TextField(
        "معرفی کوتاه (فوتر)",
        blank=True,
        default="آکادمی تخصصی آموزش ایمنی، بهداشت و محیط زیست.",
    )
    about_full = models.TextField("متن کامل درباره ما", blank=True)

    # --- کنترل نمایش بخش‌های صفحه اصلی ---
    # ادمین می‌تواند هر بخش را بدون تغییر کد خاموش کند.
    show_hero_slider = models.BooleanField("نمایش اسلایدر بالای صفحه", default=True)
    show_calendar_section = models.BooleanField("نمایش تقویم دوره‌های آموزشی", default=True)
    show_categories_section = models.BooleanField("نمایش بخش دسته‌بندی‌ها", default=True)
    show_featured_courses = models.BooleanField("نمایش دوره‌های منتخب", default=True)
    show_features_section = models.BooleanField("نمایش بخش چرا ما", default=True)
    show_instructors_section = models.BooleanField("نمایش مدرسان", default=True)
    show_testimonials_section = models.BooleanField("نمایش نظرات", default=True)
    show_partners_section = models.BooleanField("نمایش همکاران", default=True)
    show_faq_section = models.BooleanField("نمایش سؤالات متداول", default=True)
    show_articles_section = models.BooleanField(
        "نمایش مقالات",
        default=False,
        help_text="بخش مقالات در نسخه اول منتشر نمی‌شود.",
    )

    # --- تنظیمات اسلایدر ---
    hero_slider_interval_seconds = models.PositiveIntegerField(
        "فاصله بین اسلایدها (ثانیه)",
        default=6,
        help_text="هر چند ثانیه یک‌بار اسلاید بعدی نمایش داده شود.",
    )
    hero_slider_transition_ms = models.PositiveIntegerField(
        "مدت محو شدن اسلاید (میلی‌ثانیه)",
        default=1400,
        help_text=(
            "عدد بزرگ‌تر یعنی جابه‌جایی نرم‌تر و کندتر. "
            "مقدار پیشنهادی بین ۸۰۰ تا ۱۵۰۰."
        ),
    )

    # --- تعداد آیتم‌های صفحه اصلی ---
    homepage_calendar_count = models.PositiveIntegerField(
        "تعداد ردیف تقویم آموزشی در صفحه اصلی", default=6
    )
    homepage_category_count = models.PositiveIntegerField(
        "تعداد دسته‌بندی در صفحه اصلی", default=8
    )

    # --- پرداخت کارت به کارت ---
    card_transfer_enabled = models.BooleanField(
        "فعال بودن پرداخت کارت به کارت",
        default=False,
        help_text="تا شماره کارت وارد نشده باشد، این گزینه به خریدار نمایش داده نمی‌شود.",
    )
    card_transfer_number = models.CharField(
        "شماره کارت مقصد",
        max_length=19,
        blank=True,
        help_text="۱۶ رقم؛ با یا بدون فاصله.",
    )
    card_transfer_holder = models.CharField("نام صاحب کارت", max_length=100, blank=True)
    card_transfer_bank = models.CharField("نام بانک", max_length=50, blank=True)
    card_transfer_sheba = models.CharField(
        "شماره شبا (اختیاری)",
        max_length=34,
        blank=True,
        help_text="برای مبالغ بیشتر از سقف کارت به کارت. مثال: IR000000000000000000000000",
    )
    card_transfer_note = models.TextField(
        "توضیح برای خریدار (اختیاری)",
        blank=True,
        help_text="زیر اطلاعات کارت نمایش داده می‌شود.",
    )
    card_transfer_notify_mobile = models.CharField(
        "موبایل مدیر برای اطلاع از رسید جدید",
        max_length=11,
        blank=True,
        help_text="با ثبت هر رسید، به این شماره پیامک می‌رود. خالی یعنی پیامک نرود.",
    )

    # --- سئو ---
    meta_title = models.CharField("عنوان سئو", max_length=70, blank=True)
    meta_description = models.CharField("توضیحات سئو", max_length=160, blank=True)

    updated_at = models.DateTimeField("آخرین بروزرسانی", auto_now=True)

    class Meta:
        verbose_name = "تنظیمات سایت"
        verbose_name_plural = "تنظیمات سایت"

    def __str__(self) -> str:
        return self.site_name

    def clean(self):
        """اجازه ساخت بیش از یک ردیف تنظیمات را نمی‌دهیم."""
        if not self.pk and SiteSetting.objects.exists():
            raise ValidationError("فقط یک ردیف تنظیمات سایت می‌تواند وجود داشته باشد.")

        if self.card_transfer_enabled and len(self.card_transfer_digits) != 16:
            raise ValidationError(
                {"card_transfer_number": "برای فعال کردن کارت به کارت، شماره کارت ۱۶ رقمی را وارد کنید."}
            )

    @property
    def card_transfer_available(self) -> bool:
        """گزینه کارت به کارت فقط وقتی دیده می‌شود که روشن باشد و کارت داشته باشد."""
        return self.card_transfer_enabled and len(self.card_transfer_digits) == 16

    @property
    def card_transfer_digits(self) -> str:
        """شماره کارت فقط به‌صورت رقم انگلیسی، بدون فاصله و خط تیره."""
        digits = self.card_transfer_number.translate(
            str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
        )
        return "".join(ch for ch in digits if ch.isdigit())

    @property
    def card_transfer_display(self) -> str:
        """شماره کارت در چهار گروه چهاررقمی، برای خواندن راحت."""
        digits = self.card_transfer_digits
        return " ".join(digits[i : i + 4] for i in range(0, len(digits), 4))

    @property
    def hero_slider_interval_ms(self) -> int:
        """فاصله اسلایدها بر حسب میلی‌ثانیه — جاوااسکریپت با این واحد کار می‌کند."""
        return max(self.hero_slider_interval_seconds, 2) * 1000

    @classmethod
    def load(cls) -> "SiteSetting":
        """
        تنظیمات سایت را برمی‌گرداند و اگر وجود نداشته باشد می‌سازد.

        این‌طوری سایت حتی روی دیتابیس خالی هم بدون خطا بالا می‌آید.
        """
        setting, _ = cls.objects.get_or_create(pk=1)
        return setting


class HeroSlide(BaseContentBlock):
    """
    یک اسلاید از بنر بزرگ بالای صفحه اصلی.

    طبق خواسته کارفرما این بخش فقط تصویر است و هیچ متنی روی آن نوشته نمی‌شود.
    فیلد title فقط برای دو کار استفاده می‌شود:
      ۱. شناسایی اسلاید در پنل مدیریت
      ۲. متن جایگزین تصویر (alt) — که برای سئو و دسترس‌پذیری الزامی است
    """

    title = models.CharField(
        "عنوان (فقط برای پنل و متن جایگزین تصویر)",
        max_length=150,
        help_text="روی تصویر نمایش داده نمی‌شود.",
    )
    image = models.ImageField(
        "تصویر اسلاید",
        upload_to="slides/",
        help_text="اندازه پیشنهادی: ۱۹۲۰×۶۵۰ پیکسل.",
    )
    image_mobile = models.ImageField(
        "تصویر نسخه موبایل",
        upload_to="slides/",
        blank=True,
        null=True,
        help_text="اختیاری. اگر خالی باشد، همان تصویر اصلی استفاده می‌شود.",
    )
    link_url = models.CharField(
        "لینک اسلاید",
        max_length=300,
        blank=True,
        help_text="با کلیک روی تصویر کاربر به این آدرس می‌رود. خالی یعنی بدون لینک.",
    )

    starts_at = models.DateTimeField(
        "نمایش از تاریخ",
        null=True,
        blank=True,
        help_text="خالی یعنی بدون محدودیت شروع.",
    )
    ends_at = models.DateTimeField(
        "نمایش تا تاریخ",
        null=True,
        blank=True,
        help_text="خالی یعنی بدون محدودیت پایان.",
    )

    class Meta(BaseContentBlock.Meta):
        verbose_name = "اسلاید صفحه اصلی"
        verbose_name_plural = "اسلایدهای صفحه اصلی"

    def __str__(self) -> str:
        return self.title

    @property
    def is_visible_now(self) -> bool:
        """آیا اسلاید با توجه به بازه تاریخ، همین الان باید نمایش داده شود؟"""
        if not self.is_active:
            return False
        now = timezone.now()
        if self.starts_at and now < self.starts_at:
            return False
        if self.ends_at and now > self.ends_at:
            return False
        return True


class Feature(BaseContentBlock):
    """یک مورد از بخش «چرا ما» در صفحه اصلی."""

    ICON_CHOICES = [
        ("shield", "سپر ایمنی"),
        ("certificate", "گواهی"),
        ("users", "مدرسان"),
        ("video", "کلاس آنلاین"),
        ("download", "محتوای آفلاین"),
        ("lock", "پرداخت امن"),
        ("headset", "پشتیبانی"),
        ("chart", "کاربردی"),
    ]

    icon = models.CharField("آیکون", max_length=20, choices=ICON_CHOICES, default="shield")
    title = models.CharField("عنوان", max_length=100)
    description = models.TextField("توضیح", blank=True)

    class Meta(BaseContentBlock.Meta):
        verbose_name = "مزیت (چرا ما)"
        verbose_name_plural = "مزیت‌ها (چرا ما)"

    def __str__(self) -> str:
        return self.title


class Testimonial(BaseContentBlock):
    """نظر یک دانشجو درباره دوره‌ها."""

    full_name = models.CharField("نام و نام خانوادگی", max_length=100)
    job_title = models.CharField(
        "سمت یا سازمان",
        max_length=120,
        blank=True,
        help_text="مثلاً «کارشناس HSE، شرکت پتروشیمی»",
    )
    avatar = models.ImageField("عکس", upload_to="testimonials/", blank=True, null=True)
    quote = models.TextField("متن نظر")

    class Meta(BaseContentBlock.Meta):
        verbose_name = "نظر دانشجو"
        verbose_name_plural = "نظرات دانشجویان"

    def __str__(self) -> str:
        return self.full_name


class Partner(BaseContentBlock):
    """سازمان، شرکت یا دانشگاه همکار."""

    name = models.CharField("نام سازمان", max_length=120)
    logo = models.ImageField("لوگو", upload_to="partners/", blank=True, null=True)
    website = models.URLField("وب‌سایت", blank=True)

    class Meta(BaseContentBlock.Meta):
        verbose_name = "همکار"
        verbose_name_plural = "سازمان‌های همکار"

    def __str__(self) -> str:
        return self.name


class FAQ(BaseContentBlock):
    """سؤال متداول."""

    question = models.CharField("سؤال", max_length=250)
    answer = models.TextField("پاسخ")
    show_on_homepage = models.BooleanField(
        "نمایش در صفحه اصلی",
        default=True,
        help_text="اگر خاموش باشد فقط در صفحه سؤالات متداول دیده می‌شود.",
    )

    class Meta(BaseContentBlock.Meta):
        verbose_name = "سؤال متداول"
        verbose_name_plural = "سؤالات متداول"

    def __str__(self) -> str:
        return self.question


class ContactMessage(models.Model):
    """پیام ارسال‌شده از فرم تماس با ما."""

    full_name = models.CharField("نام و نام خانوادگی", max_length=100)
    mobile = models.CharField("شماره تماس", max_length=20)
    email = models.EmailField("ایمیل", blank=True)
    subject = models.CharField("موضوع", max_length=150)
    message = models.TextField("متن پیام")

    is_read = models.BooleanField("خوانده شده", default=False)
    admin_note = models.TextField("یادداشت داخلی", blank=True)

    created_at = models.DateTimeField("تاریخ ارسال", auto_now_add=True)

    class Meta:
        verbose_name = "پیام تماس"
        verbose_name_plural = "پیام‌های تماس"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.full_name} — {self.subject}"
