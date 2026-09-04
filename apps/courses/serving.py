"""
تحویل فایل‌های محافظت‌شده به کاربرِ مجاز.

دو روش وجود دارد و هر دو پشتیبانی می‌شوند:

۱. حالت توسعه (پیش‌فرض): خود Django فایل را می‌خواند و می‌فرستد.
   ساده است و به تنظیم اضافه نیاز ندارد، اما برای هر ویدیو یک Worker
   پایتون تا پایان دانلود مشغول می‌ماند.

۲. حالت Production با Nginx (X-Accel-Redirect): Django فقط مجوز را بررسی
   می‌کند و به Nginx می‌گوید «این فایل را بفرست». پایتون بلافاصله آزاد
   می‌شود و ارسال فایل را وب‌سرور — که برای همین کار ساخته شده — انجام
   می‌دهد. برای فعال کردن، در فایل .env بنویسید:

       USE_X_ACCEL_REDIRECT=True

   و در Nginx این بلاک را اضافه کنید (internal یعنی این مسیر مستقیماً از
   بیرون قابل صدا زدن نیست و فقط با دستور Django کار می‌کند):

       location /protected-internal/ {
           internal;
           alias /srv/hse/protected_media/;
       }
"""

from __future__ import annotations

import mimetypes
from urllib.parse import quote

from django.conf import settings
from django.core.files.storage import Storage
from django.http import FileResponse, Http404, HttpResponse


def serve_protected_file(
    storage: Storage,
    name: str,
    *,
    as_attachment: bool = False,
    download_name: str = "",
) -> HttpResponse:
    """فایل را با روش مناسبِ محیط جاری تحویل می‌دهد."""
    if not name or not storage.exists(name):
        raise Http404("فایل مورد نظر پیدا نشد.")

    filename = download_name or name.rsplit("/", 1)[-1]
    content_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"

    if settings.USE_X_ACCEL_REDIRECT:
        response = HttpResponse(content_type=content_type)
        response["X-Accel-Redirect"] = f"{settings.X_ACCEL_REDIRECT_PREFIX}{quote(name)}"
        response["Content-Disposition"] = _disposition(as_attachment, filename)
        return response

    response = FileResponse(
        storage.open(name, "rb"),
        content_type=content_type,
        as_attachment=as_attachment,
        filename=filename,
    )
    return response


def _disposition(as_attachment: bool, filename: str) -> str:
    """
    نام فایل فارسی در هدر HTTP باید کدگذاری شود.

    بدون این کار، مرورگر نام فایل «جزوه ایمنی.pdf» را خراب نشان می‌دهد یا
    اصلاً هدر را نامعتبر می‌داند.
    """
    kind = "attachment" if as_attachment else "inline"
    return f"{kind}; filename*=UTF-8''{quote(filename)}"
