"""پنل مدیریت دسته‌بندی‌ها و دوره‌ها."""

from django.contrib import admin
from django.urls import reverse
from django.utils import timezone
from django.utils.html import format_html

from .models import (
    Course,
    CourseCategory,
    Enrollment,
    EnrollmentStatus,
    Lesson,
    LessonAttachment,
    LessonProgress,
    OnlineSession,
    OnlineSessionStatus,
    Section,
    online_courses_enabled,
)


class OnlineOnlyAdminMixin:
    """
    بخش‌هایی از پنل که فقط به دوره‌های آنلاین مربوط‌اند.

    وقتی ONLINE_COURSES_ENABLED خاموش است، این بخش‌ها از فهرست پنل مدیریت
    پنهان می‌شوند تا مدیر با گزینه‌هایی که فعلاً کاری نمی‌کنند سردرگم نشود.
    داده‌ها و خود صفحه‌ها سر جایشان‌اند؛ با روشن شدن کلید برمی‌گردند.
    """

    def has_module_permission(self, request) -> bool:
        return online_courses_enabled() and super().has_module_permission(request)


@admin.register(CourseCategory)
class CourseCategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "parent", "course_count", "show_on_homepage", "is_active", "order")
    list_editable = ("show_on_homepage", "is_active", "order")
    list_filter = ("is_active", "show_on_homepage", "parent")
    search_fields = ("name", "description")
    # اسلاگ به‌صورت خودکار از روی نام پر می‌شود.
    prepopulated_fields = {"slug": ("name",)}
    ordering = ("order", "name")
    list_per_page = 30

    fieldsets = (
        ("اطلاعات اصلی", {"fields": ("name", "slug", "description", "parent")}),
        ("نمایش", {"fields": ("icon", "image", "show_on_homepage", "is_active", "order")}),
        ("سئو", {"fields": ("meta_title", "meta_description"), "classes": ("collapse",)}),
    )

    @admin.display(description="تعداد دوره")
    def course_count(self, obj: CourseCategory) -> int:
        return obj.published_course_count


class SectionInline(admin.TabularInline):
    """
    فصل‌های دوره، داخل صفحه ویرایش خود دوره.

    چرا فقط فصل‌ها اینجا هستند و درس‌ها نه؟
    پنل مدیریت جنگو از Inline تودرتو (فصل داخل دوره، درس داخل فصل) پشتیبانی
    نمی‌کند. پس ساختار این‌طور است: در صفحه دوره فصل‌ها را می‌سازید، و با
    زدن روی هر فصل، درس‌های آن را وارد می‌کنید.
    """

    model = Section
    extra = 1
    fields = ("title", "order", "is_published", "lesson_count_display", "edit_link")
    readonly_fields = ("lesson_count_display", "edit_link")
    ordering = ("order", "id")

    @admin.display(description="تعداد درس")
    def lesson_count_display(self, obj: Section) -> str:
        return str(obj.lesson_count) if obj.pk else "—"

    @admin.display(description="درس‌های این فصل")
    def edit_link(self, obj: Section):
        if not obj.pk:
            return "ابتدا فصل را ذخیره کنید."
        url = reverse("admin:courses_section_change", args=[obj.pk])
        return format_html('<a href="{}">افزودن و ویرایش درس‌ها</a>', url)


class LessonInline(admin.TabularInline):
    """درس‌های یک فصل، داخل صفحه ویرایش همان فصل."""

    model = Lesson
    extra = 1
    fields = (
        "title",
        "lesson_type",
        "order",
        "duration_minutes",
        "is_free_preview",
        "is_published",
        "edit_link",
    )
    readonly_fields = ("edit_link",)
    ordering = ("order", "id")

    @admin.display(description="محتوا و فایل‌ها")
    def edit_link(self, obj: Lesson):
        if not obj.pk:
            return "ابتدا درس را ذخیره کنید."
        url = reverse("admin:courses_lesson_change", args=[obj.pk])
        return format_html('<a href="{}">ویرایش محتوا</a>', url)


class OnlineSessionInline(admin.TabularInline):
    """
    برنامه کلاس‌های آنلاین، روی همان صفحه ویرایش دوره.

    چیدن جلسه‌ها کنار خود دوره است چون مدیر معمولاً هر هفته یک ردیف
    اضافه می‌کند و نباید برای این کار صفحه عوض کند.
    """

    model = OnlineSession
    extra = 0
    fields = ("title", "starts_at", "duration_minutes", "meeting_url", "status")
    ordering = ("starts_at",)
    show_change_link = True


