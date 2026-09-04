"""
Viewهای عمومی دوره‌ها.

منطق فیلتر داخل یک تابع جدا نگه داشته شده تا View کوتاه بماند و
بتوان همان فیلتر را در صفحات دیگر (مثل جست‌وجو) هم استفاده کرد.
"""

from urllib.parse import quote

from django.contrib.admin.views.decorators import staff_member_required
from django.core.paginator import Paginator
from django.db.models import Count, Prefetch, Q, QuerySet
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, render
from django.urls import reverse

from apps.accounts.models import InstructorProfile

from .access import check_lesson_access
from .models import (
    Course,
    CourseCategory,
    CourseLevel,
    CourseType,
    Lesson,
    LessonAttachment,
)
from .serving import serve_protected_file
from .storages import protected_storage

# گزینه‌های مرتب‌سازی: کلیدِ داخل آدرس → (برچسب فارسی، فیلد مرتب‌سازی)
SORT_OPTIONS = {
    "newest": ("جدیدترین", "-created_at"),
    "cheapest": ("ارزان‌ترین", "price"),
    "expensive": ("گران‌ترین", "-price"),
    "upcoming": ("نزدیک‌ترین تاریخ شروع", "start_date"),
}
DEFAULT_SORT = "newest"
PAGE_SIZE = 12


def filter_courses(request: HttpRequest, queryset: QuerySet[Course]) -> QuerySet[Course]:
    """
    فیلترهای صفحه دوره‌ها را روی کوئری‌ست اعمال می‌کند.

    همه فیلترها از پارامترهای آدرس خوانده می‌شوند تا کاربر بتواند
    نتیجه فیلترشده را کپی و به دیگری بدهد (و برای سئو هم بهتر است).
    """
    category_slug = request.GET.get("category")
    if category_slug:
        # زیردسته‌ها هم باید در نتیجه بیایند؛ وگرنه انتخاب یک دسته اصلی
        # ظاهراً «هیچ دوره‌ای ندارد» در حالی که دوره‌ها زیر زیردسته‌اند.
        queryset = queryset.filter(
            Q(category__slug=category_slug) | Q(category__parent__slug=category_slug)
        )

    course_type = request.GET.get("type")
    if course_type in CourseType.values:
        queryset = queryset.filter(course_type=course_type)

    level = request.GET.get("level")
    if level in CourseLevel.values:
        queryset = queryset.filter(level=level)

    price_filter = request.GET.get("price")
    if price_filter == "free":
        queryset = queryset.filter(price=0)
    elif price_filter == "paid":
        queryset = queryset.filter(price__gt=0)

    query = request.GET.get("q", "").strip()
    if query:
        queryset = queryset.filter(
            Q(title__icontains=query)
            | Q(short_description__icontains=query)
            | Q(full_description__icontains=query)
            | Q(category__name__icontains=query)
        )

    sort_key = request.GET.get("sort", DEFAULT_SORT)
    if sort_key not in SORT_OPTIONS:
        sort_key = DEFAULT_SORT
    queryset = queryset.order_by(SORT_OPTIONS[sort_key][1])

    return queryset


def _filter_context(request: HttpRequest) -> dict:
    """داده‌های مشترک نوار فیلتر — در صفحه دوره‌ها و جست‌وجو استفاده می‌شود."""
    return {
        "categories": CourseCategory.objects.filter(
            is_active=True, parent__isnull=True
        ).annotate(num_courses=Count("courses", filter=Q(courses__is_published=True))),
        "course_types": CourseType.choices,
        "levels": CourseLevel.choices,
        "sort_options": [(key, label) for key, (label, _) in SORT_OPTIONS.items()],
        # مقادیر انتخاب‌شده فعلی، تا در قالب تیک بخورند
        "selected_category": request.GET.get("category", ""),
        "selected_type": request.GET.get("type", ""),
        "selected_level": request.GET.get("level", ""),
        "selected_price": request.GET.get("price", ""),
        "selected_sort": request.GET.get("sort", DEFAULT_SORT),
        "query": request.GET.get("q", "").strip(),
    }


def _courses_crumb() -> dict:
    """حلقه مشترک همه مسیرهای راهنمای بخش دوره‌ها."""
    return {"label": "دوره‌ها", "url": reverse("courses:list")}


