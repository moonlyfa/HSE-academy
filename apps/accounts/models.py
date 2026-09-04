"""
مدل کاربر سفارشی پروژه.

چرا از همین فاز ۱؟
Django اجازه نمی‌دهد بعد از اجرای اولین migrate، مدل کاربر را به‌راحتی عوض کنید.
تغییر AUTH_USER_MODEL در پروژه‌ای که دیتابیس دارد یعنی پاک کردن دیتابیس یا
نوشتن Migration دستی و پیچیده. پس مدل کاربر را قبل از اولین migrate می‌سازیم.

در فاز ۳ به این اپ فرم‌ها، Viewها و صفحات ورود/ثبت‌نام اضافه می‌شود و در
فاز ۴ و ۵ مدل‌های OTP و IdentityVerification به آن اضافه می‌شوند.
"""

from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin
from django.db import models
from django.urls import reverse
from django.utils import timezone
from django.utils.text import slugify

from .managers import UserManager
from .validators import validate_iranian_mobile, validate_national_code


class UserRole(models.TextChoices):
    """
    نقش کاربر.

    این فیلد فقط یک «برچسب» است تا در پنل و منطق برنامه سریع بفهمیم کاربر
    چه‌کاره است. کنترل دسترسی واقعی با Group و Permission استاندارد Django
    انجام می‌شود (فاز ۳)، نه با مقایسه رشته‌ای این فیلد.
    """

    SUPER_ADMIN = "super_admin", "مدیر ارشد"
    ADMIN = "admin", "مدیر"
    INSTRUCTOR = "instructor", "مدرس"
    STUDENT = "student", "دانشجو"
    FINANCE = "finance", "مالی"
    SUPPORT = "support", "پشتیبانی"
    CONTENT_MANAGER = "content_manager", "مدیر محتوا"


class User(AbstractBaseUser, PermissionsMixin):
    """
    کاربر سایت.

    AbstractBaseUser: امکانات پایه احراز هویت (رمز هش‌شده، last_login) را می‌دهد.
    PermissionsMixin: سیستم گروه و دسترسی استاندارد Django را اضافه می‌کند.
    """

    mobile = models.CharField(
        "شماره موبایل",
        max_length=11,
        unique=True,
        validators=[validate_iranian_mobile],
        help_text="شماره موبایل به شکل 09xxxxxxxxx — همین شماره نام کاربری شماست.",
    )
    national_code = models.CharField(
        "کد ملی",
        max_length=10,
        unique=True,
        null=True,
        blank=True,
        validators=[validate_national_code],
        help_text="تا زمان تکمیل احراز هویت می‌تواند خالی باشد.",
    )
    first_name = models.CharField("نام", max_length=50, blank=True)
    last_name = models.CharField("نام خانوادگی", max_length=50, blank=True)
    email = models.EmailField("ایمیل", blank=True)

    # وضعیت احراز هویت
    is_mobile_verified = models.BooleanField(
        "موبایل تأیید شده",
        default=False,
        help_text="بعد از تأیید موفق کد پیامکی True می‌شود.",
    )
    is_identity_verified = models.BooleanField(
        "هویت تأیید شده",
        default=False,
        help_text="بعد از تطبیق موفق شماره موبایل و کد ملی True می‌شود.",
    )

    # اشتراک ویژه
    is_vip = models.BooleanField("کاربر ویژه", default=False)
    vip_expires_at = models.DateTimeField("انقضای اشتراک ویژه", null=True, blank=True)

    role = models.CharField(
        "نقش",
        max_length=20,
        choices=UserRole.choices,
        default=UserRole.STUDENT,
    )

    # فیلدهای لازم برای پنل مدیریت Django
    is_active = models.BooleanField("فعال", default=True)
    is_staff = models.BooleanField(
        "دسترسی به پنل مدیریت",
        default=False,
        help_text="اگر فعال باشد، کاربر می‌تواند وارد پنل مدیریت شود.",
    )

    created_at = models.DateTimeField("تاریخ ثبت‌نام", auto_now_add=True)
    updated_at = models.DateTimeField("آخرین بروزرسانی", auto_now=True)

    objects = UserManager()

    # نام کاربری سایت، شماره موبایل است.
    USERNAME_FIELD = "mobile"
    # فیلدهایی که هنگام createsuperuser علاوه بر USERNAME_FIELD پرسیده می‌شوند.
    REQUIRED_FIELDS: list[str] = []

    class Meta:
        verbose_name = "کاربر"
        verbose_name_plural = "کاربران"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return self.full_name or self.mobile

    @property
    def full_name(self) -> str:
        """نام کامل کاربر؛ اگر نام ثبت نشده باشد رشته خالی برمی‌گرداند."""
        return f"{self.first_name} {self.last_name}".strip()

    def get_full_name(self) -> str:
        """Django در بعضی قسمت‌ها (مثل پنل ادمین) این متد را صدا می‌زند."""
        return self.full_name or self.mobile

    def get_short_name(self) -> str:
        return self.first_name or self.mobile

    @property
    def masked_mobile(self) -> str:
        """
        شماره موبایل به شکل ماسک‌شده: 0912***4567

        در صفحه استعلام گواهی و هر جای عمومی دیگر، هرگز شماره کامل نمایش داده نمی‌شود.
        """
        if len(self.mobile) != 11:
            return self.mobile
        return f"{self.mobile[:4]}***{self.mobile[-4:]}"

    @property
    def has_active_vip(self) -> bool:
        """آیا اشتراک ویژه کاربر هم‌اکنون معتبر است؟"""
        if not self.is_vip:
            return False
        if self.vip_expires_at is None:
            return True
        return self.vip_expires_at > timezone.now()

    @property
    def is_fully_verified(self) -> bool:
        """کاربری که هم موبایل و هم هویتش تأیید شده است."""
        return self.is_mobile_verified and self.is_identity_verified


