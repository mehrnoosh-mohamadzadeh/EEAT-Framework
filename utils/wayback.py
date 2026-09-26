# -*- coding: utf-8 -*-
"""
یکپارچه‌سازی با Wayback Machine (Internet Archive) CDX API — برای
تخمین تاریخ آخرین تغییر واقعی محتوای یک صفحه، وقتی خودِ صفحه هیچ
تاریخ قابل‌استخراجی ندارد (نه در JSON-LD schema، نه در متن فارسی).

این مستقیماً محدودیت «فقط به HTML یک صفحه دسترسی داریم» را برای T6
کاهش می‌دهد — بدون این ماژول، نبود تاریخ روی خودِ صفحه یعنی T6 همیشه
is_missing است، حتی اگر صفحه در واقع به‌روز باشد یا سال‌ها بدون تغییر
مانده باشد.

مرجع رسمی API: https://github.com/internetarchive/wayback/tree/master/wayback-cdx-server (🟢)

روش تخمین (🔵 تصمیم طراحی این پروژه، نه استاندارد رسمی Internet Archive):
CDX API علاوه بر timestamp هر بار آرشیوشدن یک URL، یک "digest" (هش
محتوا) هم برمی‌گرداند. اگر بین دو بار آرشیوشدن، digest عوض شود، یعنی
محتوا واقعاً تغییر کرده — نه فقط اینکه Wayback دوباره همان صفحه را
کراول کرده. با پیدا کردن قدیمی‌ترین timestampی که digest آن با
جدیدترین digest شناخته‌شده یکی است، یک تخمین معقول از «آخرین تغییر
واقعی محتوا» به دست می‌آید.

⚠️ محدودیت صادقانه (برای فصل محدودیت‌ها): این یک تخمین است، نه
اندازه‌گیری قطعی. دقتش وابسته به تراکم کراول Wayback از آن صفحه‌ی
خاص است — صفحات کم‌بازدید ممکن است ماه‌ها بین دو کراول فاصله داشته
باشند و یک تغییر واقعی را از دست بدهند. هم‌چنین اگر صفحه هرگز در
Wayback آرشیو نشده باشد (مثلاً بلاک robots.txt یا خیلی جدید بودن)،
این fallback هم چیزی برنمی‌گرداند.

این ماژول عمداً هیچ Exception ای به بیرون درز نمی‌دهد: هر خطای شبکه/
پارس باعث برگرداندن None/لیست خالی می‌شود، نه کرش برنامه — چون این
یک fallback اختیاری است (کنترل‌شده با تنظیم external_data_sources در
config/settings.yaml)، نباید کل اجرای ابزار را وابسته به در دسترس
بودن archive.org کند.
"""

import datetime

import requests

CDX_API_URL = "http://web.archive.org/cdx/search/cdx"
DEFAULT_TIMEOUT_SECONDS = 10


def get_capture_history(url: str, timeout: int = DEFAULT_TIMEOUT_SECONDS) -> list:
    """
    خواندن تاریخچه‌ی کراول‌های موفق (statuscode=200) یک URL از Wayback
    CDX API، مرتب‌شده از قدیم به جدید.

    خروجی: لیستی از dict با کلیدهای "timestamp" (رشته ۱۴ رقمی
    yyyyMMddHHmmss) و "digest" (هش محتوا). در صورت هر خطای شبکه/پارس
    یا نبود هیچ رکوردی، لیست خالی برمی‌گرداند.
    """
    params = {
        "url": url,
        "output": "json",
        "fl": "timestamp,digest,statuscode",
        "filter": "statuscode:200",
        "collapse": "digest",
    }
    try:
        response = requests.get(CDX_API_URL, params=params, timeout=timeout)
        response.raise_for_status()
        rows = response.json()
    except Exception:
        # هر خطایی (اتصال، timeout، JSON نامعتبر، ...) — این fallback
        # اختیاری است، نباید کل T6 یا کل اجرای ابزار را متوقف کند
        return []

    if not rows or not isinstance(rows, list) or len(rows) < 2:
        return []

    header = rows[0]
    try:
        ts_idx = header.index("timestamp")
        digest_idx = header.index("digest")
    except (ValueError, AttributeError, TypeError):
        return []

    history = []
    for row in rows[1:]:
        try:
            history.append({"timestamp": row[ts_idx], "digest": row[digest_idx]})
        except (IndexError, TypeError):
            continue

    history.sort(key=lambda item: item["timestamp"])
    return history


def estimate_last_content_change(url: str, timeout: int = DEFAULT_TIMEOUT_SECONDS):
    """
    تخمین تاریخ آخرین تغییر واقعی محتوا (نه صرفاً آخرین کراول Wayback)
    با مقایسه‌ی digest ها — رجوع به توضیح روش در بالای فایل.

    برمی‌گرداند datetime.date یا None (اگر هیچ تاریخچه‌ای در Wayback
    نبود یا خطایی رخ داد).
    """
    history = get_capture_history(url, timeout=timeout)
    if not history:
        return None

    latest_digest = history[-1]["digest"]
    for item in history:
        if item["digest"] == latest_digest:
            return _parse_wayback_timestamp(item["timestamp"])
    return None


def _parse_wayback_timestamp(ts):
    """تبدیل timestamp ۱۴ رقمی Wayback (yyyyMMddHHmmss) به datetime.date؛ در خطا None."""
    if not isinstance(ts, str):
        return None
    try:
        return datetime.datetime.strptime(ts[:14], "%Y%m%d%H%M%S").date()
    except ValueError:
        return None
