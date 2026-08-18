"""
تگ‌ها و فیلترهای کمکی قالب‌ها.

آیکون‌ها را به‌صورت SVG داخل خود صفحه چاپ می‌کنیم؛ نه فایل خارجی و نه CDN.
مزیت: هیچ درخواست اضافه‌ای به شبکه زده نمی‌شود و رنگ آیکون از CSS ارث می‌برد.
"""

from django import template
from django.utils.safestring import mark_safe

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
