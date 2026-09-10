"""
کلاس پایه مشترک برای هر ۴ ماژول Extractor.

هر Extractor (Experience/Expertise/Authority/Trust) این کلاس را
گسترش می‌دهد تا رابط یکسانی داشته باشند و ماژول Normalizer بتواند
خروجی همه آن‌ها را به شکل یکسان پردازش کند.
"""

from dataclasses import dataclass, field


@dataclass
class IndicatorResult:
    """
    نتیجه محاسبه یک شاخص منفرد (مثلاً E1 یا T6).

    value:      مقدار خام محاسبه‌شده (معمولاً در بازه [0,1])
    is_missing: True اگر داده لازم برای این شاخص یافت نشد
                (مثلاً T6 وقتی هیچ تاریخی پیدا نشود — طبق تعریف
                فرهنگ شاخص‌ها نسخه ۳)
    applicable: False اگر این شاخص برای این نوع صفحه اصلاً معنا
                ندارد (مثلاً E2 برای صفحات محصول — طبق تعریف
                فرهنگ شاخص‌ها نسخه ۳)
    """
    code: str                 # مثل "E1", "T6", "X5"
    value: float | None
    is_missing: bool = False
    applicable: bool = True
    raw_details: dict = field(default_factory=dict)  # برای دیباگ/گزارش


class BaseExtractor:
    """رابط مشترک همه Extractor ها."""

    component_name: str = ""  # "Experience" / "Expertise" / "Authoritativeness" / "Trustworthiness"

    def extract(self, parsed_page) -> list[IndicatorResult]:
        """
        محاسبه همه شاخص‌های این مؤلفه برای یک صفحه پارس‌شده.

        باید در هر زیرکلاس بازنویسی شود و لیستی از IndicatorResult
        برای هر شاخص مربوط به آن مؤلفه برگرداند.
        """
        raise NotImplementedError
