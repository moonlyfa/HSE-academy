"""
مدل گواهی پایان دوره.

گواهی، بیرونی‌ترین خروجی این سایت است: کاغذی که دانشجو به کارفرما نشان
می‌دهد و کارفرما باید بتواند اصالتش را بررسی کند. سه تصمیم، شکل این مدل
را ساخته‌اند:

**۱. کد گواهی و توکن استعلام دو چیز جدا هستند.**
کد (`HSE-1404-00123`) برای نمایش به آدم‌هاست: روی گواهی چاپ می‌شود و
تلفنی خوانده می‌شود، پس باید کوتاه و ترتیبی باشد. اما چیزی که کوتاه و
ترتیبی است را می‌شود یکی‌یکی حدس زد؛ اگر لینک QR هم همین بود، هرکسی
می‌توانست با شمردن، گواهی همه دانشجوها را بیرون بکشد. پس لینک QR روی یک
**توکن تصادفی** ساخته می‌شود.

**۲. اطلاعات روی گواهی عکس‌برداری می‌شوند.**
نام دانشجو، عنوان دوره، مدت و نمره در لحظه صدور داخل خود گواهی نوشته
می‌شوند. اگر بعداً عنوان دوره عوض شود یا دانشجو نامش را در پروفایل
اصلاح کند، گواهیِ چاپ‌شده در دست کارفرما با آنچه سایت نشان می‌دهد
نمی‌خواند — و همان یک تفاوت، اصالت گواهی را زیر سؤال می‌برد.

**۳. گواهی باطل می‌شود، پاک نمی‌شود.**
اگر گواهی‌ای اشتباه صادر شده باشد، حذفش یعنی صفحه استعلام می‌گوید «چنین
گواهی‌ای وجود ندارد» — که با «این گواهی باطل شده است» زمین تا آسمان فرق
دارد.
"""

from __future__ import annotations

import secrets

from django.db import models
from django.urls import reverse
from django.utils import timezone

from apps.core.jalali import gregorian_to_jalali

# طول توکن استعلام. ۲۲ کاراکتر urlsafe یعنی حدس‌زدنش عملاً ممکن نیست.
VERIFICATION_TOKEN_BYTES = 16
CERTIFICATE_CODE_PREFIX = "HSE"


def generate_verification_token() -> str:
    return secrets.token_urlsafe(VERIFICATION_TOKEN_BYTES)


def build_certificate_code(year: int, serial: int) -> str:
    """کد خوانا و ترتیبی گواهی: HSE-1404-00123"""
    return f"{CERTIFICATE_CODE_PREFIX}-{year}-{serial:05d}"


class CertificateStatus(models.TextChoices):
    ACTIVE = "active", "معتبر"
    REVOKED = "revoked", "باطل‌شده"


class CertificateQuerySet(models.QuerySet):
    def active(self):
        return self.filter(status=CertificateStatus.ACTIVE)


class Certificate(models.Model):
    """گواهی پایان یک دوره برای یک دانشجو."""

    user = models.ForeignKey(
        "accounts.User",
        verbose_name="دانشجو",
        on_delete=models.CASCADE,
        related_name="certificates",
    )
    course = models.ForeignKey(
        "courses.Course",
        verbose_name="دوره",
        # گواهی صادرشده نباید با حذف دوره از بین برود؛ دوره‌ای که گواهی
        # دارد اصلاً نباید حذف شود.
        on_delete=models.PROTECT,
        related_name="certificates",
    )
    enrollment = models.ForeignKey(
        "courses.Enrollment",
        verbose_name="ثبت‌نام",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="certificates",
    )
    exam_attempt = models.ForeignKey(
        "exams.ExamAttempt",
        verbose_name="کارنامه آزمون",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="certificates",
        help_text="اگر دوره آزمون داشته، کارنامه‌ای که مبنای صدور بوده.",
    )

    certificate_code = models.CharField(
        "کد گواهی",
        max_length=30,
        unique=True,
        help_text="کدی که روی گواهی چاپ می‌شود و کاربر آن را می‌بیند.",
    )
    verification_token = models.CharField(
        "توکن استعلام",
        max_length=64,
        unique=True,
        default=generate_verification_token,
        help_text="آدرس داخل QR روی همین ساخته می‌شود، نه روی کد گواهی.",
    )

    # --- عکس‌برداری در لحظه صدور ---
    holder_name = models.CharField("نام دارنده", max_length=150)
    course_title = models.CharField("عنوان دوره", max_length=200)
    course_hours = models.PositiveIntegerField("مدت دوره (ساعت)", default=0)
    instructor_name = models.CharField("نام مدرس", max_length=150, blank=True)
    score = models.PositiveIntegerField(
        "نمره آزمون", null=True, blank=True, help_text="خالی یعنی دوره آزمون نداشته."
    )

    issued_at = models.DateTimeField("تاریخ صدور", default=timezone.now)
    valid_until = models.DateField(
        "اعتبار تا",
        null=True,
        blank=True,
        help_text="خالی یعنی گواهی تاریخ انقضا ندارد.",
    )

    status = models.CharField(
        "وضعیت",
        max_length=20,
        choices=CertificateStatus.choices,
        default=CertificateStatus.ACTIVE,
    )
    revoke_reason = models.CharField("علت ابطال", max_length=300, blank=True)

    created_at = models.DateTimeField("تاریخ ایجاد", auto_now_add=True)
    updated_at = models.DateTimeField("آخرین تغییر", auto_now=True)

    objects = CertificateQuerySet.as_manager()

    class Meta:
        verbose_name = "گواهی"
        verbose_name_plural = "گواهی‌ها"
        ordering = ["-issued_at"]
        constraints = [
            # یک دانشجو در یک دوره یک گواهی دارد. اگر دوباره دوره را
            # بگذراند، همان گواهی معتبر است نه دو کاغذ موازی با دو کد.
            models.UniqueConstraint(
                fields=["user", "course"], name="unique_certificate_per_user_course"
            )
        ]
        indexes = [
            models.Index(fields=["certificate_code"]),
            models.Index(fields=["user", "status"]),
        ]

    def __str__(self) -> str:
        return f"{self.certificate_code} — {self.holder_name}"

    def get_absolute_url(self) -> str:
        return reverse("certificates:detail", kwargs={"code": self.certificate_code})

    def get_pdf_url(self) -> str:
        return reverse("certificates:pdf", kwargs={"code": self.certificate_code})

    def get_verification_url(self) -> str:
        """
        آدرس استعلام عمومی — همان چیزی که داخل QR می‌رود.

        روی توکن ساخته می‌شود نه کد گواهی، تا کسی نتواند با شمردن کدها
        گواهی دیگران را بیرون بکشد.
        """
        url = reverse("core:certificate_verify")
        return f"{url}?token={self.verification_token}"

    @property
    def is_expired(self) -> bool:
        return bool(self.valid_until and timezone.localdate() > self.valid_until)

    @property
    def is_revoked(self) -> bool:
        return self.status == CertificateStatus.REVOKED

    @property
    def is_valid(self) -> bool:
        """گواهی معتبر است؟ (باطل نشده و منقضی نشده)"""
        return self.status == CertificateStatus.ACTIVE and not self.is_expired

    @property
    def status_label(self) -> str:
        if self.is_revoked:
            return "باطل‌شده"
        if self.is_expired:
            return "منقضی‌شده"
        return "معتبر"

    @property
    def issued_jalali(self) -> tuple[int, int, int]:
        """تاریخ صدور به شمسی — برای چاپ روی گواهی."""
        issued = timezone.localtime(self.issued_at)
        return gregorian_to_jalali(issued.year, issued.month, issued.day)
