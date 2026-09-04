"""Viewهای صفحات عمومی سایت."""

from django.contrib import messages
from django.db.models import Count, Q
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import redirect, render

from apps.accounts.models import InstructorProfile
from apps.courses.models import Course, CourseCategory

from .forms import ContactForm
from .models import FAQ, Feature, HeroSlide, Partner, SiteSetting, Testimonial


def home(request: HttpRequest) -> HttpResponse:
    """
    صفحه اصلی.

    ترتیب بخش‌ها: اسلایدر تصویری ← تقویم آموزشی ← دسته‌بندی‌ها ← چرا ما
    ← مدرسان ← نظرات ← همکاران ← سؤالات متداول
    """
    site = SiteSetting.load()

    slides = [s for s in HeroSlide.objects.active() if s.is_visible_now]

    calendar_courses = (
        Course.objects.upcoming()
        .select_related("category", "instructor")
        .order_by("start_date")[: site.homepage_calendar_count]
    )

    categories = (
        CourseCategory.objects.filter(is_active=True, show_on_homepage=True)
        .annotate(num_courses=Count("courses", filter=Q(courses__is_published=True)))[
            : site.homepage_category_count
        ]
    )

    instructors = InstructorProfile.objects.filter(
        is_active=True, show_on_homepage=True
    ).annotate(num_courses=Count("courses", filter=Q(courses__is_published=True)))[:4]

    context = {
        "slides": slides,
        "calendar_courses": calendar_courses,
        "categories": categories,
        "featured_courses": Course.objects.featured().select_related(
            "category", "instructor"
        )[:6],
        "features": Feature.objects.active(),
        "instructors": instructors,
        "testimonials": Testimonial.objects.active(),
        "partners": Partner.objects.active(),
        "faqs": FAQ.objects.active().filter(show_on_homepage=True)[:6],
        "nav_active": "home",
    }
    return render(request, "core/home.html", context)


# ---------------------------------------------------------------------------
# صفحات ثابت
# ---------------------------------------------------------------------------


def about(request: HttpRequest) -> HttpResponse:
    return render(
        request,
        "core/about.html",
        {
            "features": Feature.objects.active(),
            "partners": Partner.objects.active(),
            # کارت مدرس همه‌جا تعداد دوره را نشان می‌دهد، پس همین‌جا
            # با یک کوئری شمرده می‌شود نه با یک کوئری به‌ازای هر مدرس.
            "instructors": InstructorProfile.objects.filter(is_active=True).annotate(
                num_courses=Count("courses", filter=Q(courses__is_published=True))
            )[:4],
            "nav_active": "about",
        },
    )


def contact(request: HttpRequest) -> HttpResponse:
    """
    تماس با ما.

    پیام در دیتابیس ذخیره می‌شود و ادمین آن را در پنل می‌بیند.
    بعد از ثبت موفق، Redirect می‌کنیم تا با رفرش صفحه پیام دوباره ثبت نشود
    (الگوی Post/Redirect/Get).
    """
    # اگر کاربر از صفحه یک دوره با دکمه «ثبت‌نام» به اینجا آمده باشد،
    # موضوع پیام از قبل پر می‌شود تا مجبور نباشد نام دوره را تایپ کند.
    requested_course = None
    course_slug = request.GET.get("course", "").strip()
    if course_slug:
        requested_course = Course.objects.published().filter(slug=course_slug).first()

    if request.method == "POST":
        form = ContactForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(
                request,
                "پیام شما با موفقیت ثبت شد. همکاران ما در اولین فرصت پاسخ می‌دهند.",
            )
            return redirect("core:contact")
        messages.error(request, "لطفاً خطاهای فرم را برطرف کنید.")
    else:
        initial = {}
        if requested_course:
            initial["subject"] = f"درخواست ثبت‌نام در دوره «{requested_course.title}»"
        if request.user.is_authenticated:
            initial.setdefault("full_name", request.user.get_full_name())
            initial.setdefault("mobile", request.user.mobile)
        form = ContactForm(initial=initial)

    return render(
        request,
        "core/contact.html",
        {
            "form": form,
            "requested_course": requested_course,
            "nav_active": "contact",
        },
    )


def faq(request: HttpRequest) -> HttpResponse:
    return render(
        request,
        "core/faq.html",
        {"faqs": FAQ.objects.active(), "nav_active": "faq"},
    )


def privacy(request: HttpRequest) -> HttpResponse:
    return render(request, "core/privacy.html")


def terms(request: HttpRequest) -> HttpResponse:
    return render(request, "core/terms.html")


def certificate_verify(request: HttpRequest) -> HttpResponse:
    """
    صفحه استعلام گواهی.

    در فاز ۱۸ به مدل Certificate وصل می‌شود. فعلاً فرم را نشان می‌دهد و
    اگر کدی وارد شود، پیام «در دست ساخت» می‌دهد — نه نتیجه ساختگی.
    """
    code = request.GET.get("code", "").strip()
    context = {"code": code, "searched": bool(code), "nav_active": "verify"}
    return render(request, "core/certificate_verify.html", context)


def health(request: HttpRequest) -> JsonResponse:
    """آدرس بررسی سلامت سرویس برای مانیتورینگ سرور."""
    return JsonResponse({"status": "ok"})


# ---------------------------------------------------------------------------
# صفحات خطا
# ---------------------------------------------------------------------------


def error_404(request: HttpRequest, exception=None) -> HttpResponse:
    return render(request, "errors/404.html", status=404)


def error_403(request: HttpRequest, exception=None) -> HttpResponse:
    return render(request, "errors/403.html", status=403)


def error_500(request: HttpRequest) -> HttpResponse:
    return render(request, "errors/500.html", status=500)
