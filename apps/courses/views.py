"""
Viewهای عمومی دوره‌ها.

منطق فیلتر داخل یک تابع جدا نگه داشته شده تا View کوتاه بماند و
بتوان همان فیلتر را در صفحات دیگر (مثل جست‌وجو) هم استفاده کرد.
"""

import logging
from urllib.parse import quote

from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, Prefetch, Q, QuerySet
from django.http import Http404, HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from apps.accounts.models import InstructorProfile
from apps.core.seo import listing_seo

from .access import check_lesson_access, check_session_access
from .capacity import full_message, has_seat, lock_and_find_full, seats_left
from .enrollment import active_enrollment
from .live import sessions_with_access, user_sessions
from .models import (
    Course,
    CourseCategory,
    CourseLevel,
    CourseType,
    Lesson,
    LessonAttachment,
    OnlineSession,
    offered_course_types,
    offered_courses_q,
    online_courses_enabled,
)
from .progress import (
    LessonProgress,
    course_progress,
    record_view,
    save_position,
    set_completed,
)
from .services import get_skyroom_service
from .serving import serve_protected_file
from .storages import protected_storage

logger = logging.getLogger("hse.skyroom")

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
        ).annotate(num_courses=Count("courses", filter=offered_courses_q("courses__"))),
        # فقط شیوه‌هایی که در سایت عرضه می‌شوند؛ اگر یکی بیشتر نباشد، قالب
        # کل این گروه فیلتر را نشان نمی‌دهد.
        "course_types": [
            (value, label)
            for value, label in CourseType.choices
            if value in offered_course_types()
        ],
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
                            "courses", filter=offered_courses_q("courses__")
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

    # صفحه دسته‌بندی، صفحه واقعی سایت است و ایندکس می‌شود؛ ترکیب‌های
    # فیلتر و مرتب‌سازی فقط ابزار کاربرند و noindex می‌گیرند.
    seo = listing_seo(request, reverse("courses:list"))

    context = {
        "page_obj": page,
        "courses": page.object_list,
        "total_count": paginator.count,
        "querystring": params.urlencode(),
        "active_category": active_category,
        "breadcrumb_items": breadcrumb_items,
        "breadcrumb_current": breadcrumb_current,
        "nav_active": "courses",
        "seo_canonical": seo["canonical"],
        "page_noindex": seo["noindex"],
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

    # apps.orders و apps.exams به apps.courses وابسته‌اند؛ برای اینکه
    # وابستگی دوطرفه نشود، این دو همین‌جا وارد می‌شوند نه در بالای فایل.
    from apps.certificates.issue import certificate_card
    from apps.exams.summary import exam_card
    from apps.orders.services import purchased_course_ids

    # دوره حضوری (و هر دوره‌ای وقتی بخش آنلاین خاموش است) درس و کلاس
    # آنلاینی ندارد که نشان داده شود؛ صفحه فقط سرفصل متنی را می‌آورد.
    online = course.has_online_content

    context = {
        "course": course,
        # ساختار دوره به‌همراه وضعیت قفل هر درس برای همین بازدیدکننده
        "curriculum": _curriculum_for(course, request.user) if online else [],
        "progress": course_progress(request.user, course),
        "in_cart": course.pk in request.session.get("cart", []),
        # جلسه‌های آنلاینِ تمام‌نشده. عنوان و ساعت را همه می‌بینند (برای
        # فروش دوره لازم است)، اما لینک ورود فقط از راه View بررسی‌کننده
        # دسترسی تحویل داده می‌شود.
        "session_rows": (
            sessions_with_access(request.user, course.online_sessions.upcoming()[:5])
            if online
            else []
        ),
        "enrollment": active_enrollment(request.user, course),
        # کارت آزمون پایان دوره. None یعنی این دوره آزمون فعالی ندارد.
        "exam_card": exam_card(request.user, course),
        # کارت گواهی — فقط برای دانشجوی ثبت‌نام‌شده معنا دارد.
        "certificate_card": certificate_card(request.user, course),
        "already_purchased": course.pk in purchased_course_ids(request.user),
        # ظرفیت: None یعنی نامحدود. «پر» برای کسی که خودش صندلی دارد معنا
        # ندارد، پس has_seat با کاربر فعلی پرسیده می‌شود.
        "seats_left": seats_left(course),
        "is_full": not has_seat(course, request.user),
        "related_courses": related,
        "share": _share_links(request, course),
        "breadcrumb_items": breadcrumb_items,
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
            # نتیجه جست‌وجو صفحه‌ی سایت نیست؛ محتوایش از صفحه‌های دیگر
            # می‌آید و ایندکس‌شدنش فقط نسخه تکراری می‌سازد.
            "page_noindex": True,
            "seo_canonical": request.build_absolute_uri(reverse("core:search")),
        },
    )


# ---------------------------------------------------------------------------
# مدرسان
# ---------------------------------------------------------------------------


