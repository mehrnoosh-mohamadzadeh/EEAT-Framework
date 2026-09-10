# -*- coding: utf-8 -*-
"""
بارگذاری آستانه‌های عددی از config/settings.yaml.

قبل از این ماژول، آستانه‌هایی مثل K=15 در E2 یا سقف ۷۳۰ روزه در T6
به‌صورت ثابت (hardcoded) داخل هر extractor تکرار شده بودند، در حالی که
همان مقادیر در config/settings.yaml هم مستند شده بودند — یعنی یک منبع
حقیقت نداشتیم و اگر کسی عدد را در yaml عوض می‌کرد، هیچ اثری روی محاسبه
نداشت. این ماژول settings.yaml را تنها منبع این آستانه‌ها می‌کند.

عمداً fallback خاموش ندارد: اگر فایل یا کلید مورد نیاز نباشد، خطای
صریح می‌دهد. چون این اعداد مبنای محاسبه‌ی امتیاز نهایی پایان‌نامه‌اند،
بهتر است برنامه متوقف شود تا این‌که بی‌صدا یک مقدار پیش‌فرض اشتباه
استفاده کند.
"""

import os
import yaml

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SETTINGS_PATH = os.path.join(PROJECT_ROOT, "config", "settings.yaml")

_settings_cache = None


def load_settings(config_path: str = SETTINGS_PATH) -> dict:
    """خواندن کل فایل settings.yaml (با کش، چون در طول یک اجرا تغییر نمی‌کند)."""
    global _settings_cache
    if _settings_cache is not None:
        return _settings_cache
    with open(config_path, "r", encoding="utf-8") as f:
        settings = yaml.safe_load(f)
    _settings_cache = settings
    return settings


def get_threshold(key: str):
    """
    خواندن یک آستانه از بخش thresholds در config/settings.yaml.
    مرجع مقادیر و توجیه هرکدام: feature_dictionary_v3.md.
    """
    settings = load_settings()
    thresholds = settings.get("thresholds", {})
    if key not in thresholds:
        raise KeyError(
            f"آستانه '{key}' در config/settings.yaml زیر thresholds تعریف نشده است."
        )
    return thresholds[key]


def reset_cache_for_tests():
    """فقط برای tests: کش را خالی می‌کند تا فایل yaml دوباره خوانده شود."""
    global _settings_cache
    _settings_cache = None
