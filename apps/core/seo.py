"""
تصمیم‌های سئوی صفحه‌های فهرست.

صفحه دوره‌ها با هر ترکیبی از فیلترها یک آدرس تازه می‌سازد:

    /courses/?category=safety
    /courses/?category=safety&sort=cheapest
    /courses/?level=advanced&price=free&sort=expensive

از نظر گوگل اینها ده‌ها صفحه‌ی جداگانه با محتوای تقریباً یکسان‌اند
(Duplicate Content) و اعتبار صفحه اصلیِ فهرست بین همه‌شان خرد می‌شود.

قاعده‌ای که اینجا پیاده شده:

**دسته‌بندی، صفحه واقعی است.** `/courses/?category=safety` عنوان، توضیح و
محتوای مخصوص خودش را دارد و باید ایندکس شود — این همان «صفحه دسته‌بندی»
سایت است.

**بقیه فیلترها ابزار کاربرند، نه صفحه.** مرتب‌سازی، سطح، قیمت و جست‌وجو
`noindex` می‌گیرند و آدرس اصلی‌شان (canonical) به همان فهرست بدون فیلتر
اشاره می‌کند.

**صفحه‌بندی ایندکس می‌شود** و canonical هر صفحه، خودش است؛ صفحه دوم
فهرست، محتوای متفاوتی دارد و اشاره‌دادن canonical آن به صفحه اول یعنی
گفتن دروغ به موتور جست‌وجو.
"""

from __future__ import annotations

from django.http import HttpRequest

# پارامترهایی که صفحه را «صفحه مستقل قابل ایندکس» نگه می‌دارند.
INDEXABLE_PARAMS = {"category", "page"}


def listing_seo(request: HttpRequest, base_url: str) -> dict:
    """
    آدرس اصلی و وضعیت ایندکس یک صفحه فهرست را حساب می‌کند.

    خروجی: {"canonical": "...", "noindex": True/False}
    """
    params = {key: value for key, value in request.GET.items() if value}
    extra = set(params) - INDEXABLE_PARAMS

    canonical_parts = []
    if params.get("category"):
        canonical_parts.append(f"category={params['category']}")
    if params.get("page") and params["page"] != "1":
        canonical_parts.append(f"page={params['page']}")

    canonical = base_url
    if canonical_parts and not extra:
        canonical = f"{base_url}?{'&'.join(canonical_parts)}"

    return {
        "canonical": request.build_absolute_uri(canonical),
        "noindex": bool(extra),
    }
