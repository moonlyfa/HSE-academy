"""
تگ‌ها و فیلترهای کمکی قالب‌ها.

آیکون‌ها را به‌صورت SVG داخل خود صفحه چاپ می‌کنیم؛ نه فایل خارجی و نه CDN.
مزیت: هیچ درخواست اضافه‌ای به شبکه زده نمی‌شود و رنگ آیکون از CSS ارث می‌برد.
"""

import json
import os

from django import template
from django.conf import settings
from django.contrib.staticfiles import finders
from django.templatetags.static import static
from django.urls import reverse
from django.utils.safestring import mark_safe

from apps.core.jalali import PERSIAN_DIGITS as PERSIAN_TRANSLATION
from apps.core.jalali import to_jalali_string, to_persian_digits

register = template.Library()

# هر آیکون فقط مسیر داخلی SVG است؛ قاب بیرونی را در تگ می‌سازیم.
_ICON_PATHS = {
    "shield": '<path d="M12 2 4 5v6c0 5 3.4 9.4 8 11 4.6-1.6 8-6 8-11V5l-8-3Z"/>',
    "certificate": (
        '<circle cx="12" cy="9" r="5"/><path d="m8.5 13.5-1 7.5 4.5-2.5 4.5 2.5-1-7.5"/>'
    ),
    "users": (
        '<circle cx="9" cy="8" r="3.2"/><path d="M2.5 20a6.5 6.5 0 0 1 13 0"/>'
        '<path d="M16.5 5.5a3.2 3.2 0 0 1 0 6"/><path d="M18 14.5a6.5 6.5 0 0 1 3.5 5.5"/>'
    ),
    "video": '<rect x="2" y="5" width="14" height="14" rx="3"/><path d="m16 12 6-4v8l-6-4Z"/>',
    "download": '<path d="M12 3v12"/><path d="m7 11 5 5 5-5"/><path d="M4 20h16"/>',
    "lock": (
        '<rect x="4" y="10" width="16" height="11" rx="2.5"/>'
        '<path d="M8 10V7a4 4 0 0 1 8 0v3"/>'
    ),
    "headset": (
        '<path d="M4 13a8 8 0 0 1 16 0"/>'
        '<rect x="2.5" y="13" width="4.5" height="7" rx="2"/>'
        '<rect x="17" y="13" width="4.5" height="7" rx="2"/>'
        '<path d="M19 20v.5a2.5 2.5 0 0 1-2.5 2.5H13"/>'
    ),
    "chart": '<path d="M4 20V10"/><path d="M10 20V4"/><path d="M16 20v-7"/><path d="M22 20H2"/>',
    "calendar": (
        '<rect x="3" y="5" width="18" height="16" rx="3"/><path d="M3 10h18"/>'
        '<path d="M8 3v4"/><path d="M16 3v4"/>'
    ),
    "book": (
        '<path d="M4 4.5A2.5 2.5 0 0 1 6.5 2H20v18H6.5A2.5 2.5 0 0 0 4 22.5Z"/>'
        '<path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/>'
    ),
    "close": '<path d="M6 6l12 12"/><path d="M18 6 6 18"/>',
    "chevron-right": '<path d="m9 6 6 6-6 6"/>',
    "chevron-left": '<path d="m15 6-6 6 6 6"/>',
    "filter": '<path d="M3 5h18"/><path d="M6 12h12"/><path d="M10 19h4"/>',
    "star": '<path d="m12 3 2.6 5.6 6 .8-4.4 4.2 1.1 6L12 16.8 6.7 19.6l1.1-6L3.4 9.4l6-.8Z"/>',
    "search": '<circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/>',
    "check": '<path d="m4 12 5 5L20 6"/>',
    "arrow-left": '<path d="M19 12H5"/><path d="m11 6-6 6 6 6"/>',
    "phone": (
        '<path d="M6 3h4l2 5-2.5 1.5a12 12 0 0 0 5 5L16 12l5 2v4a2 2 0 0 1-2.2 2'
        'A17 17 0 0 1 4 5.2 2 2 0 0 1 6 3Z"/>'
    ),
    "mail": '<rect x="2.5" y="5" width="19" height="14" rx="3"/><path d="m3 7 9 6 9-6"/>',
    "location": (
        '<path d="M12 21s7-5.5 7-11a7 7 0 1 0-14 0c0 5.5 7 11 7 11Z"/>'
        '<circle cx="12" cy="10" r="2.5"/>'
    ),
    "clock": '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3.5 2"/>',
    "link": (
        '<path d="M10 13a5 5 0 0 0 7 0l2-2a5 5 0 0 0-7-7l-1 1"/>'
        '<path d="M14 11a5 5 0 0 0-7 0l-2 2a5 5 0 0 0 7 7l1-1"/>'
    ),
    "share": (
        '<circle cx="18" cy="5" r="3"/><circle cx="6" cy="12" r="3"/>'
        '<circle cx="18" cy="19" r="3"/><path d="m8.6 10.6 6.8-4.2"/>'
        '<path d="m8.6 13.4 6.8 4.2"/>'
    ),
    "linkedin": (
        '<rect x="3" y="3" width="18" height="18" rx="3"/><path d="M7.5 10.5V17"/>'
        '<path d="M11.5 17v-3.5a2.5 2.5 0 0 1 5 0V17"/>'
        '<path d="M7.5 7.5v.01"/>'
    ),
    "send": '<path d="M21 3 10.5 13.5"/><path d="M21 3 14.5 21l-4-8-8-4L21 3Z"/>',
    "graduation": (
        '<path d="m12 4 10 5-10 5L2 9l10-5Z"/><path d="M6 11.5V16c0 1.7 2.7 3 6 3s6-1.3 6-3v-4.5"/>'
    ),
}


