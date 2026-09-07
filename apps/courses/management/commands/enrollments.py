"""
گزارش وضعیت دسترسی دانشجویان.

انقضای دسترسی در خود مدل و در لحظه محاسبه می‌شود، پس این دستور برای
«بستن» دسترسی لازم نیست — کارش گزارش دادن است: چند نفر دسترسی فعال
دارند، دسترسی چه کسانی این هفته تمام می‌شود، و کدام‌ها منقضی شده‌اند.

نمونه استفاده:
    python manage.py enrollments
    python manage.py enrollments --expiring 30
"""

from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db.models import Count
from django.utils import timezone

from apps.courses.models import Enrollment, EnrollmentStatus


class Command(BaseCommand):
    help = "گزارش وضعیت ثبت‌نام‌ها و دسترسی دانشجویان"

    def add_arguments(self, parser):
        parser.add_argument(
            "--expiring",
            type=int,
            default=7,
            help="نمایش دسترسی‌هایی که تا این تعداد روز آینده تمام می‌شوند (پیش‌فرض: ۷)",
        )

    def handle(self, *args, **options):
        now = timezone.now()
        active = Enrollment.objects.filter(status=EnrollmentStatus.ACTIVE)

        lifetime = active.filter(expires_at__isnull=True).count()
        valid = active.filter(expires_at__gt=now).count()
        expired = active.filter(expires_at__lte=now).count()
        suspended = Enrollment.objects.filter(
            status=EnrollmentStatus.SUSPENDED
        ).count()

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("وضعیت دسترسی دانشجویان"))
        self.stdout.write("─" * 46)
        self.stdout.write(f"  دسترسی دائمی        : {lifetime}")
        self.stdout.write(f"  دسترسی مدت‌دار معتبر : {valid}")
        self.stdout.write(f"  منقضی‌شده           : {expired}")
        self.stdout.write(f"  تعلیق‌شده           : {suspended}")

        # --- پرطرفدارترین دوره‌ها ---
        top = (
            active.values("course__title")
            .annotate(total=Count("id"))
            .order_by("-total")[:5]
        )
        if top:
            self.stdout.write("")
            self.stdout.write("بیشترین ثبت‌نام:")
            for row in top:
                self.stdout.write(f"  {row['total']:>4}  {row['course__title']}")

        # --- دسترسی‌های رو به پایان ---
        days = options["expiring"]
        soon = (
            active.filter(expires_at__gt=now, expires_at__lte=now + timedelta(days=days))
            .select_related("user", "course")
            .order_by("expires_at")
        )

        self.stdout.write("")
        if soon:
            self.stdout.write(
                self.style.WARNING(f"دسترسی‌هایی که تا {days} روز آینده تمام می‌شوند:")
            )
            for enrollment in soon:
                self.stdout.write(
                    f"  {enrollment.user.masked_mobile}  "
                    f"{enrollment.course.title}  "
                    f"({enrollment.days_remaining} روز)"
                )
        else:
            self.stdout.write(f"در {days} روز آینده هیچ دسترسی‌ای تمام نمی‌شود.")

        self.stdout.write("")
