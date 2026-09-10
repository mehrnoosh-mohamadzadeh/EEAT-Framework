"""
توابع کمکی برای تشخیص و تبدیل تاریخ شمسی در متن فارسی.

استفاده اصلی: شاخص T6 (تازگی محتوا) در trust_extractor.py

کتابخانه پایه: jdatetime (pip install jdatetime)

نکته طراحی: منطق استخراج عدد (regex + تبدیل ارقام فارسی) عمداً از
ساخت شیء jdatetime.date جدا شده (تابع _extract_raw_jalali_parts) تا
این بخش بدون نیاز به نصب jdatetime هم قابل تست باشد.
"""

import re


PERSIAN_MONTH_NAMES = [
    "فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور",
    "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند",
]

# نگاشت ارقام فارسی/عربی به ارقام لاتین برای نرمال‌سازی قبل از regex
_DIGIT_TRANSLATION = str.maketrans(
    "۰۱۲۳۴۵۶۷۸۹" + "٠١٢٣٤٥٦٧٨٩",
    "01234567890123456789",
)

# فرمت عددی: ۱۴۰۳/۰۵/۱۲ یا 1403-05-12 (فقط سال‌های ۱۳xx و ۱۴xx پذیرفته می‌شود)
_NUMERIC_JALALI_PATTERN = re.compile(r"\b(1[34]\d{2})[/\-.](\d{1,2})[/\-.](\d{1,2})\b")

# فرمت متنی: "۱۲ مرداد ۱۴۰۳"
_MONTH_NAME_PATTERN = re.compile(
    r"\b(\d{1,2})\s+(" + "|".join(PERSIAN_MONTH_NAMES) + r")\s+(1[34]\d{2})\b"
)


def normalize_digits(text: str) -> str:
    """تبدیل ارقام فارسی/عربی موجود در متن به ارقام لاتین معمولی."""
    return text.translate(_DIGIT_TRANSLATION)


def _extract_raw_jalali_parts(text: str) -> tuple[int, int, int] | None:
    """
    جستجوی یک تاریخ شمسی در متن آزاد و بازگرداندن (سال, ماه, روز) خام
    (بدون اعتبارسنجی تقویمی و بدون ساخت شیء jdatetime).

    این تابع عمداً بدون وابستگی به jdatetime نوشته شده تا مستقل
    قابل تست باشد.
    """
    normalized = normalize_digits(text)

    match = _NUMERIC_JALALI_PATTERN.search(normalized)
    if match:
        year, month, day = (int(g) for g in match.groups())
        return (year, month, day)

    match = _MONTH_NAME_PATTERN.search(normalized)
    if match:
        day = int(match.group(1))
        month_name = match.group(2)
        year = int(match.group(3))
        month = PERSIAN_MONTH_NAMES.index(month_name) + 1
        return (year, month, day)

    return None


def find_jalali_date_in_text(text: str):
    """
    جستجوی یک تاریخ شمسی معتبر در متن و بازگرداندن شیء jdatetime.date
    (یا None اگر چیزی یافت نشد یا تاریخ یافت‌شده نامعتبر بود، مثلاً
    روز ۳۲ ام).

    نکته: import jdatetime عمداً داخل تابع (lazy) قرار گرفته تا بقیه
    این ماژول (از جمله _extract_raw_jalali_parts) بدون نیاز به نصب
    jdatetime هم قابل استفاده/تست باشد.
    """
    import jdatetime

    parts = _extract_raw_jalali_parts(text)
    if parts is None:
        return None

    year, month, day = parts
    try:
        return jdatetime.date(year, month, day)
    except ValueError:
        # تاریخ نامعتبر تقویمی (مثلاً ماه ۱۳ یا روز ۳۲) — طبق مدیریت
        # داده گمشده در فرهنگ شاخص‌ها نسخه ۳، این هم باید "نامشخص" تلقی شود
        return None


def jalali_to_gregorian(j_date):
    """تبدیل تاریخ شمسی به میلادی با متد togregorian() کتابخانه jdatetime."""
    return j_date.togregorian()


def days_since(date) -> int:
    """محاسبه تعداد روز از یک تاریخ میلادی (datetime.date) تا امروز."""
    import datetime
    return (datetime.date.today() - date).days