def instructor_list(request: HttpRequest) -> HttpResponse:
    """فهرست مدرسان فعال آکادمی."""
    instructors = InstructorProfile.objects.filter(is_active=True).annotate(
        num_courses=Count("courses", filter=offered_courses_q("courses__"))
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

    # درس، ویدیو و جزوه محتوای آنلاین‌اند. وقتی این بخش خاموش است (یا
    # دوره حضوری است)، آدرس درس هم مثل صفحه‌ای که وجود ندارد رفتار می‌کند؛
    # حتی برای کسی که آدرس را از قبل دارد.
    if not lesson.section.course.is_offered:
        raise Http404("دوره منتشر نشده است.")

    if not lesson.section.course.has_online_content:
        raise Http404("این دوره محتوای آنلاین ندارد.")

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

    # درس‌هایی که این کاربر تمام کرده — با یک کوئری، نه یکی به‌ازای هر درس.
    completed_ids: set[int] = set()
    if user.is_authenticated:
        completed_ids = set(
            LessonProgress.objects.filter(
                user=user, is_completed=True, lesson__section__course=course
            ).values_list("lesson_id", flat=True)
        )

    result = []
    for index, section in enumerate(sections):
        lessons = [
            {
                "lesson": lesson,
                "access": check_lesson_access(user, lesson),
                "is_completed": lesson.pk in completed_ids,
            }
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

    # باز کردن درس یعنی «دیدمش»؛ همین یک ردیف است که بعداً درصد پیشرفت و
    # دکمه «ادامه یادگیری» از روی آن ساخته می‌شود.
    lesson_progress = record_view(request.user, lesson) if access.allowed else None

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
            "lesson_progress": lesson_progress,
            "progress": course_progress(request.user, course),
            "curriculum": _curriculum_for(
                course, request.user, current_lesson=lesson
            ),
            "previous_lesson": siblings[index - 1] if index else None,
            "next_lesson": (
                siblings[index + 1]
                if index is not None and index + 1 < len(siblings)
                else None
            ),
            # جلسه‌های آنلاینی که مدیر به همین درس وصل کرده است. قول این
            # بخش در فاز ۹ داده شده بود: «لینک ورود پیش از شروع جلسه در
            # همین صفحه قرار می‌گیرد».
            "session_rows": sessions_with_access(
                request.user, lesson.online_sessions.all()
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


@login_required
@require_POST
def lesson_complete(request: HttpRequest, slug: str, pk: int) -> HttpResponse:
    """
    علامت‌گذاری درس به‌عنوان تکمیل‌شده (یا برگرداندن آن).

    چرا فقط POST؟ چون این درخواست وضعیت را تغییر می‌دهد. اگر با GET کار
    می‌کرد، یک لینک ساده یا حتی پیش‌بارگذاری مرورگر می‌توانست درس‌ها را
    بی‌اجازه تکمیل کند.

    این یک فرم معمولی است، نه Ajax؛ پس اگر جاوااسکریپت کاربر خاموش باشد
    هم درست کار می‌کند.
    """
    lesson = _lesson_or_404(slug, pk)

    if not check_lesson_access(request.user, lesson):
        raise Http404("دسترسی به این درس امکان‌پذیر نیست.")

    completed = request.POST.get("completed") == "1"
    set_completed(request.user, lesson, completed)

    # بعد از تکمیل، کاربر معمولاً می‌خواهد سراغ درس بعدی برود.
    if completed and request.POST.get("go_next") == "1":
        progress = course_progress(request.user, lesson.section.course)
        if progress.next_lesson:
            return redirect(progress.next_lesson.get_absolute_url())

    return redirect(lesson.get_absolute_url())


@login_required
@require_POST
def lesson_position(request: HttpRequest, slug: str, pk: int) -> JsonResponse:
    """
    ذخیره ثانیه‌ای که کاربر ویدیو را در آن رها کرده است.

    این تنها جای پروژه است که از جاوااسکریپت درخواست پس‌زمینه می‌فرستیم،
    و کاملاً اختیاری است: اگر کار نکند، فقط ویدیو از اول پخش می‌شود و
    هیچ بخشی از سایت خراب نمی‌شود.
    """
    lesson = _lesson_or_404(slug, pk)

    if not check_lesson_access(request.user, lesson):
        raise Http404("دسترسی به این درس امکان‌پذیر نیست.")

    try:
        seconds = int(float(request.POST.get("seconds", 0)))
    except (TypeError, ValueError):
        return JsonResponse({"ok": False, "error": "مقدار نامعتبر"}, status=400)

    save_position(request.user, lesson, seconds)
    return JsonResponse({"ok": True})


@login_required
@require_POST
def enroll_free(request: HttpRequest, slug: str) -> HttpResponse:
    """
    ثبت‌نام در دوره رایگان.

    دوره رایگان از مسیر سبد خرید و پرداخت رد نمی‌شود؛ همین یک دکمه کافی
    است. اما رکورد ثبت‌نام مثل بقیه ساخته می‌شود تا در «دوره‌های من»،
    گزارش‌های مدیر و بعداً صدور گواهی، هیچ فرقی با دوره پولی نداشته باشد.
    """
    from .enrollment import enroll
    from .models import EnrollmentSource

    course = get_object_or_404(Course.objects.published(), slug=slug)

    if not course.is_free:
        messages.error(request, "این دوره رایگان نیست.")
        return redirect(course.get_absolute_url())

    if not course.registration_open:
        messages.error(request, "مهلت ثبت‌نام این دوره به پایان رسیده است.")
        return redirect(course.get_absolute_url())

    # بررسی ظرفیت و ساخت ثبت‌نام زیر یک قفل؛ وگرنه دو کلیک هم‌زمان روی
    # آخرین صندلی هر دو موفق می‌شدند.
    with transaction.atomic():
        if lock_and_find_full([course.pk], request.user):
            messages.error(request, full_message([course]))
            return redirect(course.get_absolute_url())
        enroll(request.user, course, source=EnrollmentSource.FREE)
    messages.success(request, f"ثبت‌نام شما در «{course.title}» انجام شد.")

    progress = course_progress(request.user, course)
    if progress.resume_lesson:
        return redirect(progress.resume_lesson.get_absolute_url())

    return redirect(course.get_absolute_url())


# ---------------------------------------------------------------------------
# کلاس‌های آنلاین
# ---------------------------------------------------------------------------


def _session_or_404(slug: str, pk: int) -> OnlineSession:
    """
    جلسه را همراه دوره‌اش پیدا می‌کند.

    مثل آدرس درس، آدرس جلسه هم اسلاگ دوره را دارد و بررسی می‌کنیم که
    جلسه واقعاً به همان دوره تعلق داشته باشد؛ وگرنه شناسه جلسه‌ای از یک
    دوره گران، زیر آدرس یک دوره رایگان قابل صدا زدن می‌شد.
    """
    session = get_object_or_404(
        OnlineSession.objects.select_related("course", "course__instructor"), pk=pk
    )

    if session.course.slug != slug:
        raise Http404("این جلسه متعلق به این دوره نیست.")

    if not session.course.is_offered:
        raise Http404("دوره منتشر نشده است.")

    if not session.course.has_online_content:
        raise Http404("کلاس آنلاین برای این دوره فعال نیست.")

    return session


@login_required
def session_join(request: HttpRequest, slug: str, pk: int) -> HttpResponse:
    """
    ورود به کلاس آنلاین.

    این View تنها راه رسیدن به آدرس کلاس است. هیچ‌جای سایت لینک واقعی
    را در HTML نمی‌گذارد؛ پس کسی نمی‌تواند با دیدن سورس صفحه یا
    فوروارد کردن یک لینک عمومی، وارد کلاسی شود که در آن ثبت‌نام ندارد.

    اگر شرایط ورود فراهم نباشد، کاربر با پیام روشن به صفحه دوره
    برمی‌گردد — نه یک خطای فنی.
    """
    session = _session_or_404(slug, pk)
    access = check_session_access(request.user, session)

    if not access.allowed:
        messages.error(request, access.message or "ورود به این کلاس امکان‌پذیر نیست.")
        return redirect(session.course.get_absolute_url())

    link = get_skyroom_service().join_link(session, request.user)

    if not link.success:
        logger.warning(
            "ورود به کلاس ناموفق. جلسه=%s کاربر=%s علت=%s",
            session.pk,
            request.user.masked_mobile,
            link.message,
        )
        messages.error(request, link.message or "ورود به این کلاس امکان‌پذیر نیست.")
        return redirect(session.course.get_absolute_url())

    logger.info(
        "ورود به کلاس. جلسه=%s دوره=%s کاربر=%s سرویس=%s",
        session.pk,
        session.course.slug,
        request.user.masked_mobile,
        link.provider,
    )

    # خود آدرس کلاس در پاسخ نمی‌نشیند؛ مرورگر با یک Redirect به آن
    # می‌رود و صفحه‌ای که لینک را نشان بدهد اصلاً ساخته نمی‌شود.
    return redirect(link.url)


@login_required
def my_sessions(request: HttpRequest) -> HttpResponse:
    """
    کلاس‌های آنلاین کاربر — پیش‌رو و برگزارشده.

    فقط جلسه‌های دوره‌هایی که کاربر در آن‌ها ثبت‌نام فعال دارد؛ همان
    فهرستی که دانشجو برای پاسخ به «کلاس بعدی من کِی است؟» باز می‌کند.
    """
    if not online_courses_enabled():
        raise Http404("کلاس آنلاین فعال نیست.")

    sessions = user_sessions(request.user)

    return render(
        request,
        "courses/my_sessions.html",
        {
            "upcoming_rows": sessions_with_access(request.user, sessions.upcoming()),
            "past_rows": sessions_with_access(request.user, sessions.past()[:20]),
        },
    )