class LessonAttachmentInline(admin.TabularInline):
    model = LessonAttachment
    extra = 1
    fields = ("title", "file", "order")
    ordering = ("order", "id")


@admin.register(Section)
class SectionAdmin(OnlineOnlyAdminMixin, admin.ModelAdmin):
    list_display = ("title", "course", "order", "lesson_count_display", "is_published")
    list_filter = ("is_published", "course")
    search_fields = ("title", "course__title")
    autocomplete_fields = ("course",)
    ordering = ("course", "order")
    inlines = (LessonInline,)

    @admin.display(description="تعداد درس")
    def lesson_count_display(self, obj: Section) -> int:
        return obj.lesson_count


@admin.register(Lesson)
class LessonAdmin(OnlineOnlyAdminMixin, admin.ModelAdmin):
    list_display = (
        "title",
        "course_title",
        "section",
        "lesson_type",
        "duration_minutes",
        "is_free_preview",
        "is_published",
    )
    list_editable = ("is_free_preview", "is_published")
    list_filter = ("lesson_type", "is_published", "is_free_preview", "section__course")
    search_fields = ("title", "summary", "content", "section__title")
    autocomplete_fields = ("section",)
    ordering = ("section__course", "section__order", "order")
    inlines = (LessonAttachmentInline,)
    readonly_fields = ("created_at", "updated_at")

    fieldsets = (
        ("اطلاعات درس", {"fields": ("section", "title", "summary", "order")}),
        ("نوع و مدت", {"fields": ("lesson_type", "duration_minutes")}),
        (
            "محتوا",
            {
                "description": (
                    "فایل ویدیو در پوشه محافظت‌شده ذخیره می‌شود و آدرس مستقیم آن "
                    "برای کسی که در دوره ثبت‌نام نکرده کار نمی‌کند."
                ),
                "fields": ("content", "video_file", "video_external_url", "scheduled_at"),
            },
        ),
        (
            "دسترسی",
            {
                "description": (
                    "«پیش‌نمایش رایگان» یعنی این درس برای همه بازدیدکنندگان سایت باز است. "
                    "معمولاً یکی دو درس اول را پیش‌نمایش می‌گذارند."
                ),
                "fields": ("is_free_preview", "is_published"),
            },
        ),
        ("تاریخ‌ها", {"fields": ("created_at", "updated_at"), "classes": ("collapse",)}),
    )

    @admin.display(description="دوره", ordering="section__course__title")
    def course_title(self, obj: Lesson) -> str:
        return obj.section.course.title

    def get_queryset(self, request):
        # بدون این، فهرست درس‌ها برای هر سطر دو کوئری اضافه می‌زد.
        return super().get_queryset(request).select_related("section", "section__course")


