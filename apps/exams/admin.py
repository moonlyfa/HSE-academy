"""
پنل مدیریت آزمون.

چیدمان بر اساس کاری است که مدرس واقعاً انجام می‌دهد: یک آزمون می‌سازد،
سؤال‌ها را یکی‌یکی وارد می‌کند، و بعد کارنامه‌ها را نگاه می‌کند. برای
همین گزینه‌ها داخل صفحه سؤال هستند و کارنامه‌ها فقط خواندنی‌اند.
"""

from django.contrib import admin
from django.utils.html import format_html

from .models import (
    AttemptStatus,
    Exam,
    ExamAttempt,
    Question,
    QuestionOption,
    UserAnswer,
)


class QuestionOptionInline(admin.TabularInline):
    model = QuestionOption
    extra = 4
    fields = ("text", "is_correct", "order")
    ordering = ("order", "id")


class QuestionInline(admin.TabularInline):
    """
    فهرست سؤال‌ها روی صفحه آزمون — فقط برای مرور و ترتیب‌دهی.

    گزینه‌ها اینجا نمی‌آیند چون جدولِ تودرتو در پنل جنگو خوانا نیست؛
    برای ویرایش گزینه‌ها، لینک «ویرایش گزینه‌ها» به صفحه خود سؤال می‌رود.
    """

    model = Question
    extra = 0
    fields = ("text", "points", "order", "is_active", "option_summary")
    readonly_fields = ("option_summary",)
    ordering = ("order", "id")
    show_change_link = True

    @admin.display(description="گزینه‌ها")
    def option_summary(self, obj: Question) -> str:
        if not obj.pk:
            return "ابتدا سؤال را ذخیره کنید."
        total = obj.options.count()
        if not total:
            return "بدون گزینه"
        if not obj.is_answerable:
            return format_html('<span style="color:#c0392b">پاسخ درست مشخص نشده</span>')
        return f"{total} گزینه"


@admin.register(Exam)
class ExamAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "course",
        "question_pool_display",
        "questions_per_attempt",
        "pass_score",
        "time_limit_minutes",
        "is_published",
    )
    list_editable = ("is_published",)
    list_filter = ("is_published", "require_course_completion")
    search_fields = ("title", "description", "course__title")
    autocomplete_fields = ("course",)
    readonly_fields = ("created_at", "updated_at")
    inlines = (QuestionInline,)

    fieldsets = (
        ("آزمون", {"fields": ("course", "title", "description")}),
        (
            "قواعد برگزاری",
            {
                "description": (
                    "«تعداد سؤال هر آزمون» را کمتر از تعداد سؤال‌های بانک بگذارید تا "
                    "هر دانشجو سؤال‌های متفاوتی بگیرد."
                ),
                "fields": (
                    "question_count",
                    "time_limit_minutes",
                    "pass_score",
                    "max_attempts",
                    "require_course_completion",
                ),
            },
        ),
        (
            "نمایش",
            {"fields": ("shuffle_questions", "shuffle_options", "show_correct_answers")},
        ),
        ("وضعیت", {"fields": ("is_published", "created_at", "updated_at")}),
    )

    @admin.display(description="بانک سؤال")
    def question_pool_display(self, obj: Exam):
        pool = obj.question_pool_size
        if not pool:
            return format_html('<span style="color:#c0392b">بدون سؤال</span>')
        return pool

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("course")


@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display = ("short_text", "exam", "points", "order", "answer_status", "is_active")
    list_editable = ("points", "order", "is_active")
    list_filter = ("is_active", "exam")
    search_fields = ("text", "explanation")
    autocomplete_fields = ("exam",)
    inlines = (QuestionOptionInline,)
    readonly_fields = ("created_at", "updated_at")

    fieldsets = (
        ("سؤال", {"fields": ("exam", "text", "question_type", "points", "order")}),
        (
            "توضیح پاسخ",
            {
                "description": "بعد از آزمون همراه پاسخ درست نمایش داده می‌شود.",
                "fields": ("explanation",),
            },
        ),
        ("وضعیت", {"fields": ("is_active", "created_at", "updated_at")}),
    )

    @admin.display(description="متن سؤال")
    def short_text(self, obj: Question) -> str:
        return obj.text[:70]

    @admin.display(description="پاسخ درست")
    def answer_status(self, obj: Question):
        if obj.is_answerable:
            return "مشخص شده"
        # سؤال بی‌پاسخ‌درست در آزمون نمی‌آید؛ مدرس باید ببیندش.
        return format_html('<span style="color:#c0392b">مشخص نشده</span>')

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("exam")


class UserAnswerInline(admin.TabularInline):
    model = UserAnswer
    extra = 0
    can_delete = False
    fields = ("order", "question", "selected_option", "is_correct", "earned_points")
    readonly_fields = fields

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(ExamAttempt)
class ExamAttemptAdmin(admin.ModelAdmin):
    """
    کارنامه‌ها فقط خواندنی‌اند.

    دست‌بردن در نمره‌ی ثبت‌شده یعنی از بین بردن همان چیزی که گواهی به آن
    استناد می‌کند. اگر آزمونی باید دوباره گرفته شود، تلاش تازه‌ای برگزار
    می‌شود — کارنامه قبلی پاک نمی‌شود.
    """

    list_display = (
        "user",
        "exam",
        "score_badge",
        "status",
        "started_at",
        "duration_display",
        "auto_submitted",
    )
    list_filter = ("status", "is_passed", "auto_submitted", "exam")
    search_fields = ("user__mobile", "user__first_name", "user__last_name", "exam__title")
    date_hierarchy = "started_at"
    ordering = ("-started_at",)
    list_per_page = 50
    inlines = (UserAnswerInline,)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    @admin.display(description="نمره", ordering="score")
    def score_badge(self, obj: ExamAttempt):
        if obj.status != AttemptStatus.FINISHED:
            return "—"
        color = "#1e8449" if obj.is_passed else "#c0392b"
        label = "قبول" if obj.is_passed else "مردود"
        return format_html(
            '<span style="color:{};font-weight:600">{}٪ ({})</span>',
            color,
            obj.score,
            label,
        )

    @admin.display(description="مدت")
    def duration_display(self, obj: ExamAttempt) -> str:
        if not obj.finished_at:
            return "—"
        return f"{obj.duration_minutes} دقیقه"

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("user", "exam", "exam__course")