@register.simple_tag
def icon(name: str, size: int = 24, css_class: str = "") -> str:
    """
    چاپ آیکون SVG داخل صفحه.

    نمونه استفاده در قالب:
        {% load core_extras %}
        {% icon "shield" size=32 css_class="text-primary" %}
    """
    path = _ICON_PATHS.get(name)
    if path is None:
        return ""

    return mark_safe(  # noqa: S308 — محتوا از دیکشنری ثابت خودمان می‌آید، نه ورودی کاربر.
        f'<svg class="icon {css_class}" width="{size}" height="{size}" '
        f'viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" '
        f'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" '
        f'focusable="false">{path}</svg>'
    )


@register.filter(name="jalali")
def jalali(value, with_weekday: bool = False) -> str:
    """
    تبدیل تاریخ میلادی به شمسی در قالب.

    نمونه: {{ course.start_date|jalali }}  →  ۱۱ شهریور ۱۴۰۵
    """
    if value is None:
        return ""
    return to_jalali_string(value, with_weekday=with_weekday)


@register.filter(name="fa_digits")
def fa_digits(value) -> str:
    """
    تبدیل اعداد انگلیسی به فارسی.

    نمونه: {{ course.duration_hours|fa_digits }}  →  ۴۰
    """
    return to_persian_digits(value)


@register.filter(name="toman")
def toman(value) -> str:
    """
    نمایش قیمت با جداکننده هزارگان و ارقام فارسی.

    چرا از intcomma استفاده نمی‌کنیم؟
    فیلتر intcomma به تنظیمات محلی (locale) وابسته است و در locale فارسی
    مقدار NUMBER_GROUPING برابر صفر است؛ یعنی جداکننده هزارگان اصلاً اعمال
    نمی‌شود و قیمت به شکل «۹۵۰۰۰۰» نمایش داده می‌شود که خوانا نیست.
    این فیلتر گروه‌بندی را خودش انجام می‌دهد تا مستقل از locale درست کار کند.
    """
    try:
        number = int(value)
    except (TypeError, ValueError):
        return to_persian_digits(value)
    return f"{number:,}".translate(PERSIAN_TRANSLATION)


@register.simple_tag
def static_v(path: str) -> str:
    """
    آدرس فایل استاتیک به همراه «شماره نسخه» بر اساس زمان آخرین تغییر فایل.

    چرا لازم است؟
    مرورگر فایل CSS و JS را کش می‌کند. در محیط توسعه این باعث می‌شود بعد از
    تغییر استایل، مرورگر همچنان نسخه قدیمی را نشان بدهد و فکر کنید تغییر
    اعمال نشده است. با افزودن ?v=<زمان تغییر> هر بار که فایل عوض شود،
    آدرس هم عوض می‌شود و مرورگر مجبور به دانلود نسخه جدید می‌شود.

    در Production لازم نیست: نام فایل‌ها توسط WhiteNoise هش‌دار می‌شود.
    """
    url = static(path)

    if not settings.DEBUG:
        return url

    absolute_path = finders.find(path)
    if absolute_path:
        url = f"{url}?v={int(os.path.getmtime(absolute_path))}"
    return url