def course_list(request: HttpRequest) -> HttpResponse:
    """
    صفحه همه دوره‌ها با فیلتر.

    هم دکمه «دوره‌ها» در هدر و هم دکمه «همه دسته‌بندی‌ها» در صفحه اصلی
    به همین صفحه می‌آیند — یک صفحه واحد، نه دو صفحه موازی.
    """
    queryset = Course.objects.published().select_related("category", "instructor")
    queryset = filter_courses(request, queryset)

    paginator = Paginator(queryset, PAGE_SIZE)
    page = paginator.get_page(request.GET.get("page"))

    # پارامترهای فعلی منهای page — برای ساخت لینک صفحه‌بندی
    params = request.GET.copy()
    params.pop("page", None)

    active_category = None
    if request.GET.get("category"):
        active_category = (
            CourseCategory.objects.filter(
                slug=request.GET["category"], is_active=True
            )
            .prefetch_related(
                Prefetch(
                    "children",
                    queryset=CourseCategory.objects.filter(is_active=True).annotate(
                        num_courses=Count(
                            "courses", filter=Q(courses__is_published=True)
                        )
                    ),
                )
            )
            .first()
        )

    # وقتی روی یک دسته فیلتر شده‌ایم، همان دسته آخرین حلقه مسیر است
    # و «دوره‌ها» به حلقه قبلی تبدیل می‌شود.
    if active_category:
        breadcrumb_items = [_courses_crumb()]
        breadcrumb_current = active_category.name
    else:
        breadcrumb_items = []
        breadcrumb_current = "همه دوره‌ها"

    context = {
        "page_obj": page,
        "courses": page.object_list,
        "total_count": paginator.count,
        "querystring": params.urlencode(),
        "active_category": active_category,
        "breadcrumb_items": breadcrumb_items,
        "breadcrumb_current": breadcrumb_current,
        "nav_active": "courses",
        **_filter_context(request),
    }
    return render(request, "courses/course_list.html", context)


def _share_links(request: HttpRequest, course: Course) -> dict:
    """
    لینک‌های اشتراک‌گذاری دوره.

    اینها فقط «لینک» هستند، نه اسکریپت خارجی؛ پس اگر شبکه‌های اجتماعی
    در دسترس نباشند صفحه سالم بالا می‌آید و چیزی کند نمی‌شود.
    """
    absolute_url = request.build_absolute_uri(course.get_absolute_url())
    text = quote(f"{course.title} — {absolute_url}")

    return {
        "url": absolute_url,
        "telegram": f"https://t.me/share/url?url={quote(absolute_url)}&text={quote(course.title)}",
        "whatsapp": f"https://wa.me/?text={text}",
        "email": f"mailto:?subject={quote(course.title)}&body={text}",
    }


def course_detail(request: HttpRequest, slug: str) -> HttpResponse:
    """صفحه جزئیات یک دوره."""
    course = get_object_or_404(
        Course.objects.published().select_related(
            "category", "category__parent", "instructor"
        ),
        slug=slug,
    )

    related = (
        Course.objects.published()
        .filter(category=course.category)
        .exclude(pk=course.pk)
        .select_related("category", "instructor")[:3]
    )

    # مسیر راهنما: صفحه اصلی ← دوره‌ها ← [دسته والد ←] دسته ← عنوان دوره
    breadcrumb_items = [_courses_crumb()]
    if course.category.parent:
        breadcrumb_items.append(
            {
                "label": course.category.parent.name,
                "url": course.category.parent.get_absolute_url(),
            }
        )
    breadcrumb_items.append(
        {"label": course.category.name, "url": course.category.get_absolute_url()}
    )

    context = {
        "course": course,
        # ساختار دوره به‌همراه وضعیت قفل هر درس برای همین بازدیدکننده
        "curriculum": _curriculum_for(course, request.user),
        "related_courses": related,
        "share": _share_links(request, course),
        "breadcrumb_items": breadcrumb_items,
        # تا فاز سبد خرید، درخواست ثبت‌نام از راه فرم تماس ثبت می‌شود.
        "enroll_url": f"{reverse('core:contact')}?course={course.slug}",
        "nav_active": "courses",
    }
    return render(request, "courses/course_detail.html", context)


