"""
ماژول Normalizer.

نکته: چون طبق فرهنگ شاخص‌ها نسخه ۳، اکثر فرمول‌های شاخص‌ها از قبل
در بازه [۰,۱] طراحی شده‌اند (با min/max داخل خود فرمول)، کار این
ماژول عمدتاً موارد زیر است، نه یک تبدیل ریاضی پیچیده اضافه:

  ۱. مدیریت شاخص‌های is_missing (طبق تعریف T6) — این‌ها باید از
     میانگین‌گیری آن مؤلفه کنار گذاشته شوند، نه به‌عنوان صفر لحاظ شوند.
  ۲. مدیریت شاخص‌های applicable=False (طبق تعریف E2) — این‌ها هم باید
     کنار گذاشته شوند و وزن باقی شاخص‌های همان مؤلفه به‌نسبت افزایش یابد.
  ۳. اعتبارسنجی نهایی که همه مقادیر واقعاً در بازه [۰,۱] هستند.
"""

from extractors.base import IndicatorResult


def normalize_component_scores(results: list) -> dict:
    """
    دریافت لیست IndicatorResult یک مؤلفه و بازگرداندن دیکشنری آماده
    برای ورودی Scorer.

    منطق:
      - شاخص‌هایی که applicable=False هستند (مثل E2 روی صفحه محصول)
        در excluded_indicators ثبت می‌شوند و از میانگین‌گیری مؤلفه
        کنار گذاشته می‌شوند.
      - شاخص‌هایی که is_missing=True هستند (مثل T6 وقتی تاریخی پیدا
        نشد) در missing_indicators ثبت می‌شوند و همان‌طور کنار
        گذاشته می‌شوند — نه به‌عنوان صفر لحاظ می‌شوند.
      - بقیه شاخص‌ها (usable) باید در بازه [0,1] باشند؛ در غیر این
        صورت یک ValueError صریح پرتاب می‌شود (خطای برنامه‌نویسی در
        فرمول یک Extractor، نه یک وضعیت قابل قبول).
    """
    usable_indicators = {}
    excluded_indicators = {}
    missing_indicators = {}

    for result in results:
        if not result.applicable:
            excluded_indicators[result.code] = "not_applicable"
            continue
        if result.is_missing:
            missing_indicators[result.code] = "missing_data"
            continue

        if result.value is None:
            raise ValueError(
                f"شاخص {result.code} مقدار None دارد ولی is_missing=False و "
                f"applicable=True است — این یک ناسازگاری در Extractor است."
            )
        if not (0.0 <= result.value <= 1.0):
            raise ValueError(
                f"شاخص {result.code} مقدار {result.value} خارج از بازه [0,1] دارد."
            )

        usable_indicators[result.code] = result.value

    return {
        "usable_indicators": usable_indicators,
        "excluded_indicators": excluded_indicators,
        "missing_indicators": missing_indicators,
    }
