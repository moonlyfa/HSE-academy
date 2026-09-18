"""
مدل‌های آزمون: آزمون، سؤال، گزینه، تلاش و پاسخ.

سه قاعده کل این فایل را توضیح می‌دهند:

**۱. نمره ذخیره می‌شود، نه اینکه هر بار محاسبه شود.**
اگر نمره را هر بار از روی سؤال‌ها حساب می‌کردیم، روزی که مدرس یک گزینه
اشتباه را اصلاح می‌کند، نمره‌ی دانشجویی که ماه پیش امتحان داده هم عوض
می‌شد — و گواهی صادرشده‌اش با کارنامه‌اش نمی‌خواند. نمره، مجموع امتیاز و
قبولی هر سه در لحظه تصحیح، داخل `ExamAttempt` نوشته می‌شوند.

**۲. مجموعه سؤال‌های هر تلاش، همان لحظه شروع قفل می‌شود.**
اگر آزمون از بانک سؤال، ۲۰ سؤال تصادفی برمی‌دارد، آن ۲۰ سؤال باید تا آخر
همان تلاش ثابت بمانند؛ وگرنه با هر بار تازه‌کردن صفحه، سؤال‌ها عوض می‌شوند
و پاسخ‌های قبلی بی‌معنی می‌شوند. ردیف‌های `UserAnswer` در همان لحظه شروع
ساخته می‌شوند و **همان‌ها** یعنی برگه امتحان این دانشجو.

**۳. پاسخ‌ها همان لحظه انتخاب ذخیره می‌شوند، نه فقط موقع «ثبت نهایی».**
امتحان زمان‌دار است؛ اگر مرورگر بسته شود یا اینترنت قطع شود، دانشجو نباید
همه‌چیز را از دست بدهد.
"""

from __future__ import annotations

from datetime import timedelta

from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils import timezone


class Exam(models.Model):
    """
    آزمون پایان دوره.

    هر دوره حداکثر یک آزمون دارد. چند آزمون برای یک دوره یعنی باید
    جایی تصمیم بگیریم «کدامشان ملاک گواهی است» — سؤالی که در نسخه اول
    جوابی جز پیچیدگی ندارد.
    """

    course = models.OneToOneField(
        "courses.Course",
        verbose_name="دوره",
        on_delete=models.CASCADE,
        related_name="exam",
    )

    title = models.CharField("عنوان آزمون", max_length=200, default="آزمون پایان دوره")
    description = models.TextField(
        "توضیح و قوانین",
        blank=True,
        help_text="پیش از شروع آزمون به دانشجو نشان داده می‌شود.",
    )

    # --- قواعد برگزاری ---
    question_count = models.PositiveIntegerField(
        "تعداد سؤال هر آزمون",
        default=0,
        help_text=(
            "صفر یعنی همه سؤال‌های فعال. اگر عددی کمتر از تعداد سؤال‌ها بگذارید، "
            "برای هر دانشجو همان تعداد سؤال تصادفی انتخاب می‌شود."
        ),
    )
    time_limit_minutes = models.PositiveIntegerField(
        "مدت آزمون (دقیقه)",
        default=30,
        help_text="صفر یعنی بدون محدودیت زمانی.",
    )
    pass_score = models.PositiveIntegerField(
        "نمره قبولی (درصد)",
        default=70,
        help_text="دانشجو با این درصد یا بالاتر، قبول می‌شود.",
    )
    max_attempts = models.PositiveIntegerField(
        "حداکثر دفعات شرکت",
        default=3,
        help_text="صفر یعنی بدون محدودیت.",
    )

    # --- نمایش ---
    shuffle_questions = models.BooleanField("ترتیب تصادفی سؤال‌ها", default=True)
    shuffle_options = models.BooleanField("ترتیب تصادفی گزینه‌ها", default=True)
    show_correct_answers = models.BooleanField(
        "نمایش پاسخ درست بعد از آزمون",
        default=True,
        help_text="اگر خاموش باشد، دانشجو فقط نمره‌اش را می‌بیند.",
    )

    require_course_completion = models.BooleanField(
        "نیاز به تکمیل دوره",
        default=False,
        help_text="اگر روشن باشد، تا همه درس‌ها تکمیل نشوند آزمون باز نمی‌شود.",
    )
    is_published = models.BooleanField(
        "منتشر شده",
        default=False,
        help_text="تا وقتی خاموش است، فقط مدیر و مدرس دوره آزمون را می‌بینند.",
    )

    created_at = models.DateTimeField("تاریخ ایجاد", auto_now_add=True)
    updated_at = models.DateTimeField("آخرین بروزرسانی", auto_now=True)

    class Meta:
        verbose_name = "آزمون"
        verbose_name_plural = "آزمون‌ها"

    def __str__(self) -> str:
        return f"{self.title} — {self.course.title}"

    def get_absolute_url(self) -> str:
        return reverse("exams:detail", kwargs={"slug": self.course.slug})

    @property
    def active_questions(self):
        return self.questions.filter(is_active=True).order_by("order", "id")

    @property
    def question_pool_size(self) -> int:
        return self.active_questions.count()

    @property
    def questions_per_attempt(self) -> int:
        """چند سؤال در یک برگه امتحان می‌آید؟"""
        pool = self.question_pool_size
        if not self.question_count:
            return pool
        return min(self.question_count, pool)

    @property
    def has_time_limit(self) -> bool:
        return bool(self.time_limit_minutes)

    @property
    def is_ready(self) -> bool:
        """آزمونی که سؤال ندارد، آزمون نیست."""
        return self.question_pool_size > 0


