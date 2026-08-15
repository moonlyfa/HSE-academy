from django.apps import AppConfig


class CoreConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    # چون اپ داخل پوشه apps/ است، مسیر کامل آن را می‌نویسیم.
    name = "apps.core"
    # label کوتاه باعث می‌شود نام جدول‌های دیتابیس core_xxx شود، نه apps_core_xxx.
    label = "core"
    verbose_name = "هسته سایت"