@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "category",
        "instructor",
        "course_type",
        "site_visibility",
        "start_date",
        "seats_display",
        "price_display",
        "lesson_count_display",
        "is_featured",
        "is_published",
    )
    list_editable = ("is_featured", "is_published")
    list_filter = (
        "is_published",
        "is_featured",
        "course_type",
        "level",
        "category",
        "certificate_available",
        "start_date",
    )
    search_fields = ("title", "short_description", "full_description")
    prepopulated_fields = {"slug": ("title",)}
    date_hierarchy = "start_date"
    autocomplete_fields = ("category",)
    ordering = ("-created_at",)
    list_per_page = 25
    readonly_fields = ("created_at", "updated_at", "thumbnail_preview")
    inlines = (SectionInline, OnlineSessionInline)

    def get_inlines(self, request, obj):
        # فصل و درس و کلاس آنلاین فقط برای دوره غیرحضوری و فقط وقتی بخش
        # آنلاین روشن است معنا دارند.
        if not online_courses_enabled() or (obj is not None and obj.is_in_person):
            return ()
        return super().get_inlines(request, obj)

    fieldsets = (
        (
            "اطلاعات اصلی",
            {"fields": ("title", "slug", "category", "instructor", "short_description")},
        ),
        ("توضیحات", {"fields": ("full_description", "target_audience", "prerequisites", "syllabus")}),
        ("شیوه برگزاری", {"fields": ("course_type", "level", "location")}),
        (
            "زمان‌بندی و ظرفیت",
            {"fields": ("start_date", "end_date", "duration_hours", "capacity")},
        ),
        (
            "قیمت",
            {
                "description": "قیمت‌ها به تومان وارد شوند. صفر یعنی دوره رایگان است.",
                "fields": ("price", "discount_price"),
            },
        ),
        ("تصاویر", {"fields": ("thumbnail", "thumbnail_preview", "hero_image")}),
        ("امکانات", {"fields": ("certificate_available", "exam_available")}),
        (
            "دسترسی",
            {
                "description": (
                    "«مدت دسترسی» صفر یعنی دسترسی دائمی است. «دوره اشتراک ویژه» "
                    "یعنی کاربران دارای اشتراک ویژه بدون خرید جداگانه به این دوره "
                    "دسترسی دارند."
                ),
                "fields": ("access_duration_days", "vip_access"),
            },
        ),
        ("وضعیت انتشار", {"fields": ("is_featured", "is_published", "created_at", "updated_at")}),
        ("سئو", {"fields": ("meta_title", "meta_description"), "classes": ("collapse",)}),
    )

    @admin.display(description="تعداد درس")
    def lesson_count_display(self, obj: Course) -> int:
        return obj.lesson_count

    @admin.display(description="ثبت‌نام / ظرفیت")
    def seats_display(self, obj: Course) -> str:
        from .capacity import seats_taken

        taken = seats_taken(obj)
        if obj.capacity is None:
            return f"{taken} / نامحدود"
        return f"{taken} / {obj.capacity}"

    @admin.display(description="در سایت")
    def site_visibility(self, obj: Course):
        """
        دوره در سایت دیده می‌شود یا نه — و اگر نه، چرا.

        «منتشر شده» به‌تنهایی کافی نیست: دوره آنلاینِ منتشرشده هم تا روشن
        شدن بخش آنلاین پنهان است و مدیر باید این را همین‌جا ببیند.
        """
        if obj.is_offered:
            return format_html('<span style="color:#1e8449">دیده می‌شود</span>')
        if not obj.is_published:
            return format_html('<span style="color:#7f8c8d">منتشر نشده</span>')
        return format_html('<span style="color:#d99400">پنهان (غیرحضوری)</span>')

    @admin.display(description="قیمت")
    def price_display(self, obj: Course) -> str:
        if obj.is_free:
            return "رایگان"
        if obj.has_discount:
            return f"{obj.final_price:,} ({obj.discount_percent}٪ تخفیف)"
        return f"{obj.price:,}"

    @admin.display(description="پیش‌نمایش تصویر")
    def thumbnail_preview(self, obj: Course):
        if obj.thumbnail:
            return format_html(
                '<img src="{}" style="max-height:100px;border-radius:8px;">', obj.thumbnail.url
            )
        return "—"

    @admin.action(description="انتشار دوره‌های انتخاب‌شده")
    def publish_courses(self, request, queryset):
        updated = queryset.update(is_published=True)
        self.message_user(request, f"{updated} دوره منتشر شد.")

    @admin.action(description="لغو انتشار دوره‌های انتخاب‌شده")
    def unpublish_courses(self, request, queryset):
        updated = queryset.update(is_published=False)
        self.message_user(request, f"{updated} دوره از انتشار خارج شد.")

    actions = ("publish_courses", "unpublish_courses")


@admin.register(LessonProgress)
class LessonProgressAdmin(OnlineOnlyAdminMixin, admin.ModelAdmin):
    """
    مشاهده پیشرفت دانشجویان.

    فقط‌خواندنی است: پیشرفت باید بازتاب کاری باشد که دانشجو واقعاً انجام
    داده. اگر از پنل قابل ویرایش باشد، عددی که مبنای صدور گواهی است
    دستکاری‌شدنی می‌شود.
    """

    list_display = (
        "user",
        "course_title",
        "lesson",
        "is_completed",
        "completed_at",
        "last_viewed_at",
    )
    list_filter = ("is_completed", "lesson__section__course")
    search_fields = ("user__mobile", "user__first_name", "user__last_name", "lesson__title")
    date_hierarchy = "last_viewed_at"
    ordering = ("-last_viewed_at",)
    list_per_page = 50

    def has_add_permission(self, request) -> bool:
        return False

    def has_change_permission(self, request, obj=None) -> bool:
        return False

    def get_readonly_fields(self, request, obj=None):
        return [field.name for field in self.model._meta.fields]

    @admin.display(description="دوره", ordering="lesson__section__course__title")
    def course_title(self, obj: LessonProgress) -> str:
        return obj.lesson.section.course.title

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .select_related("user", "lesson", "lesson__section", "lesson__section__course")
        )


