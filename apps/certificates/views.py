"""
Viewهای گواهی.

سه صفحه و یک دانلود:

    my_certificates    ← گواهی‌های من در داشبورد
    certificate_issue  ← دکمه «دریافت گواهی» (فقط POST)
    certificate_detail ← نمایش گواهی برای صاحبش
    certificate_pdf    ← دانلود فایل PDF

صفحه عمومی استعلام (که QR به آن می‌رود) کار فاز ۱۸ است؛ اینجا هر چهار
مسیر فقط برای صاحب گواهی و مدیر باز است.
"""

from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.courses.enrollment import enrolled_courses
from apps.courses.models import Course

from .issue import check_eligibility, issue_certificate, user_certificates
from .models import Certificate
from .pdf import render_certificate


def _certificate_or_404(request: HttpRequest, code: str) -> Certificate:
    """
    گواهی را فقط برای صاحبش (یا مدیر) برمی‌گرداند.

    استعلام عمومی مسیر جداگانه‌ای دارد و با توکن کار می‌کند، نه با این
    آدرس؛ پس اینجا سخت‌گیری کامل درست است.
    """
    queryset = Certificate.objects.select_related("course", "user")
    if not request.user.is_staff:
        queryset = queryset.filter(user=request.user)
    return get_object_or_404(queryset, certificate_code=code)


def _site_name() -> str:
    from apps.core.models import SiteSetting

    return SiteSetting.load().site_name


@login_required
def my_certificates(request: HttpRequest) -> HttpResponse:
    """
    گواهی‌های من — و دوره‌هایی که گواهی‌شان آماده دریافت است.

    نشان دادن «آماده دریافت» کنار گواهی‌های صادرشده، همان یک قدمی است که
    دانشجو باید بردارد؛ بدون آن باید تک‌تک صفحه دوره‌ها را باز کند تا
    بفهمد کدام گواهی دارد.
    """
    certificates = user_certificates(request.user)
    issued_course_ids = set(certificates.values_list("course_id", flat=True))

    ready = []
    for enrollment in enrolled_courses(request.user):
        course = enrollment.course
        if course.pk in issued_course_ids:
            continue
        if check_eligibility(request.user, course).allowed:
            ready.append(course)

    return render(
        request,
        "certificates/my_certificates.html",
        {"certificates": certificates, "ready_courses": ready},
    )


@login_required
@require_POST
def certificate_issue(request: HttpRequest, slug: str) -> HttpResponse:
    """
    صدور گواهی.

    فقط POST، چون صدور یک کد یکتا می‌سازد که روی کاغذ چاپ می‌شود.
    شرط‌ها دوباره همین‌جا بررسی می‌شوند — دکمه‌ای که در صفحه نیست هم
    ممکن است با یک درخواست دستی صدا زده شود.
    """
    course = get_object_or_404(Course.objects.published(), slug=slug)
    eligibility = check_eligibility(request.user, course)

    if not eligibility.allowed:
        messages.error(request, eligibility.message or "امکان صدور گواهی وجود ندارد.")
        return redirect(course.get_absolute_url())

    certificate = issue_certificate(request.user, course)
    if certificate is None:
        messages.error(request, "صدور گواهی انجام نشد. لطفاً با پشتیبانی تماس بگیرید.")
        return redirect(course.get_absolute_url())

    messages.success(request, f"گواهی شما با کد {certificate.certificate_code} صادر شد.")
    return redirect(certificate.get_absolute_url())


@login_required
def certificate_detail(request: HttpRequest, code: str) -> HttpResponse:
    """صفحه گواهی: اطلاعات، وضعیت اعتبار و دکمه دانلود."""
    certificate = _certificate_or_404(request, code)

    return render(
        request,
        "certificates/certificate_detail.html",
        {
            "certificate": certificate,
            "verification_url": request.build_absolute_uri(
                certificate.get_verification_url()
            ),
        },
    )


@login_required
def certificate_pdf(request: HttpRequest, code: str) -> HttpResponse:
    """
    دانلود فایل PDF گواهی.

    فایل در لحظه ساخته می‌شود و روی دیسک ذخیره نمی‌ماند؛ این‌طور نسخه‌ای
    که دانشجو دانلود می‌کند همیشه با داده‌های همین لحظه می‌خواند — مثلاً
    گواهی باطل‌شده، مهر «باطل‌شده» دارد.
    """
    certificate = _certificate_or_404(request, code)

    content = render_certificate(
        certificate,
        verification_url=request.build_absolute_uri(certificate.get_verification_url()),
        site_name=_site_name(),
    )

    response = HttpResponse(content, content_type="application/pdf")
    response["Content-Disposition"] = (
        f'attachment; filename="{certificate.certificate_code}.pdf"'
    )
    return response
