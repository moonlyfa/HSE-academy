"""
دستور کمکی محیط توسعه: ساخت یا بازنشانی حساب مدیر.

چرا این دستور را داریم؟
دستور استاندارد createsuperuser رمز را به‌صورت نامرئی می‌پرسد و اگر اشتباه تایپ
شود، هیچ راهی برای فهمیدنش نیست. این دستور رمز را به‌صورت آرگومان می‌گیرد تا
دقیقاً بدانید چه رمزی ثبت شده است.

نمونه استفاده:
    python manage.py make_admin --list
    python manage.py make_admin 09121234567 hse12345
"""

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

User = get_user_model()


class Command(BaseCommand):
    help = "ساخت یا بازنشانی حساب مدیر (فقط برای محیط توسعه)"

    def add_arguments(self, parser):
        parser.add_argument("mobile", nargs="?", help="شماره موبایل مدیر، مثل 09121234567")
        parser.add_argument("password", nargs="?", help="رمز عبور دلخواه")
        parser.add_argument(
            "--list",
            action="store_true",
            help="فقط نمایش کاربران موجود، بدون تغییر چیزی",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="اجازه اجرا در حالت Production (به‌صورت پیش‌فرض ممنوع است)",
        )

    def handle(self, *args, **options):
        if options["list"]:
            self._list_users()
            return

        mobile = options["mobile"]
        password = options["password"]

        if not mobile or not password:
            raise CommandError(
                "شماره موبایل و رمز عبور را وارد کنید.\n"
                "نمونه: python manage.py make_admin 09121234567 hse12345\n"
                "برای دیدن کاربران موجود: python manage.py make_admin --list"
            )

        # این دستور رمز را روی صفحه نمایش می‌دهد، پس در سرور واقعی مجاز نیست.
        if not settings.DEBUG and not options["force"]:
            raise CommandError(
                "این دستور فقط در محیط توسعه مجاز است. "
                "در سرور از createsuperuser یا changepassword استفاده کنید."
            )

        user = User.objects.filter(mobile=mobile).first()

        if user is None:
            user = User.objects.create_superuser(
                mobile=mobile,
                password=password,
                first_name="مدیر",
                last_name="سایت",
            )
            self.stdout.write(self.style.SUCCESS(f"کاربر مدیر جدید ساخته شد: {mobile}"))
        else:
            user.set_password(password)
            user.is_staff = True
            user.is_superuser = True
            user.is_active = True
            user.is_mobile_verified = True
            user.save()
            self.stdout.write(self.style.SUCCESS(f"رمز کاربر موجود بازنشانی شد: {mobile}"))

        self.stdout.write("")
        self.stdout.write("حالا با این اطلاعات وارد /admin/ شوید:")
        self.stdout.write(self.style.WARNING(f"  شماره موبایل : {mobile}"))
        self.stdout.write(self.style.WARNING(f"  رمز عبور     : {password}"))

    def _list_users(self):
        users = User.objects.all().order_by("created_at")

        if not users:
            self.stdout.write(self.style.WARNING("هیچ کاربری در دیتابیس وجود ندارد."))
            self.stdout.write("برای ساخت مدیر: python manage.py make_admin 09121234567 hse12345")
            return

        self.stdout.write(f"تعداد کاربران: {users.count()}")
        self.stdout.write("-" * 55)
        for user in users:
            flags = "مدیر" if user.is_staff else "کاربر عادی"
            active = "فعال" if user.is_active else "غیرفعال"
            self.stdout.write(f"  {user.mobile}  |  {flags}  |  {active}")
        self.stdout.write("-" * 55)