def training_calendar(request: HttpRequest) -> HttpResponse:
    """
    تقویم دوره‌های آموزشی — دوره‌هایی که هنوز شروع نشده‌اند.

    نسخه کوتاه همین لیست در صفحه اصلی هم نمایش داده می‌شود.
    """
    courses = (
        Course.objects.upcoming()
        .select_related("category", "instructor")
        .order_by("start_date")
    )
    courses = filter_courses(request, courses) if request.GET else courses

    return render(
        request,
        "courses/calendar.html",
        {
            "courses": courses,
            "total_count": courses.count(),
            "nav_active": "calendar",
            **_filter_context(request),
        },
    )


def search(request: HttpRequest) -> HttpResponse:
    """صفحه نتایج جست‌وجو — فعلاً روی دوره‌ها جست‌وجو می‌کند."""
    query = request.GET.get("q", "").strip()

    courses = Course.objects.none()
    if query:
        courses = filter_courses(
            request,
            Course.objects.published().select_related("category", "instructor"),
        )

    paginator = Paginator(courses, PAGE_SIZE)
    page = paginator.get_page(request.GET.get("page"))

    params = request.GET.copy()
    params.pop("page", None)

    return render(
        request,
        "courses/search.html",
        {
            "query": query,
            "page_obj": page,
            "courses": page.object_list,
            "total_count": paginator.count,
            "querystring": params.urlencode(),
        },
    )


# ---------------------------------------------------------------------------
# مدرسان
# ---------------------------------------------------------------------------


def instructor_list(request: HttpRequest) -> HttpResponse:
    """فهرست مدرسان فعال آکادمی."""
    instructors = InstructorProfile.objects.filter(is_active=True).annotate(
        num_courses=Count("courses", filter=Q(courses__is_published=True))
    )

    return render(
        request,
        "courses/instructor_list.html",
        {"instructors": instructors, "nav_active": "instructors"},
    )


def instructor_detail(request: HttpRequest, slug: str) -> HttpResponse:
    """
    صفحه یک مدرس: معرفی و دوره‌هایی که تدریس می‌کند.

    فقط مدرسان فعال صفحه عمومی دارند؛ مدرسی که ادمین غیرفعالش کرده،
    مثل صفحه‌ای که وجود ندارد رفتار می‌کند (۴۰۴).
    """
    instructor = get_object_or_404(
        InstructorProfile.objects.filter(is_active=True), slug=slug
    )

    courses = (
        Course.objects.published()
        .filter(instructor=instructor)
        .select_related("category", "instructor")
        .order_by("-created_at")
    )

    return render(
        request,
        "courses/instructor_detail.html",
        {
            "instructor": instructor,
            "courses": courses,
            "total_count": courses.count(),
            "breadcrumb_items": [
                {"label": "مدرسان", "url": reverse("core:instructors")}
            ],
            "nav_active": "instructors",
        },
    )


# ---------------------------------------------------------------------------
# درس‌ها و فایل‌های دوره
# ---------------------------------------------------------------------------


def _lesson_or_404(slug: str, pk: int) -> Lesson:
    """
    درس را همراه دوره‌اش پیدا می‌کند.

    آدرس درس شامل اسلاگ دوره هم هست؛ پس بررسی می‌کنیم که این درس واقعاً
    متعلق به همان دوره باشد. بدون این بررسی، آدرس دوره‌ای ارزان با شناسه
    درسی از دوره‌ای گران، در را باز می‌کرد.
    """
    lesson = get_object_or_404(
        Lesson.objects.select_related(
            "section", "section__course", "section__course__instructor"
        ).prefetch_related("attachments"),
        pk=pk,
    )

    if lesson.section.course.slug != slug:
        raise Http404("این درس متعلق به این دوره نیست.")

    if not lesson.section.course.is_published:
        raise Http404("دوره منتشر نشده است.")

    return lesson


def _curriculum_for(course: Course, user, current_lesson: Lesson | None = None) -> list[dict]:
    """
    ساختار کامل دوره به‌همراه وضعیت دسترسی هر درس.

    وضعیت قفل را همین‌جا حساب می‌کنیم و به قالب می‌دهیم؛ قالب نباید خودش
    منطق دسترسی داشته باشد، چون منطق پخش‌شده در قالب‌ها همان‌جایی است که
    رخنه‌های امنیتی پیدا می‌شوند.

    is_open مشخص می‌کند کدام فصل باز نمایش داده شود: فصلی که درس جاری در
    آن است، و اگر درس جاری نداشتیم، فصل اول.
    """
    sections = (
        course.sections.filter(is_published=True)
        .prefetch_related(
            Prefetch("lessons", queryset=Lesson.objects.filter(is_published=True))
        )
        .order_by("order", "id")
    )

    result = []
    for index, section in enumerate(sections):
        lessons = [
            {"lesson": lesson, "access": check_lesson_access(user, lesson)}
            for lesson in section.lessons.all()
        ]
        is_open = (
            section.pk == current_lesson.section_id
            if current_lesson
            else index == 0
        )
        result.append({"section": section, "lessons": lessons, "is_open": is_open})
    return result