class InstructorProfile(models.Model):
    """
    پروفایل مدرس.

    چرا جدا از User؟ چون فقط بخش کوچکی از کاربران مدرس هستند و بی‌دلیل
    جدول کاربران را با فیلدهای بیوگرافی و عکس سنگین نمی‌کنیم.
    """

    user = models.OneToOneField(
        "accounts.User",
        verbose_name="کاربر",
        on_delete=models.CASCADE,
        related_name="instructor_profile",
        null=True,
        blank=True,
        help_text="اگر مدرس حساب کاربری دارد، اینجا وصل کنید.",
    )

    display_name = models.CharField("نام نمایشی", max_length=120)
    slug = models.SlugField(
        "نشانی یکتا (اسلاگ)",
        max_length=140,
        unique=True,
        allow_unicode=True,
        blank=True,
        help_text="در آدرس صفحه مدرس استفاده می‌شود. خالی بگذارید تا خودکار ساخته شود.",
    )
    specialty = models.CharField(
        "تخصص",
        max_length=150,
        blank=True,
        help_text="مثلاً «کارشناس ارشد HSE، مدرس ارزیابی ریسک»",
    )
    bio = models.TextField("بیوگرافی", blank=True)
    avatar = models.ImageField("عکس", upload_to="instructors/", blank=True, null=True)

    linkedin_url = models.URLField("لینکدین", blank=True)

    is_active = models.BooleanField("فعال", default=True)
    show_on_homepage = models.BooleanField("نمایش در صفحه اصلی", default=True)
    order = models.PositiveIntegerField("ترتیب نمایش", default=0)

    created_at = models.DateTimeField("تاریخ ایجاد", auto_now_add=True)
    updated_at = models.DateTimeField("آخرین بروزرسانی", auto_now=True)

    class Meta:
        verbose_name = "مدرس"
        verbose_name_plural = "مدرسان"
        ordering = ["order", "display_name"]

    def __str__(self) -> str:
        return self.display_name

    def save(self, *args, **kwargs):
        """
        اگر ادمین اسلاگ را خالی گذاشت، از روی نام مدرس ساخته می‌شود.

        allow_unicode=True یعنی حروف فارسی هم در آدرس مجازند؛ اگر نام
        کاملاً از کاراکترهایی باشد که اسلاگ نمی‌شوند، به شناسه عددی
        برمی‌گردیم تا هیچ‌وقت اسلاگ خالی ذخیره نشود.
        """
        if not self.slug:
            base = slugify(self.display_name, allow_unicode=True) or "instructor"
            candidate = base
            counter = 2
            while (
                InstructorProfile.objects.filter(slug=candidate)
                .exclude(pk=self.pk)
                .exists()
            ):
                candidate = f"{base}-{counter}"
                counter += 1
            self.slug = candidate
        super().save(*args, **kwargs)

    def get_absolute_url(self) -> str:
        return reverse("core:instructor_detail", kwargs={"slug": self.slug})

    @property
    def published_course_count(self) -> int:
        return self.courses.filter(is_published=True).count()


class OtpPurpose(models.TextChoices):
    """
    هدف هر کد یکبارمصرف.

    چرا هدف را ذخیره می‌کنیم؟ تا کدی که برای «بازیابی رمز» فرستاده شده،
    نتواند برای «ثبت‌نام» استفاده شود. هر کد فقط برای همان کاری معتبر است
    که برایش ساخته شده.
    """

    REGISTER = "register", "ثبت‌نام"
    PASSWORD_RESET = "password_reset", "بازیابی رمز عبور"
    VERIFY_MOBILE = "verify_mobile", "تأیید شماره موبایل"


