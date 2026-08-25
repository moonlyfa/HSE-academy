"""
Viewهای عمومی دوره‌ها.

منطق فیلتر داخل یک تابع جدا نگه داشته شده تا View کوتاه بماند و
بتوان همان فیلتر را در صفحات دیگر (مثل جست‌وجو) هم استفاده کرد.
"""

from django.core.paginator import Paginator
from django.db.models import Count, Q, QuerySet
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, render

from .models import Course, CourseCategory, CourseLevel, CourseType

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
        queryset = queryset.filter(category__slug=category_slug)

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
        "categories": CourseCategory.objects.filter(is_active=True).annotate(
            num_courses=Count("courses", filter=Q(courses__is_published=True))
        ),
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

    context = {
        "page_obj": page,
        "courses": page.object_list,
        "total_count": paginator.count,
        "querystring": params.urlencode(),
        "active_category": (
            CourseCategory.objects.filter(slug=request.GET.get("category")).first()
            if request.GET.get("category")
            else None
        ),
        **_filter_context(request),
    }
    return render(request, "courses/course_list.html", context)


def course_detail(request: HttpRequest, slug: str) -> HttpResponse:
    """صفحه جزئیات یک دوره."""
    course = get_object_or_404(
        Course.objects.published().select_related("category", "instructor"),
        slug=slug,
    )

    related = (
        Course.objects.published()
        .filter(category=course.category)
        .exclude(pk=course.pk)
        .select_related("category")[:3]
    )

    return render(
        request,
        "courses/course_detail.html",
        {"course": course, "related_courses": related},
    )


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
        {"courses": courses, "total_count": courses.count(), **_filter_context(request)},
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