class QuestionType(models.TextChoices):
    """
    نوع سؤال.

    در نسخه اول فقط سؤال چندگزینه‌ای پیاده شده است. «تشریحی» از همین حالا
    در مدل هست چون تصحیح تشریحی یک رابط جداگانه برای مدرس می‌خواهد و
    اضافه‌کردن بعدیِ آن نباید مدل و مهاجرت را به‌هم بریزد — اما تا آن روز،
    سؤال تشریحی ذخیره نمی‌شود (در `clean` جلویش گرفته می‌شود).
    """

    MULTIPLE_CHOICE = "multiple_choice", "چندگزینه‌ای"
    ESSAY = "essay", "تشریحی (نسخه بعد)"


class Question(models.Model):
    """یک سؤال از بانک سؤال آزمون."""

    exam = models.ForeignKey(
        Exam,
        verbose_name="آزمون",
        on_delete=models.CASCADE,
        related_name="questions",
    )

    text = models.TextField("متن سؤال")
    question_type = models.CharField(
        "نوع سؤال",
        max_length=20,
        choices=QuestionType.choices,
        default=QuestionType.MULTIPLE_CHOICE,
    )
    explanation = models.TextField(
        "توضیح پاسخ",
        blank=True,
        help_text="بعد از آزمون، همراه پاسخ درست به دانشجو نشان داده می‌شود.",
    )
    points = models.PositiveIntegerField("امتیاز", default=1)
    order = models.PositiveIntegerField("ترتیب نمایش", default=0)
    is_active = models.BooleanField(
        "فعال",
        default=True,
        help_text=(
            "سؤالی که دیگر نمی‌خواهید پرسیده شود را غیرفعال کنید، نه اینکه پاکش "
            "کنید؛ پاک کردنش کارنامه‌های قبلی را بی‌معنی می‌کند."
        ),
    )

    created_at = models.DateTimeField("تاریخ ایجاد", auto_now_add=True)
    updated_at = models.DateTimeField("آخرین بروزرسانی", auto_now=True)

    class Meta:
        verbose_name = "سؤال"
        verbose_name_plural = "سؤال‌ها"
        ordering = ["order", "id"]
        indexes = [models.Index(fields=["exam", "order"])]

    def __str__(self) -> str:
        return self.text[:60]

    def clean(self) -> None:
        from django.core.exceptions import ValidationError

        if self.question_type == QuestionType.ESSAY:
            raise ValidationError(
                {
                    "question_type": (
                        "سؤال تشریحی در نسخه فعلی پشتیبانی نمی‌شود؛ تصحیح آن به "
                        "رابط جداگانه‌ای برای مدرس نیاز دارد."
                    )
                }
            )

    @property
    def correct_options(self):
        return self.options.filter(is_correct=True)

    @property
    def is_answerable(self) -> bool:
        """سؤالی که گزینه درست ندارد، قابل تصحیح نیست و در آزمون نمی‌آید."""
        return self.correct_options.exists()


