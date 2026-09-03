"""
ساخت گروه‌های نقش و تعیین دسترسی‌های هر گروه.

چرا گروه و نه فیلد role؟
فیلد role فقط یک برچسب برای نمایش است. کنترل دسترسی واقعی باید با سیستم
استاندارد Permission جنگو انجام شود، چون پنل مدیریت، دکوریتورها و
قالب‌ها همگی با همان سیستم کار می‌کنند.

اجرا:
    python manage.py setup_groups

این دستور بی‌خطر است: چند بار اجرا کردنش مشکلی ایجاد نمی‌کند و
دسترسی‌های دستی اضافه‌شده به کاربران را پاک نمی‌کند.
"""

from django.contrib.auth.models import Group, Permission
from django.core.management.base import BaseCommand
from django.db import transaction

# برای هر گروه: کدام مدل‌ها و با چه سطحی
# "full"     → افزودن، مشاهده، ویرایش، حذف
# "edit"     → افزودن، مشاهده، ویرایش (بدون حذف)
# "view"     → فقط مشاهده
GROUP_PERMISSIONS: dict[str, dict[str, list[str]]] = {
    "مدیر": {
        "full": [
            "courses.course",
            "courses.coursecategory",
            "core.heroslide",
            "core.feature",
            "core.faq",
            "core.testimonial",
            "core.partner",
            "accounts.instructorprofile",
        ],
        "edit": ["core.sitesetting", "accounts.user"],
        "view": ["core.contactmessage"],
    },
    "مدرس": {
        # مدرس فقط محتوای آموزشی را می‌بیند و ویرایش می‌کند.
        # کنترل اینکه «فقط دوره‌های خودش» را ببیند، در فاز ۱۴ اضافه می‌شود.
        "edit": ["courses.course"],
        "view": ["courses.coursecategory", "accounts.instructorprofile"],
    },
    "مدیر محتوا": {
        "full": [
            "core.heroslide",
            "core.feature",
            "core.faq",
            "core.testimonial",
            "core.partner",
        ],
        "edit": ["courses.course", "courses.coursecategory", "core.sitesetting"],
    },
    "پشتیبانی": {
        "edit": ["core.contactmessage"],
        "view": ["accounts.user", "courses.course", "courses.coursecategory"],
    },
    "مالی": {
        # مدل‌های سفارش و پرداخت در فاز ۱۱ اضافه می‌شوند و اینجا وصل خواهند شد.
        "view": ["accounts.user", "courses.course"],
    },
    "دانشجو": {
        # دانشجو اصلاً به پنل مدیریت دسترسی ندارد؛ گروه فقط برای
        # دسته‌بندی کاربران و استفاده در منطق برنامه است.
    },
}

ACTIONS = {
    "full": ("add", "view", "change", "delete"),
    "edit": ("add", "view", "change"),
    "view": ("view",),
}


class Command(BaseCommand):
    help = "ساخت گروه‌های نقش و تعیین دسترسی‌های استاندارد هر گروه"

    @transaction.atomic
    def handle(self, *args, **options):
        for group_name, levels in GROUP_PERMISSIONS.items():
            group, created = Group.objects.get_or_create(name=group_name)

            permissions = []
            missing = []

            for level, models in levels.items():
                for model_path in models:
                    app_label, model_name = model_path.split(".")
                    for action in ACTIONS[level]:
                        codename = f"{action}_{model_name}"
                        permission = Permission.objects.filter(
                            codename=codename,
                            content_type__app_label=app_label,
                        ).first()

                        if permission:
                            permissions.append(permission)
                        else:
                            missing.append(f"{app_label}.{codename}")

            group.permissions.set(permissions)

            state = "ساخته شد" if created else "بروزرسانی شد"
            self.stdout.write(
                self.style.SUCCESS(f"✓ گروه «{group_name}» {state} — {len(permissions)} دسترسی")
            )

            if missing:
                self.stdout.write(
                    self.style.WARNING(f"  دسترسی‌های موجود نبود: {', '.join(missing)}")
                )

        self.stdout.write("")
        self.stdout.write("برای دادن نقش به کاربر: پنل مدیریت ← کاربران ← انتخاب کاربر ←")
        self.stdout.write("بخش «دسترسی‌ها» ← گروه مورد نظر را اضافه کنید.")
        self.stdout.write(
            self.style.WARNING(
                "یادآوری: کاربر برای ورود به پنل مدیریت باید تیک "
                "«دسترسی به پنل مدیریت» را هم داشته باشد."
            )
        )
