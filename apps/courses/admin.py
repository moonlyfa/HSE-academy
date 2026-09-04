"""پنل مدیریت دسته‌بندی‌ها و دوره‌ها."""

from django.contrib import admin
from django.urls import reverse
from django.utils.html import format_html

from .models import (
    Course,
    CourseCategory,
    Lesson,
    LessonAttachment,
    LessonProgress,
    Section,
)


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


class LessonAttachmentInline(admin.TabularInline):
    model = LessonAttachment
    extra = 1
    fields = ("title", "file", "order")
    ordering = ("order", "id")


@admin.register(Section)
class SectionAdmin(admin.ModelAdmin):
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
class LessonAdmin(admin.ModelAdmin):
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
        "start_date",
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
    inlines = (SectionInline,)

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
        ("وضعیت انتشار", {"fields": ("is_featured", "is_published", "created_at", "updated_at")}),
        ("سئو", {"fields": ("meta_title", "meta_description"), "classes": ("collapse",)}),
    )

    @admin.display(description="تعداد درس")
    def lesson_count_display(self, obj: Course) -> int:
        return obj.lesson_count

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
class LessonProgressAdmin(admin.ModelAdmin):
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
