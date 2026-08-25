"""فرم‌های بخش عمومی سایت."""

from django import forms

from apps.accounts.validators import validate_iranian_mobile

from .models import ContactMessage


class ContactForm(forms.ModelForm):
    """
    فرم تماس با ما.

    ModelForm یعنی فرم مستقیماً از روی مدل ساخته می‌شود؛ اعتبارسنجی و
    ذخیره‌سازی خودکار انجام می‌شود و کد تکراری نمی‌نویسیم.
    """

    class Meta:
        model = ContactMessage
        fields = ("full_name", "mobile", "email", "subject", "message")
        widgets = {
            "full_name": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "نام و نام خانوادگی"}
            ),
            "mobile": forms.TextInput(
                attrs={
                    "class": "form-control ltr",
                    "placeholder": "09xxxxxxxxx",
                    # این ویژگی باعث می‌شود اعداد فارسی خودکار به انگلیسی تبدیل شوند.
                    "data-digits": "en",
                    "inputmode": "numeric",
                }
            ),
            "email": forms.EmailInput(
                attrs={"class": "form-control ltr", "placeholder": "اختیاری"}
            ),
            "subject": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "موضوع پیام"}
            ),
            "message": forms.Textarea(
                attrs={"class": "form-control", "rows": 5, "placeholder": "متن پیام شما"}
            ),
        }

    def clean_mobile(self) -> str:
        mobile = (self.cleaned_data.get("mobile") or "").strip()
        validate_iranian_mobile(mobile)
        return mobile
