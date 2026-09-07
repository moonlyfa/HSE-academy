"""
سبد خرید.

سبد در Session ذخیره می‌شود، نه در دیتابیس. چرا؟

۱. کاربر مهمان هم باید بتواند دوره را در سبد بگذارد و بعد ثبت‌نام کند.
   اگر سبد به کاربر گره می‌خورد، مهمان‌ها اصلاً سبدی نداشتند.
۲. سبد داده موقتی است؛ ساختن جدول برای چیزی که ممکن است هرگز به سفارش
   تبدیل نشود، دیتابیس را بی‌دلیل سنگین می‌کند.

در Session فقط **شناسه دوره‌ها** نگه داشته می‌شود، نه قیمت. قیمت هربار از
دیتابیس خوانده می‌شود؛ وگرنه کاربر می‌توانست محتوای Session خودش را
دستکاری کند و دوره چهار میلیونی را هزار تومان بخرد.
"""

from __future__ import annotations

from dataclasses import dataclass

from django.http import HttpRequest

from apps.courses.models import Course

CART_SESSION_KEY = "cart"


@dataclass
class CartLine:
    """یک ردیف سبد خرید."""

    course: Course

    @property
    def unit_price(self) -> int:
        return self.course.price

    @property
    def final_price(self) -> int:
        return self.course.final_price

    @property
    def has_discount(self) -> bool:
        return self.course.has_discount


class Cart:
    """سبد خرید کاربر جاری."""

    def __init__(self, request: HttpRequest) -> None:
        self.session = request.session
        self.user = request.user
        self._ids: list[int] = list(self.session.get(CART_SESSION_KEY, []))

    # ------------------------------------------------------------------
    # خواندن
    # ------------------------------------------------------------------
    @property
    def course_ids(self) -> list[int]:
        return list(self._ids)

    def __contains__(self, course: Course | int) -> bool:
        course_id = course.pk if isinstance(course, Course) else int(course)
        return course_id in self._ids

    def __len__(self) -> int:
        return len(self._ids)

    @property
    def lines(self) -> list[CartLine]:
        """
        ردیف‌های سبد، به همان ترتیبی که کاربر اضافه کرده است.

        دوره‌ای که از انتشار خارج شده از سبد کنار گذاشته می‌شود — نه اینکه
        خطا بدهد. کاربر نباید بابت دوره‌ای که دیگر ارائه نمی‌شود پول بدهد.
        """
        if not self._ids:
            return []

        courses = {
            course.pk: course
            for course in Course.objects.published()
            .filter(pk__in=self._ids)
            .select_related("category", "instructor")
        }
        return [CartLine(course=courses[pk]) for pk in self._ids if pk in courses]

    @property
    def subtotal(self) -> int:
        return sum(line.final_price for line in self.lines)

    @property
    def has_only_free_courses(self) -> bool:
        lines = self.lines
        return bool(lines) and all(line.final_price == 0 for line in lines)

    # ------------------------------------------------------------------
    # تغییر
    # ------------------------------------------------------------------
    def add(self, course: Course) -> bool:
        """
        افزودن دوره به سبد. اگر از قبل بود، چیزی تغییر نمی‌کند.

        خروجی True یعنی واقعاً اضافه شد؛ برای اینکه View بتواند پیام درست
        را نشان بدهد.
        """
        if course.pk in self._ids:
            return False

        self._ids.append(course.pk)
        self._save()
        return True

    def remove(self, course_id: int) -> bool:
        if course_id not in self._ids:
            return False

        self._ids.remove(course_id)
        self._save()
        return True

    def clear(self) -> None:
        self._ids = []
        self.session.pop(CART_SESSION_KEY, None)
        self.session.modified = True

    def _save(self) -> None:
        self.session[CART_SESSION_KEY] = self._ids
        self.session.modified = True
