"""
ماژول Scorer — ترکیب امتیاز شاخص‌ها به امتیاز نهایی.

منطق کلی (دو مرحله‌ی متفاوت — عمداً هر دو «وزنی» نیستند):
  ۱. برای هر مؤلفه (Experience/Expertise/Authority/Trust)، میانگین ساده
     (نه وزنی) شاخص‌های usable آن مؤلفه محاسبه می‌شود (شاخص‌های
     missing/excluded طبق خروجی Normalizer کنار گذاشته می‌شوند). یعنی
     همه‌ی شاخص‌های یک مؤلفه وزن مساوی دارند — رجوع به بخش «روش‌شناسی
     وزن‌دهی» در feature_dictionary_v3.md برای توجیه و پیامد این تصمیم
     (سهم هر شاخص Trust ~۳.۶٪ در برابر هر شاخص Experience ~۶.۲۵٪).
  ۲. امتیاز نهایی = ترکیب *وزنی* ۴ امتیاز مؤلفه، با وزن‌های خوانده‌شده
     از فایل config (weights_equal.yaml یا weights_ahp.yaml). فقط این
     مرحله واقعاً «وزنی» است.

طبق تصمیم مستندشده در گفتگوی پروژه: اجرای پیش‌فرض با وزن مساوی
(weights_equal.yaml) است؛ weights_ahp.yaml فقط برای تحلیل حساسیت
در فاز ارزیابی استفاده می‌شود، نه اجرای اصلی.
"""

import yaml
from dataclasses import dataclass, field


@dataclass
class PageScore:
    """نتیجه امتیازدهی نهایی یک صفحه."""
    url: str
    component_scores: dict
    final_score: float
    weights_used: str
    excluded_indicators: dict = field(default_factory=dict)
    missing_indicators: dict = field(default_factory=dict)
    indicator_details: dict = field(default_factory=dict)
    # indicator_details: {"E1": {"value": 0.6, "missing": False, "applicable": True}, ...}
    # پر می‌شود توسط pipeline.py — برای نمایش جزئیات هر شاخص در گزارش نهایی/وب‌اپ


REQUIRED_COMPONENT_KEYS = {"experience", "expertise", "authority", "trust"}


def load_weights(config_path: str) -> dict:
    """
    خواندن فایل وزن‌ها از config/*.yaml و اعتبارسنجی اینکه هر ۴
    مؤلفه اصلی وجود دارند و جمعشان (تقریباً) برابر ۱ است.
    """
    with open(config_path, "r", encoding="utf-8") as f:
        weights = yaml.safe_load(f)

    missing_keys = REQUIRED_COMPONENT_KEYS - set(weights.keys())
    if missing_keys:
        raise ValueError(f"فایل وزن {config_path} فاقد کلیدهای الزامی است: {missing_keys}")

    total = sum(weights[k] for k in REQUIRED_COMPONENT_KEYS)
    if not (0.99 <= total <= 1.01):
        raise ValueError(f"جمع وزن‌ها در {config_path} برابر {total} است، نه ۱ (با تلورانس ۰.۰۱)")

    return weights


def compute_component_score(usable_indicators: dict) -> float | None:
    """
    محاسبه امتیاز یک مؤلفه: میانگین ساده شاخص‌های usable آن.

    اگر همه شاخص‌های یک مؤلفه missing/excluded باشند (حالت نادر ولی
    ممکن)، None برمی‌گرداند تا Scorer بتواند این مؤلفه را هم از
    ترکیب نهایی کنار بگذارد (با افزایش نسبی وزن بقیه مؤلفه‌ها).
    """
    if not usable_indicators:
        return None
    return sum(usable_indicators.values()) / len(usable_indicators)


def compute_final_score(component_scores: dict, weights: dict) -> float:
    """
    ترکیب وزنی امتیاز مؤلفه‌ها.

    اگر یک یا چند مؤلفه None باشند (هیچ شاخص usable‌ای نداشتند)،
    وزن آن‌ها از محاسبه کنار گذاشته می‌شود و وزن باقی مؤلفه‌ها به‌نسبت
    normalize می‌شود — تا هرگز صفر ساختگی به یک مؤلفه بدون داده
    نسبت داده نشود.
    """
    available = {k: v for k, v in component_scores.items() if v is not None}
    if not available:
        raise ValueError("هیچ مؤلفه‌ای امتیاز قابل‌محاسبه‌ای نداشت؛ امتیاز نهایی قابل تعیین نیست.")

    weight_key_map = {
        "Experience": "experience",
        "Expertise": "expertise",
        "Authoritativeness": "authority",
        "Trustworthiness": "trust",
    }

    raw_weight_sum = sum(weights[weight_key_map[k]] for k in available)
    final_score = sum(
        available[k] * weights[weight_key_map[k]] for k in available
    ) / raw_weight_sum

    return final_score
