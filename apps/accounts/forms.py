"""
فرم‌های ورود، ثبت‌نام و پروفایل.

نکته مشترک همه فرم‌ها: کاربر ایرانی ممکن است شماره موبایل را با اعداد
فارسی تایپ کند. اگر تبدیل نکنیم، سرور «۰۹۱۲…» را نامعتبر می‌بیند در حالی
که کاربر مطمئن است شماره را درست وارد کرده. این تبدیل هم در جاوااسکریپت
و هم اینجا در سمت سرور انجام می‌شود — چون به جاوااسکریپت سمت کاربر
هرگز نباید اعتماد کرد.
"""

from django import forms
from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError

from .validators import validate_iranian_mobile

User = get_user_model()

PERSIAN_TO_ENGLISH = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")


def normalize_mobile(value: str) -> str:
    """اعداد فارسی/عربی را انگلیسی می‌کند و فاصله و خط تیره را برمی‌دارد."""
    if not value:
        return ""
    cleaned = value.strip().translate(PERSIAN_TO_ENGLISH)
    for char in (" ", "-", "‌"):
        cleaned = cleaned.replace(char, "")
    # شماره‌های به شکل +989... یا 00989... یا 989... را به 09... تبدیل می‌کنیم.
    if cleaned.startswith("+98"):
        cleaned = "0" + cleaned[3:]
    elif cleaned.startswith("0098"):
        cleaned = "0" + cleaned[4:]
    elif cleaned.startswith("98") and len(cleaned) == 12:
        cleaned = "0" + cleaned[2:]
    return cleaned


class MobileFieldMixin:
    """رفتار مشترک فیلد موبایل در همه فرم‌ها."""

    def clean_mobile(self) -> str:
        mobile = normalize_mobile(self.cleaned_data.get("mobile", ""))
        validate_iranian_mobile(mobile)
        return mobile


def mobile_widget(placeholder: str = "09xxxxxxxxx") -> forms.TextInput:
    return forms.TextInput(
        attrs={
            "class": "form-control ltr text-center",
            "placeholder": placeholder,
            "data-digits": "en",
            "inputmode": "numeric",
            "autocomplete": "tel",
            "maxlength": "11",
        }
    )


def password_widget(placeholder: str, autocomplete: str) -> forms.PasswordInput:
    return forms.PasswordInput(
        attrs={
            "class": "form-control",
            "placeholder": placeholder,
            "autocomplete": autocomplete,
        }
    )


class LoginForm(MobileFieldMixin, forms.Form):
    """ورود با شماره موبایل و رمز عبور."""

    mobile = forms.CharField(label="شماره موبایل", widget=mobile_widget())
    password = forms.CharField(
        label="رمز عبور",
        widget=password_widget("رمز عبور خود را وارد کنید", "current-password"),
    )

    def __init__(self, request=None, *args, **kwargs):
        self.request = request
        self.user = None
        super().__init__(*args, **kwargs)

    def clean(self):
        cleaned = super().clean()
        mobile = cleaned.get("mobile")
        password = cleaned.get("password")

        if not mobile or not password:
            return cleaned

        self.user = authenticate(self.request, username=mobile, password=password)

        if self.user is None:
            # پیام عمداً مبهم است: نمی‌گوییم کدام‌یک اشتباه بوده تا کسی
            # نتواند با آزمون‌وخطا بفهمد چه شماره‌هایی در سایت ثبت‌نام کرده‌اند.
            raise ValidationError("شماره موبایل یا رمز عبور اشتباه است.")

        if not self.user.is_active:
            raise ValidationError(
                "این حساب کاربری غیرفعال شده است. لطفاً با پشتیبانی تماس بگیرید."
            )

        return cleaned