class OtpCode(models.Model):
    """
    کد یکبارمصرف پیامکی.

    قانون طلایی: کد خام هرگز در دیتابیس ذخیره نمی‌شود — فقط اثر انگشت
    رمزنگاری‌شده آن. حتی اگر کسی به دیتابیس دسترسی پیدا کند، نمی‌تواند
    کدهای فعال کاربران را بخواند.
    """

    mobile = models.CharField("شماره موبایل", max_length=11, db_index=True)
    purpose = models.CharField("هدف", max_length=20, choices=OtpPurpose.choices)

    code_hash = models.CharField(
        "اثر انگشت کد",
        max_length=128,
        help_text="کد خام ذخیره نمی‌شود؛ فقط نسخه رمزنگاری‌شده آن.",
    )

    attempts = models.PositiveSmallIntegerField("تعداد تلاش برای تأیید", default=0)

    created_at = models.DateTimeField("زمان ارسال", auto_now_add=True)
    expires_at = models.DateTimeField("زمان انقضا")
    used_at = models.DateTimeField("زمان استفاده", null=True, blank=True)

    ip_address = models.GenericIPAddressField("آدرس IP", null=True, blank=True)

    class Meta:
        verbose_name = "کد یکبارمصرف"
        verbose_name_plural = "کدهای یکبارمصرف"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["mobile", "purpose", "-created_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.mobile} — {self.get_purpose_display()}"

    @property
    def is_expired(self) -> bool:
        return timezone.now() >= self.expires_at

    @property
    def is_used(self) -> bool:
        return self.used_at is not None

    @property
    def is_usable(self) -> bool:
        """کد فقط وقتی قابل استفاده است که منقضی نشده، مصرف نشده و تلاش‌ها تمام نشده باشد."""
        from django.conf import settings

        return (
            not self.is_used
            and not self.is_expired
            and self.attempts < settings.OTP_MAX_ATTEMPTS
        )

    @property
    def seconds_remaining(self) -> int:
        """چند ثانیه تا انقضای کد باقی مانده — برای نمایش شمارنده به کاربر."""
        delta = (self.expires_at - timezone.now()).total_seconds()
        return max(int(delta), 0)

    def mark_used(self) -> None:
        self.used_at = timezone.now()
        self.save(update_fields=["used_at"])


class IdentityStatus(models.TextChoices):
    """نتیجه یک درخواست استعلام هویت."""

    MATCHED = "matched", "تطبیق داشت"
    NOT_MATCHED = "not_matched", "تطبیق نداشت"
    FAILED = "failed", "خطای سرویس"


class IdentityVerification(models.Model):
    """
    سابقه هر بار استعلام تطبیق شماره موبایل و کد ملی.

    چرا سابقه نگه می‌داریم؟
      ۱. هر استعلام هزینه دارد؛ باید بدانیم چند بار و برای چه کسی خرج شده.
      ۲. اگر کاربری ادعا کرد هویتش تأیید نشده، باید بتوانیم بررسی کنیم.
      ۳. کد رهگیری سرویس برای پیگیری با ارائه‌دهنده لازم است.

    نکته امنیتی: کد ملی داده شخصی حساس است. در پنل مدیریت ماسک‌شده نمایش
    داده می‌شود و هرگز در صفحات عمومی سایت دیده نمی‌شود.
    """

    user = models.ForeignKey(
        "accounts.User",
        verbose_name="کاربر",
        on_delete=models.CASCADE,
        related_name="identity_verifications",
        null=True,
        blank=True,
        help_text="هنگام ثبت‌نام هنوز کاربری ساخته نشده، پس می‌تواند خالی باشد.",
    )

    mobile = models.CharField("شماره موبایل", max_length=11, db_index=True)
    national_code = models.CharField("کد ملی", max_length=10)

    status = models.CharField("وضعیت", max_length=20, choices=IdentityStatus.choices)
    provider = models.CharField("سرویس‌دهنده", max_length=50)
    tracking_code = models.CharField("کد رهگیری", max_length=100, blank=True)
    message = models.CharField("پیام سرویس", max_length=300, blank=True)

    raw_response = models.JSONField(
        "پاسخ خام سرویس",
        default=dict,
        blank=True,
        help_text="برای پیگیری فنی با ارائه‌دهنده سرویس نگه داشته می‌شود.",
    )

    ip_address = models.GenericIPAddressField("آدرس IP", null=True, blank=True)
    created_at = models.DateTimeField("زمان استعلام", auto_now_add=True)

    class Meta:
        verbose_name = "استعلام هویت"
        verbose_name_plural = "استعلام‌های هویت"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["mobile", "-created_at"]),
            models.Index(fields=["status"]),
        ]

    def __str__(self) -> str:
        return f"{self.masked_mobile} — {self.get_status_display()}"

    @property
    def masked_mobile(self) -> str:
        if len(self.mobile) != 11:
            return self.mobile
        return f"{self.mobile[:4]}***{self.mobile[-4:]}"

    @property
    def masked_national_code(self) -> str:
        """کد ملی ماسک‌شده: 004***9481"""
        if len(self.national_code) != 10:
            return "نامعتبر"
        return f"{self.national_code[:3]}***{self.national_code[-4:]}"

    @property
    def is_matched(self) -> bool:
        return self.status == IdentityStatus.MATCHED