@admin.register(Enrollment)
class EnrollmentAdmin(admin.ModelAdmin):
    """
    مدیریت دسترسی دانشجویان.

    برخلاف جدول تراکنش‌ها که فقط‌خواندنی است، اینجا افزودن دستی لازم است:
    شرکتی که ده نفر را ثبت‌نام می‌کند، دانشجویی که خارج از سایت پرداخت
    کرده، یا هدیه‌ای که پشتیبانی می‌دهد. اما وضعیت هر ثبت‌نام همیشه ثبت
    می‌ماند تا معلوم باشد دسترسی از کجا آمده است.
    """

    list_display = (
        "user",
        "course",
        "source",
        "status_badge",
        "access_until",
        "completion_display",
        "created_at",
    )
    list_filter = (
        "status",
        "source",
        ("completed_at", admin.EmptyFieldListFilter),
        "course",
        "created_at",
    )
    search_fields = (
        "user__mobile",
        "user__first_name",
        "user__last_name",
        "course__title",
        "order__order_number",
    )
    autocomplete_fields = ("course",)
    date_hierarchy = "created_at"
    ordering = ("-created_at",)
    list_per_page = 50
    readonly_fields = ("created_at", "updated_at")

    fieldsets = (
        ("ثبت‌نام", {"fields": ("user", "course", "source", "status")}),
        (
            "مدت دسترسی",
            {
                "description": (
                    "«پایان دسترسی» را خالی بگذارید تا دسترسی دائمی باشد. "
                    "هنگام خرید، این تاریخ خودکار از روی «مدت دسترسی» دوره پر می‌شود."
                ),
                "fields": ("starts_at", "expires_at"),
            },
        ),
        (
            "گذراندن دوره",
            {
                "description": (
                    "برای دوره حضوری: پس از برگزاری کلاس، گذراندن دانشجو را اینجا "
                    "تأیید کنید. آزمون پایانی و گواهی از روی همین تأیید باز می‌شوند."
                ),
                "fields": ("completed_at",),
            },
        ),
        ("سفارش مرتبط", {"fields": ("order",), "classes": ("collapse",)}),
        ("یادداشت", {"fields": ("note",)}),
        ("تاریخ‌ها", {"fields": ("created_at", "updated_at"), "classes": ("collapse",)}),
    )

    @admin.display(description="وضعیت", ordering="status")
    def status_badge(self, obj: Enrollment):
        if obj.status == EnrollmentStatus.ACTIVE and obj.is_expired:
            return format_html('<span style="color:#d99400">منقضی شده</span>')

        colors = {
            EnrollmentStatus.ACTIVE: "#1e8449",
            EnrollmentStatus.SUSPENDED: "#c0392b",
            EnrollmentStatus.REFUNDED: "#7f8c8d",
        }
        return format_html(
            '<span style="color:{};font-weight:600">{}</span>',
            colors.get(obj.status, "#000"),
            obj.get_status_display(),
        )

    @admin.display(description="دسترسی تا")
    def access_until(self, obj: Enrollment) -> str:
        if not obj.expires_at:
            return "دائمی"
        return f"{obj.expires_at:%Y-%m-%d} ({obj.days_remaining} روز)"

    @admin.display(description="گذراندن دوره", ordering="completed_at")
    def completion_display(self, obj: Enrollment) -> str:
        if obj.completed_at:
            return f"تأییدشده ({obj.completed_at:%Y-%m-%d})"
        return "—"

    @admin.action(description="تأیید گذراندن دوره (حضوری) برای موارد انتخاب‌شده")
    def mark_completed(self, request, queryset):
        # تاریخ تأییدهای قبلی دست نمی‌خورد؛ روی گواهی‌ای که صادر شده، همان
        # تاریخ اول معتبر است.
        updated = queryset.filter(completed_at__isnull=True).update(
            completed_at=timezone.now()
        )
        self.message_user(request, f"گذراندن دوره برای {updated} ثبت‌نام تأیید شد.")

    @admin.action(description="لغو تأیید گذراندن دوره برای موارد انتخاب‌شده")
    def unmark_completed(self, request, queryset):
        updated = queryset.exclude(completed_at__isnull=True).update(completed_at=None)
        self.message_user(
            request,
            f"تأیید گذراندن دوره برای {updated} ثبت‌نام برداشته شد. "
            "گواهی‌هایی که قبلاً صادر شده‌اند خودکار باطل نمی‌شوند.",
        )

    @admin.action(description="تعلیق دسترسی موارد انتخاب‌شده")
    def suspend_selected(self, request, queryset):
        updated = queryset.update(status=EnrollmentStatus.SUSPENDED)
        self.message_user(request, f"دسترسی {updated} ثبت‌نام بسته شد.")

    @admin.action(description="فعال کردن دسترسی موارد انتخاب‌شده")
    def activate_selected(self, request, queryset):
        updated = queryset.update(status=EnrollmentStatus.ACTIVE)
        self.message_user(request, f"دسترسی {updated} ثبت‌نام فعال شد.")

    actions = (
        "mark_completed",
        "unmark_completed",
        "suspend_selected",
        "activate_selected",
    )

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("user", "course", "order")


