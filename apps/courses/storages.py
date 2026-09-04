"""
محل ذخیره فایل‌های آموزشی محافظت‌شده.

FileSystemStorage معمولی فایل‌ها را در media/ می‌گذارد که با آدرس مستقیم
برای همه باز است. این کلاس همان کار را در پوشه‌ای بیرون از دسترس وب انجام
می‌دهد؛ یعنی حتی اگر کسی مسیر فایل را حدس بزند، وب‌سرور آن را تحویل نمی‌دهد.

تحویل فایل فقط از راه Viewهای اپ دوره‌ها انجام می‌شود که اول بررسی می‌کنند
کاربر اجازه دیدن آن درس را دارد یا نه.
"""

import os

from django.conf import settings
from django.core.files.storage import FileSystemStorage
from django.utils.deconstruct import deconstructible


@deconstructible
class ProtectedStorage(FileSystemStorage):
    """
    ذخیره‌ساز فایل‌های خصوصی دوره.

    چرا location به‌جای مقدار ثابت، هربار از تنظیمات خوانده می‌شود؟
    FileSystemStorage مسیر را فقط یک‌بار (هنگام ساخته شدن) می‌خواند و در
    حافظه نگه می‌دارد. چون این ذخیره‌ساز موقع بارگذاری مدل ساخته می‌شود،
    مسیر برای همیشه قفل می‌شد و تغییر PROTECTED_MEDIA_ROOT — چه در سرور و
    چه در تست‌ها — بی‌اثر می‌ماند. با خواندن هربار، تنظیمات واقعاً کار می‌کند.

    base_url عمداً به آدرسی اشاره می‌کند که فقط برای مدیران باز است
    (نه برای عموم). دلیلش این است که پنل مدیریت جنگو برای هر FileField
    یک لینک می‌سازد و اگر url() خطا بدهد، صفحه ویرایش درس اصلاً باز نمی‌شود.
    """

    @property
    def base_location(self) -> str:
        return str(settings.PROTECTED_MEDIA_ROOT)

    @property
    def location(self) -> str:
        return os.path.abspath(self.base_location)

    @property
    def base_url(self) -> str:
        return "/protected-media/"


protected_storage = ProtectedStorage()


def lesson_video_path(instance, filename: str) -> str:
    """ویدیوها بر اساس دوره دسته‌بندی می‌شوند تا پیدا کردنشان روی سرور ساده باشد."""
    return f"lessons/{instance.section.course_id}/videos/{filename}"


def lesson_attachment_path(instance, filename: str) -> str:
    return f"lessons/{instance.lesson.section.course_id}/files/{filename}"
