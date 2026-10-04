"""فرم ارسال رسید کارت به کارت."""

from __future__ import annotations

from django import forms
from django.core.exceptions import ValidationError

from .services.card_transfer import MAX_RECEIPTS, compress_receipt

_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")


class MultipleImageInput(forms.ClearableFileInput):
    allow_multiple_selected = True


class MultipleImageField(forms.FileField):
    """چند فایل در یک فیلد؛ هر کدام جداگانه بررسی و فشرده می‌شود."""

    widget = MultipleImageInput

    def clean(self, data, initial=None):
        files = data if isinstance(data, (list, tuple)) else ([data] if data else [])
        if not files:
            raise ValidationError("عکس رسید را انتخاب کنید.")
        if len(files) > MAX_RECEIPTS:
            raise ValidationError(f"حداکثر {MAX_RECEIPTS} عکس می‌توانید بفرستید.".translate(
                str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")
            ))
        return [compress_receipt(super(MultipleImageField, self).clean(f, initial)) for f in files]


class CardTransferForm(forms.Form):
    receipts = MultipleImageField(
        label="عکس یا اسکرین‌شات رسید",
        help_text="JPG، PNG یا WEBP؛ حداکثر سه عکس (اگر مبلغ را در چند مرحله واریز کرده‌اید).",
        widget=MultipleImageInput(
            attrs={"accept": "image/jpeg,image/png,image/webp", "class": "form-control"}
        ),
    )
    payer_card_last4 = forms.CharField(
        label="چهار رقم آخر کارتی که از آن واریز کردید",
        max_length=8,
        widget=forms.TextInput(
            attrs={
                "class": "form-control ltr",
                "inputmode": "numeric",
                "autocomplete": "off",
                "dir": "ltr",
                "placeholder": "1234",
            }
        ),
    )
    tracking_code = forms.CharField(
        label="شماره پیگیری (اختیاری)",
        max_length=40,
        required=False,
        widget=forms.TextInput(attrs={"class": "form-control ltr", "dir": "ltr", "autocomplete": "off"}),
    )
    payer_note = forms.CharField(
        label="توضیح (اختیاری)",
        max_length=300,
        required=False,
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 2}),
    )

    def clean_payer_card_last4(self) -> str:
        value = self.cleaned_data["payer_card_last4"].translate(_DIGITS).strip()
        if not (len(value) == 4 and value.isdigit()):
            raise ValidationError("چهار رقم آخر کارت را وارد کنید.")
        return value

    def clean_tracking_code(self) -> str:
        return self.cleaned_data["tracking_code"].translate(_DIGITS).strip()