@admin.register(OnlineSession)
class OnlineSessionAdmin(OnlineOnlyAdminMixin, admin.ModelAdmin):
    """
    مدیریت کلاس‌های آنلاین.

    ستون «لینک» فقط می‌گوید لینک ثبت شده یا نه و خودِ آدرس را در فهرست
    چاپ نمی‌کند؛ صفحه فهرست معمولاً روی نمایشگر جلسه یا در اسکرین‌شات
    دیده می‌شود.
    """

    list_display = (
        "title",
        "course",
        "starts_at",
        "duration_minutes",
        "link_status",
        "state_badge",
    )
    list_filter = ("status", "course")
    search_fields = ("title", "description", "course__title")
    autocomplete_fields = ("course", "lesson")
    date_hierarchy = "starts_at"
    ordering = ("-starts_at",)
    list_per_page = 30
    readonly_fields = ("ends_at", "created_at", "updated_at")

    fieldsets = (
        ("جلسه", {"fields": ("course", "title", "description", "lesson")}),
        (
            "زمان",
            {
                "description": "پایان جلسه خودکار از روی شروع و مدت حساب می‌شود.",
                "fields": ("starts_at", "duration_minutes", "ends_at"),
            },
        ),
        (
            "ورود به کلاس",
            {
                "description": (
                    "لینک را از پنل اسکای‌روم کپی کنید. این آدرس در هیچ صفحه‌ای "
                    "نمایش داده نمی‌شود؛ فقط کاربری که در دوره ثبت‌نام فعال دارد، "
                    "با کلیک روی دکمه ورود به آن هدایت می‌شود. «شناسه کلاس» فقط "
                    "برای حالت اتصال خودکار به API اسکای‌روم لازم است."
                ),
                "fields": ("meeting_url", "room_id"),
            },
        ),
        ("وضعیت", {"fields": ("status", "cancel_reason")}),
        ("تاریخ‌ها", {"fields": ("created_at", "updated_at"), "classes": ("collapse",)}),
    )

    @admin.display(description="لینک ورود")
    def link_status(self, obj: OnlineSession) -> str:
        return "ثبت شده" if obj.has_link else "ثبت نشده"

    @admin.display(description="وضعیت")
    def state_badge(self, obj: OnlineSession):
        colors = {
            "live": "#1e8449",
            "upcoming": "#2471a3",
            "finished": "#7f8c8d",
            "cancelled": "#c0392b",
        }
        return format_html(
            '<span style="color:{};font-weight:600">{}</span>',
            colors[obj.state],
            obj.state_label,
        )

    @admin.action(description="لغو جلسه‌های انتخاب‌شده")
    def cancel_selected(self, request, queryset):
        updated = queryset.update(status=OnlineSessionStatus.CANCELLED)
        self.message_user(request, f"{updated} جلسه لغو شد.")

    actions = ("cancel_selected",)

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("course")
