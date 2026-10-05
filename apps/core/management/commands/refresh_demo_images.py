"""
تصویرهای نمونه (اسلایدر و دوره‌ها) را با رنگ‌های فعلی برند دوباره می‌سازد.

    python manage.py refresh_demo_images

seed_demo تصویر نمونه را فقط یک بار می‌سازد تا عکس واقعی مدیر بازنویسی
نشود. برای همین بعد از عوض شدن رنگ‌های برند، تصویرهای نمونه قدیمی (سبز
و آبی) سر جایشان می‌ماندند. این دستور فقط تصویرهایی را عوض می‌کند که
نامشان با «demo-» شروع می‌شود و هنوز نسخه برند فعلی نیستند؛ عکسی که مدیر
آپلود کرده هرگز دست نمی‌خورد.

اجرای دوباره بی‌خطر است: وقتی همه به‌روز باشند کاری انجام نمی‌دهد. run.bat
آن را در هر اجرا صدا می‌زند.
"""

from __future__ import annotations

from pathlib import PurePosixPath

from django.core.management.base import BaseCommand

from apps.core.models import HeroSlide
from apps.courses.models import Course

from .seed_demo import (
    CATEGORY_COLORS,
    ONLINE_SLIDES,
    PLACEHOLDER_PREFIX,
    SLIDES,
    Command as SeedCommand,
)

DEFAULT_COLORS = ((136, 38, 27), (35, 31, 32))


def is_outdated_placeholder(field) -> bool:
    """تصویر نمونه‌ای که seed_demo با رنگ‌های قبلی ساخته است."""
    if not field:
        return False
    name = PurePosixPath(field.name).name
    return name.startswith("demo-") and not name.startswith(PLACEHOLDER_PREFIX)


class Command(BaseCommand):
    help = "تصویرهای نمونه قدیمی را با رنگ‌های برند فعلی دوباره می‌سازد."

    def handle(self, *args, **options):
        painter = SeedCommand()
        slide_colors = {title: (start, end) for title, start, end, _ in SLIDES + ONLINE_SLIDES}
        refreshed = 0

        for index, slide in enumerate(HeroSlide.objects.order_by("order", "pk"), start=1):
            if not is_outdated_placeholder(slide.image):
                continue
            start, end = slide_colors.get(slide.title, DEFAULT_COLORS)
            slide.image.delete(save=False)
            slide.image.save(
                f"{PLACEHOLDER_PREFIX}slide-{index}.jpg",
                painter._make_gradient_image(1920, 650, start, end, "SAMPLE"),
                save=True,
            )
            refreshed += 1

        for course in Course.objects.select_related("category"):
            if not is_outdated_placeholder(course.thumbnail):
                continue
            slug = course.category.slug if course.category else ""
            start, end = CATEGORY_COLORS.get(slug, DEFAULT_COLORS)
            course.thumbnail.delete(save=False)
            course.thumbnail.save(
                f"{PLACEHOLDER_PREFIX}{course.slug}.jpg",
                painter._make_gradient_image(800, 450, start, end, "COURSE"),
                save=True,
            )
            refreshed += 1

        if refreshed:
            self.stdout.write(self.style.SUCCESS(f"✓ {refreshed} تصویر نمونه با رنگ‌های برند به‌روز شد."))
        else:
            self.stdout.write("تصویر نمونه قدیمی‌ای پیدا نشد.")
