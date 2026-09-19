"""Viewهای صفحات عمومی سایت."""

from types import SimpleNamespace

from django.conf import settings
from django.contrib import messages
from django.db.models import Count, Q
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse

from apps.accounts.models import InstructorProfile
from apps.courses.models import Course, CourseCategory

from .forms import ContactForm
from .throttling import CONTACT_LIMIT
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
        # فرم عمومی و بدون ورود است؛ بدون سقف، با یک اسکریپت ساده هزاران
        # پیام ثبت می‌شود و صندوق پیام‌های پشتیبانی بی‌استفاده می‌ماند.
        if CONTACT_LIMIT.is_exceeded(request):
            messages.error(
                request,
                "تعداد پیام‌های ارسالی شما زیاد بوده است. لطفاً کمی بعد دوباره تلاش کنید.",
            )
            return redirect("core:contact")

        form = ContactForm(request.POST)
        if form.is_valid():
            form.save()
            CONTACT_LIMIT.record(request)
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
    صفحه عمومی استعلام گواهی.

    دو راه ورودی دارد و هر دو به یک جا می‌رسند:

        ?code=HSE-1405-00001  ← کارفرما کد روی کاغذ را تایپ می‌کند
        ?token=…              ← کسی QR روی گواهی را اسکن کرده است

    منطق استعلام در اپ گواهی‌هاست نه اینجا؛ این View فقط ورودی را
    برمی‌دارد و نتیجه را به قالب می‌دهد. وارد کردن داخل تابع است تا
    apps.core — که بقیه اپ‌ها به آن وابسته‌اند — در بالای فایل به اپ
    گواهی‌ها وابسته نشود.
    """
    from apps.certificates.verification import is_throttled, register_lookup, verify

    code = request.GET.get("code", "").strip()
    token = request.GET.get("token", "").strip()
    searched = bool(code or token)

    if not searched:
        result = None
    elif is_throttled(request):
        # سقف استعلام پر شده است. پیام عمداً نمی‌گوید کد درست بود یا نه.
        result = SimpleNamespace(status="throttled", certificate=None, found=False)
    else:
        register_lookup(request)
        result = verify(code=code, token=token)

    context = {
        "code": code,
        "searched": searched,
        "result": result,
        "nav_active": "verify",
    }
    return render(request, "core/certificate_verify.html", context)


def robots_txt(request: HttpRequest) -> HttpResponse:
    """
    فایل robots.txt — با View ساخته می‌شود، نه به‌صورت فایل ثابت.

    دو دلیل: آدرس نقشه سایت باید کامل (با دامنه واقعی همین درخواست) نوشته
    شود، و روی سرور آزمایشی باید بتوان کل سایت را با یک تنظیم از دید
    موتورهای جست‌وجو بست.

    مسیرهای بسته‌شده، صفحه‌های شخصی و خریدند: داشبورد، سبد خرید، پرداخت،
    آزمون و گواهی. اینها نه برای موتور جست‌وجو فایده‌ای دارند و نه باید
    در نتایج دیده شوند. (بستن در robots.txt جای کنترل دسترسی را نمی‌گیرد؛
    آن کار در خود Viewها انجام می‌شود.)
    """
    sitemap_url = request.build_absolute_uri(reverse("sitemap"))

    if not settings.SEO_ALLOW_INDEXING:
        # سرور آزمایشی: هیچ صفحه‌ای نباید ایندکس شود.
        body = "User-agent: *\nDisallow: /\n"
        return HttpResponse(body, content_type="text/plain; charset=utf-8")

    disallowed = [
        "/accounts/",
        "/cart/",
        "/checkout/",
        "/orders/",
        "/payments/",
        "/exam/",
        "/certificates/",
        "/search/",
        "/protected-media/",
        f"/{settings.ADMIN_URL}/",
    ]

    lines = ["User-agent: *"]
    lines += [f"Disallow: {path}" for path in disallowed]
    lines += ["", f"Sitemap: {sitemap_url}", ""]

    return HttpResponse("\n".join(lines), content_type="text/plain; charset=utf-8")


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
