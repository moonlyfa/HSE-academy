"""
Manager مدل کاربر.

چون کاربر ما به‌جای username با «شماره موبایل» شناخته می‌شود، باید
UserManager پیش‌فرض Django را بازنویسی کنیم تا دستورهایی مثل
createsuperuser هم درست کار کنند.
"""

from django.contrib.auth.base_user import BaseUserManager


class UserManager(BaseUserManager):
    """ساخت کاربر عادی و کاربر مدیر بر پایه شماره موبایل."""

    use_in_migrations = True

    def _create_user(self, mobile: str, password: str | None, **extra_fields):
        if not mobile:
            raise ValueError("شماره موبایل الزامی است.")

        user = self.model(mobile=mobile, **extra_fields)
        # set_password رمز را هش می‌کند؛ هرگز رمز خام ذخیره نمی‌شود.
        user.set_password(password)
        user.full_clean(exclude=["password"])
        user.save(using=self._db)
        return user

    def create_user(self, mobile: str, password: str | None = None, **extra_fields):
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        return self._create_user(mobile, password, **extra_fields)

    def create_superuser(self, mobile: str, password: str | None = None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_active", True)
        extra_fields.setdefault("is_mobile_verified", True)
        extra_fields.setdefault("role", "super_admin")

        if extra_fields.get("is_staff") is not True:
            raise ValueError("کاربر مدیر باید is_staff=True داشته باشد.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("کاربر مدیر باید is_superuser=True داشته باشد.")

        return self._create_user(mobile, password, **extra_fields)
