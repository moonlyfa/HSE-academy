"""
افزودن اسلاگ به پروفایل مدرس (برای صفحه عمومی هر مدرس).

چرا سه مرحله؟ چون فیلد باید یکتا (unique) باشد، اما رکوردهای موجود در
دیتابیس هنوز اسلاگ ندارند. اگر مستقیم unique اضافه کنیم، همه رکوردها
مقدار خالی می‌گیرند و با هم تداخل پیدا می‌کنند. پس:
    ۱) فیلد را بدون unique اضافه می‌کنیم
    ۲) برای رکوردهای موجود اسلاگ می‌سازیم
    ۳) حالا که همه مقدار یکتا دارند، unique را فعال می‌کنیم
"""

from django.db import migrations, models
from django.utils.text import slugify


def fill_slugs(apps, schema_editor):
    InstructorProfile = apps.get_model("accounts", "InstructorProfile")

    used: set[str] = set()
    for instructor in InstructorProfile.objects.all().order_by("pk"):
        base = slugify(instructor.display_name, allow_unicode=True) or f"instructor-{instructor.pk}"
        candidate = base
        counter = 2
        while candidate in used:
            candidate = f"{base}-{counter}"
            counter += 1
        used.add(candidate)

        instructor.slug = candidate
        instructor.save(update_fields=["slug"])


def clear_slugs(apps, schema_editor):
    """برگشت به عقب: کاری لازم نیست، فیلد کلاً حذف می‌شود."""


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0004_identityverification"),
    ]

    operations = [
        migrations.AddField(
            model_name="instructorprofile",
            name="slug",
            field=models.SlugField(
                allow_unicode=True,
                blank=True,
                default="",
                help_text="در آدرس صفحه مدرس استفاده می‌شود. خالی بگذارید تا خودکار ساخته شود.",
                max_length=140,
                verbose_name="نشانی یکتا (اسلاگ)",
            ),
            preserve_default=False,
        ),
        migrations.RunPython(fill_slugs, clear_slugs),
        migrations.AlterField(
            model_name="instructorprofile",
            name="slug",
            field=models.SlugField(
                allow_unicode=True,
                blank=True,
                help_text="در آدرس صفحه مدرس استفاده می‌شود. خالی بگذارید تا خودکار ساخته شود.",
                max_length=140,
                unique=True,
                verbose_name="نشانی یکتا (اسلاگ)",
            ),
        ),
    ]