def lesson_detail(request: HttpRequest, slug: str, pk: int) -> HttpResponse:
    """
    صفحه یک درس.

    اگر کاربر مجاز نباشد، صفحه ۴۰۳ نمی‌دهیم؛ همان صفحه را با محتوای قفل‌شده
    و توضیح اینکه «چرا بسته است و چه کار باید بکند» نشان می‌دهیم. این هم
    برای کاربر مفیدتر است و هم برای فروش دوره.
    """
    lesson = _lesson_or_404(slug, pk)
    course = lesson.section.course
    access = check_lesson_access(request.user, lesson)

    # درس منتشرنشده برای کاربر عادی اصلاً نباید وجود داشته باشد.
    if access.reason == "unpublished":
        raise Http404("این درس منتشر نشده است.")

    siblings = list(
        Lesson.objects.filter(
            section__course=course, section__is_published=True, is_published=True
        )
        .select_related("section")
        .order_by("section__order", "section__id", "order", "id")
    )
    index = next((i for i, item in enumerate(siblings) if item.pk == lesson.pk), None)

    return render(
        request,
        "courses/lesson_detail.html",
        {
            "course": course,
            "lesson": lesson,
            "access": access,
            "curriculum": _curriculum_for(course, request.user, current_lesson=lesson),
            "previous_lesson": siblings[index - 1] if index else None,
            "next_lesson": (
                siblings[index + 1]
                if index is not None and index + 1 < len(siblings)
                else None
            ),
            "lesson_position": (index + 1) if index is not None else None,
            "lesson_total": len(siblings),
            "breadcrumb_items": [
                _courses_crumb(),
                {"label": course.title, "url": course.get_absolute_url()},
            ],
            "nav_active": "courses",
        },
    )


def lesson_video(request: HttpRequest, slug: str, pk: int) -> HttpResponse:
    """
    تحویل فایل ویدیوی یک درس.

    این آدرس همان بررسی دسترسی صفحه درس را دوباره انجام می‌دهد. چرا؟ چون
    کسی می‌تواند مستقیماً همین آدرس را صدا بزند بدون اینکه اصلاً صفحه درس
    را باز کند. هر مسیری که به محتوا می‌رسد باید خودش مجوز را چک کند.
    """
    lesson = _lesson_or_404(slug, pk)

    if not check_lesson_access(request.user, lesson):
        raise Http404("دسترسی به این فایل امکان‌پذیر نیست.")

    if not lesson.video_file:
        raise Http404("برای این درس فایل ویدیویی ثبت نشده است.")

    return serve_protected_file(protected_storage, lesson.video_file.name)


def lesson_attachment(
    request: HttpRequest, slug: str, pk: int, attachment_pk: int
) -> HttpResponse:
    """دانلود یک پیوست درس، با همان قاعده دسترسی."""
    lesson = _lesson_or_404(slug, pk)

    if not check_lesson_access(request.user, lesson):
        raise Http404("دسترسی به این فایل امکان‌پذیر نیست.")

    attachment = get_object_or_404(
        LessonAttachment, pk=attachment_pk, lesson=lesson
    )

    extension = attachment.file.name.rsplit(".", 1)[-1] if "." in attachment.file.name else ""
    download_name = f"{attachment.title}.{extension}" if extension else attachment.title

    return serve_protected_file(
        protected_storage,
        attachment.file.name,
        as_attachment=True,
        download_name=download_name,
    )


@staff_member_required
def protected_media(request: HttpRequest, path: str) -> HttpResponse:
    """
    دسترسی مستقیم مدیر به فایل‌های محافظت‌شده.

    پنل مدیریت جنگو برای هر فایل یک لینک می‌سازد. این View فقط به همان
    لینک‌ها پاسخ می‌دهد تا مدیر بتواند فایل آپلودشده را بررسی کند؛ برای
    بقیه کاربران بسته است.
    """
    return serve_protected_file(protected_storage, path)