class RegisterForm(MobileFieldMixin, forms.Form):
    """
    ثبت‌نام کاربر جدید.

    در فاز ۴، بین ثبت این فرم و فعال شدن حساب، مرحله تأیید کد پیامکی
    اضافه می‌شود. به همین دلیل حساب با is_mobile_verified=False ساخته
    می‌شود تا بعداً بدون تغییر ساختار، مرحله تأیید اضافه شود.
    """

    first_name = forms.CharField(
        label="نام",
        max_length=50,
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "نام"}),
    )
    last_name = forms.CharField(
        label="نام خانوادگی",
        max_length=50,
        widget=forms.TextInput(
            attrs={"class": "form-control", "placeholder": "نام خانوادگی"}
        ),
    )
    mobile = forms.CharField(label="شماره موبایل", widget=mobile_widget())
    password1 = forms.CharField(
        label="رمز عبور",
        widget=password_widget("حداقل ۸ کاراکتر", "new-password"),
    )
    password2 = forms.CharField(
        label="تکرار رمز عبور",
        widget=password_widget("رمز عبور را دوباره بنویسید", "new-password"),
    )
    accept_terms = forms.BooleanField(
        label="قوانین و مقررات سایت را می‌پذیرم",
        error_messages={"required": "برای ثبت‌نام باید قوانین سایت را بپذیرید."},
    )

    def clean_mobile(self) -> str:
        mobile = super().clean_mobile()
        if User.objects.filter(mobile=mobile).exists():
            raise ValidationError(
                "این شماره موبایل قبلاً ثبت‌نام کرده است. از صفحه ورود وارد شوید."
            )
        return mobile

    def clean_password2(self) -> str:
        password1 = self.cleaned_data.get("password1")
        password2 = self.cleaned_data.get("password2")

        if password1 and password2 and password1 != password2:
            raise ValidationError("رمز عبور و تکرار آن یکسان نیستند.")

        # اعتبارسنجی قدرت رمز طبق تنظیمات پروژه (در Production فعال است).
        if password2:
            validate_password(password2)

        return password2

    def save(self) -> User:
        return User.objects.create_user(
            mobile=self.cleaned_data["mobile"],
            password=self.cleaned_data["password1"],
            first_name=self.cleaned_data["first_name"],
            last_name=self.cleaned_data["last_name"],
        )


class ProfileForm(forms.ModelForm):
    """
    ویرایش اطلاعات شخصی.

    شماره موبایل اینجا قابل تغییر نیست: موبایل نام کاربری و پایه احراز
    هویت است، پس تغییر آن باید با تأیید پیامکی انجام شود (فاز ۴).
    """

    class Meta:
        model = User
        fields = ("first_name", "last_name", "email")
        widgets = {
            "first_name": forms.TextInput(attrs={"class": "form-control"}),
            "last_name": forms.TextInput(attrs={"class": "form-control"}),
            "email": forms.EmailInput(
                attrs={"class": "form-control ltr", "placeholder": "اختیاری"}
            ),
        }


class ChangePasswordForm(forms.Form):
    """تغییر رمز عبور توسط کاربر وارد شده."""

    current_password = forms.CharField(
        label="رمز عبور فعلی",
        widget=password_widget("رمز فعلی", "current-password"),
    )
    new_password1 = forms.CharField(
        label="رمز عبور جدید",
        widget=password_widget("حداقل ۸ کاراکتر", "new-password"),
    )
    new_password2 = forms.CharField(
        label="تکرار رمز جدید",
        widget=password_widget("رمز جدید را دوباره بنویسید", "new-password"),
    )

    def __init__(self, user, *args, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)

    def clean_current_password(self) -> str:
        current = self.cleaned_data["current_password"]
        if not self.user.check_password(current):
            raise ValidationError("رمز عبور فعلی درست نیست.")
        return current

    def clean_new_password2(self) -> str:
        p1 = self.cleaned_data.get("new_password1")
        p2 = self.cleaned_data.get("new_password2")

        if p1 and p2 and p1 != p2:
            raise ValidationError("رمز جدید و تکرار آن یکسان نیستند.")

        if p2:
            validate_password(p2, self.user)

        return p2

    def save(self) -> User:
        self.user.set_password(self.cleaned_data["new_password1"])
        self.user.save(update_fields=["password", "updated_at"])
        return self.user