class QuestionOption(models.Model):
    """یک گزینه از گزینه‌های سؤال چندگزینه‌ای."""

    question = models.ForeignKey(
        Question,
        verbose_name="سؤال",
        on_delete=models.CASCADE,
        related_name="options",
    )
    text = models.CharField("متن گزینه", max_length=500)
    is_correct = models.BooleanField("پاسخ درست", default=False)
    order = models.PositiveIntegerField("ترتیب نمایش", default=0)

    class Meta:
        verbose_name = "گزینه"
        verbose_name_plural = "گزینه‌ها"
        ordering = ["order", "id"]

    def __str__(self) -> str:
        return self.text[:60]


class AttemptStatus(models.TextChoices):
    IN_PROGRESS = "in_progress", "در حال انجام"
    FINISHED = "finished", "تصحیح‌شده"


class ExamAttempt(models.Model):
    """
    یک بار شرکت در آزمون.

    نمره و نتیجه قبولی در همین ردیف ذخیره می‌شوند و بعد از آن دیگر تغییر
    نمی‌کنند — حتی اگر سؤال‌ها یا نمره قبولی آزمون بعداً عوض شوند.
    """

    exam = models.ForeignKey(
        Exam,
        verbose_name="آزمون",
        on_delete=models.CASCADE,
        related_name="attempts",
    )
    user = models.ForeignKey(
        "accounts.User",
        verbose_name="دانشجو",
        on_delete=models.CASCADE,
        related_name="exam_attempts",
    )

    status = models.CharField(
        "وضعیت",
        max_length=20,
        choices=AttemptStatus.choices,
        default=AttemptStatus.IN_PROGRESS,
    )

    started_at = models.DateTimeField("زمان شروع", default=timezone.now)
    # مهلت در لحظه شروع محاسبه و ذخیره می‌شود. اگر مدیر وسط آزمون مدت
    # آزمون را عوض کند، مهلت کسی که مشغول است نباید جابه‌جا شود.
    expires_at = models.DateTimeField(
        "پایان مهلت", null=True, blank=True, help_text="خالی یعنی آزمون بدون زمان است."
    )
    finished_at = models.DateTimeField("زمان تصحیح", null=True, blank=True)

    # --- نتیجه (عکس‌برداری‌شده در لحظه تصحیح) ---
    score = models.PositiveIntegerField("نمره (درصد)", default=0)
    earned_points = models.PositiveIntegerField("امتیاز کسب‌شده", default=0)
    total_points = models.PositiveIntegerField("امتیاز کل", default=0)
    pass_score = models.PositiveIntegerField("نمره قبولی در زمان آزمون", default=0)
    is_passed = models.BooleanField("قبول", default=False)
    auto_submitted = models.BooleanField(
        "ثبت خودکار (پایان زمان)",
        default=False,
        help_text="یعنی دانشجو خودش ثبت نکرد و آزمون با پایان مهلت بسته شد.",
    )

    class Meta:
        verbose_name = "تلاش آزمون"
        verbose_name_plural = "تلاش‌های آزمون"
        ordering = ["-started_at"]
        indexes = [
            models.Index(fields=["user", "exam"]),
            models.Index(fields=["exam", "status"]),
        ]

    def __str__(self) -> str:
        return f"{self.user} — {self.exam.title}"

    def get_absolute_url(self) -> str:
        return reverse("exams:result", kwargs={"pk": self.pk})

    @property
    def is_finished(self) -> bool:
        return self.status == AttemptStatus.FINISHED

    @property
    def is_expired(self) -> bool:
        """مهلت تمام شده اما هنوز تصحیح نشده است."""
        return bool(
            not self.is_finished and self.expires_at and timezone.now() > self.expires_at
        )

    @property
    def remaining_seconds(self) -> int | None:
        """چند ثانیه تا پایان مهلت؟ None یعنی آزمون بدون زمان است."""
        if not self.expires_at:
            return None
        remaining = (self.expires_at - timezone.now()).total_seconds()
        return max(int(remaining), 0)

    @property
    def deadline_with_grace(self):
        """
        مهلت به‌علاوه چند ثانیه ارفاق.

        ثبت نهایی دانشجو چند ثانیه در راه است؛ بدون این ارفاق، پاسخ کسی
        که دقیقاً در ثانیه آخر دکمه را زده، دور ریخته می‌شود.
        """
        if not self.expires_at:
            return None
        return self.expires_at + timedelta(seconds=settings.EXAM_SUBMIT_GRACE_SECONDS)

    @property
    def accepts_answers(self) -> bool:
        if self.is_finished:
            return False
        if not self.expires_at:
            return True
        return timezone.now() <= self.deadline_with_grace

    @property
    def duration_minutes(self) -> int:
        end = self.finished_at or timezone.now()
        return max(int((end - self.started_at).total_seconds() // 60), 0)

    @property
    def answered_count(self) -> int:
        return self.answers.filter(selected_option__isnull=False).count()

    @property
    def question_count(self) -> int:
        return self.answers.count()

    @property
    def correct_count(self) -> int:
        return self.answers.filter(is_correct=True).count()


class UserAnswer(models.Model):
    """
    یک ردیف از برگه امتحان: یک سؤال و پاسخی که دانشجو داده است.

    ردیف‌ها در لحظه شروع آزمون ساخته می‌شوند (با پاسخ خالی) و همان‌ها
    مشخص می‌کنند این دانشجو چه سؤال‌هایی دارد و به چه ترتیبی.

    امتیاز سؤال هم اینجا عکس‌برداری می‌شود: اگر بعداً امتیاز یک سؤال از ۱
    به ۲ تغییر کند، کارنامه‌های قبلی نباید جابه‌جا شوند.
    """

    attempt = models.ForeignKey(
        ExamAttempt,
        verbose_name="تلاش",
        on_delete=models.CASCADE,
        related_name="answers",
    )
    question = models.ForeignKey(
        Question,
        verbose_name="سؤال",
        # پاک‌کردن سؤالی که کسی به آن پاسخ داده، کارنامه‌اش را ناقص
        # می‌کند. برای کنار گذاشتن یک سؤال، آن را غیرفعال کنید.
        on_delete=models.PROTECT,
        related_name="user_answers",
    )
    selected_option = models.ForeignKey(
        QuestionOption,
        verbose_name="گزینه انتخابی",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="user_answers",
    )
    text_answer = models.TextField(
        "پاسخ تشریحی",
        blank=True,
        help_text="برای سؤال‌های تشریحی نسخه‌های بعد.",
    )

    order = models.PositiveIntegerField("ترتیب در برگه", default=0)
    points = models.PositiveIntegerField("امتیاز سؤال", default=1)
    earned_points = models.PositiveIntegerField("امتیاز کسب‌شده", default=0)
    is_correct = models.BooleanField("درست", default=False)

    answered_at = models.DateTimeField("زمان پاسخ", null=True, blank=True)

    class Meta:
        verbose_name = "پاسخ دانشجو"
        verbose_name_plural = "پاسخ‌های دانشجو"
        ordering = ["order", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["attempt", "question"], name="unique_answer_per_question"
            )
        ]

    def __str__(self) -> str:
        return f"{self.attempt_id} — {self.question_id}"

    @property
    def is_answered(self) -> bool:
        return self.selected_option_id is not None
