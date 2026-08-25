"""
تبدیل تاریخ میلادی به شمسی (هجری خورشیدی).

چرا کتابخانه خارجی نصب نکردیم؟
این الگوریتم کوتاه، دقیق و بدون وابستگی است. برای سایتی که قرار است روی
زیرساخت داخلی مستقر شود، هر وابستگی کمتر یعنی یک نقطه شکست کمتر.
صحت خروجی با تست‌های apps/core/tests.py بررسی می‌شود.
"""

from datetime import date

# تعداد روزهای گذشته از ابتدای سال میلادی تا ابتدای هر ماه (سال غیرکبیسه)
_GREGORIAN_DAYS_IN_MONTH = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334]

PERSIAN_MONTHS = [
    "فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور",
    "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند",
]

PERSIAN_WEEKDAYS = ["دوشنبه", "سه‌شنبه", "چهارشنبه", "پنجشنبه", "جمعه", "شنبه", "یکشنبه"]

PERSIAN_DIGITS = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")


def gregorian_to_jalali(gy: int, gm: int, gd: int) -> tuple[int, int, int]:
    """
    تاریخ میلادی را به (سال، ماه، روز) شمسی تبدیل می‌کند.

    مثال: (2026, 3, 21) → (1405, 1, 1)  یعنی اول فروردین ۱۴۰۵
    """
    if gy > 1600:
        jy = 979
        gy -= 1600
    else:
        jy = 0
        gy -= 621

    # اگر از اسفند گذشته باشیم، سال بعد میلادی برای محاسبه کبیسه لحاظ می‌شود.
    gy2 = gy + 1 if gm > 2 else gy

    days = (
        365 * gy
        + (gy2 + 3) // 4
        - (gy2 + 99) // 100
        + (gy2 + 399) // 400
        - 80
        + gd
        + _GREGORIAN_DAYS_IN_MONTH[gm - 1]
    )

    # هر ۳۳ سال شمسی برابر ۱۲۰۵۳ روز است.
    jy += 33 * (days // 12053)
    days %= 12053

    jy += 4 * (days // 1461)
    days %= 1461

    if days > 365:
        jy += (days - 1) // 365
        days = (days - 1) % 365

    # شش ماه اول سال شمسی ۳۱ روزه و بقیه ۳۰ روزه‌اند.
    if days < 186:
        jm = 1 + days // 31
        jd = 1 + days % 31
    else:
        jm = 7 + (days - 186) // 30
        jd = 1 + (days - 186) % 30

    return jy, jm, jd


def to_jalali_string(value: date, with_weekday: bool = False) -> str:
    """
    تاریخ را به رشته فارسی خوانا تبدیل می‌کند.

    نمونه خروجی: «۱۱ شهریور ۱۴۰۵»
    """
    if value is None:
        return ""

    jy, jm, jd = gregorian_to_jalali(value.year, value.month, value.day)
    text = f"{jd} {PERSIAN_MONTHS[jm - 1]} {jy}"

    if with_weekday:
        text = f"{PERSIAN_WEEKDAYS[value.weekday()]} {text}"

    return text.translate(PERSIAN_DIGITS)


def to_persian_digits(value) -> str:
    """اعداد انگلیسی داخل یک رشته را به فارسی تبدیل می‌کند."""
    return str(value).translate(PERSIAN_DIGITS)