# ---------------------------------------------------------------------------
# داده ساختاریافته (Structured Data / JSON-LD)
# ---------------------------------------------------------------------------
#
# گوگل علاوه بر متن صفحه، یک «خلاصه ماشین‌خوان» هم می‌خواند تا بفهمد این
# صفحه دقیقاً چیست: دوره است؟ مقاله است؟ قیمتش چند است؟ اگر این خلاصه را
# بدهیم، نتیجه جست‌وجو می‌تواند به شکل کارت غنی (Rich Result) نمایش داده شود.
#
# چرا JSON را در پایتون می‌سازیم و نه داخل قالب؟
# چون اگر عنوان دوره کاراکتری مثل کوتیشن یا < داشته باشد، نوشتن دستی JSON
# در قالب، ساختار را خراب می‌کند یا حتی راه تزریق اسکریپت باز می‌کند.
# json.dumps این کار را درست انجام می‌دهد و ما هم < را جداگانه بی‌اثر می‌کنیم.


def _json_ld(data: dict) -> str:
    """تبدیل دیکشنری پایتون به تگ <script> امن."""
    payload = json.dumps(data, ensure_ascii=False).replace("<", "\\u003c")
    return mark_safe(  # noqa: S308 — خروجی با json.dumps ساخته شده و < خنثی شده است
        f'<script type="application/ld+json">{payload}</script>'
    )


@register.simple_tag(takes_context=True)
def breadcrumb_jsonld(context, items, current: str) -> str:
    """
    نسخه ماشین‌خوانِ همان مسیر راهنمایی که کاربر می‌بیند.

    نتیجه‌اش این است که در گوگل به‌جای آدرس خام، مسیر
    «صفحه اصلی › دوره‌ها › ایمنی صنعتی» زیر عنوان نمایش داده می‌شود.
    """
    request = context.get("request")
    if request is None:
        return ""

    crumbs = [{"label": "صفحه اصلی", "url": reverse("core:home")}]
    crumbs += list(items or [])

    elements = [
        {
            "@type": "ListItem",
            "position": position,
            "name": crumb["label"],
            "item": request.build_absolute_uri(crumb["url"]),
        }
        for position, crumb in enumerate(crumbs, start=1)
    ]
    elements.append(
        {
            "@type": "ListItem",
            "position": len(elements) + 1,
            "name": current,
            "item": request.build_absolute_uri(request.path),
        }
    )

    return _json_ld(
        {
            "@context": "https://schema.org",
            "@type": "BreadcrumbList",
            "itemListElement": elements,
        }
    )


@register.simple_tag(takes_context=True)
def course_jsonld(context, course) -> str:
    """
    معرفی ماشین‌خوان یک دوره برای موتورهای جست‌وجو.

    فقط اطلاعاتی که واقعاً روی صفحه هم دیده می‌شود اینجا می‌آید؛ ادعای
    اضافه (مثل امتیاز جعلی) هم خلاف واقع است و هم باعث جریمه سئو می‌شود.
    """
    request = context.get("request")
    site = context.get("site")
    site_name = getattr(site, "site_name", settings.SITE_NAME)

    data = {
        "@context": "https://schema.org",
        "@type": "Course",
        "name": course.title,
        "description": course.meta_description or course.short_description or course.title,
        "inLanguage": "fa-IR",
        "provider": {
            "@type": "Organization",
            "name": site_name,
            "url": request.build_absolute_uri("/") if request else "",
        },
    }

    if request:
        data["url"] = request.build_absolute_uri(course.get_absolute_url())
        image = course.hero_image or course.thumbnail
        if image:
            data["image"] = request.build_absolute_uri(image.url)

    if course.instructor:
        data["instructor"] = {
            "@type": "Person",
            "name": course.instructor.display_name,
        }

    # قیمت به ریال/تومان: واحد پول ایران در استاندارد بین‌المللی IRR است.
    data["offers"] = {
        "@type": "Offer",
        "price": str(course.final_price),
        "priceCurrency": "IRR",
        "availability": (
            "https://schema.org/InStock"
            if course.registration_open
            else "https://schema.org/SoldOut"
        ),
        "category": "free" if course.is_free else "paid",
    }

    instance = {
        "@type": "CourseInstance",
        "courseMode": {
            "online_live": "online",
            "offline_recorded": "online",
            "hybrid": "blended",
        }.get(course.course_type, "online"),
    }
    if course.start_date:
        instance["startDate"] = course.start_date.isoformat()
    if course.end_date:
        instance["endDate"] = course.end_date.isoformat()
    if course.duration_hours:
        instance["courseWorkload"] = f"PT{course.duration_hours}H"
    data["hasCourseInstance"] = [instance]

    return _json_ld(data)
