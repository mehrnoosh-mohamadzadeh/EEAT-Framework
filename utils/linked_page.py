"""
کمک‌تابع برای دنبال‌کردن واقعی یک لینک (مثل «درباره ما» یا «تماس با ما»)
و بازگرداندن صفحه‌ی پارس‌شده‌ی مقصد — استفاده در A3 (authority_extractor)
و T3/T4 (trust_extractor).

نکته مهم طراحی: این تابع کل صفحه‌ی پارس‌شده (نه فقط متن) را برمی‌گرداند
تا فراخوان بتواند هم متن و هم تگ‌های خاص (مثل <form>) را از یک دانلود
واحد استخراج کند — قبلاً T4 برای همین کار دو بار جداگانه دانلود می‌کرد
که باعث کندی زیاد می‌شد.

timeout کوتاه (پیش‌فرض ۵ ثانیه) عمدی است: این‌ها بررسی‌های «امتیاز
اضافه اگر جواب داد» هستند، نه بخش اصلی تحلیل — نباید کل فرآیند را کند
کنند.
"""

from urllib.parse import urljoin


def fetch_linked_page(base_url: str, href: str, timeout: int = 8):
    """
    دنبال‌کردن یک لینک نسبی/مطلق و بازگرداندن شیء ParsedPage کامل صفحه‌ی
    مقصد. در صورت هرگونه شکست (شبکه، تایم‌اوت، HTML نامعتبر) None
    برمی‌گرداند — تا فراخوان بدون کرش به شواهد صفحه‌ی فعلی بسنده کند.
    """
    if not href:
        return None
    try:
        from fetcher.page_downloader import fetch_simple
        from parser.html_parser import parse_html

        full_url = urljoin(base_url, href)
        result = fetch_simple(full_url, timeout=timeout)
        if not result.success:
            return None

        return parse_html(result.html, full_url)
    except Exception:
        return None


def fetch_linked_page_text(base_url: str, href: str, timeout: int = 8) -> str | None:
    """نسخه‌ی سازگار با قبل — فقط متن صفحه را برمی‌گرداند."""
    parsed = fetch_linked_page(base_url, href, timeout=timeout)
    if parsed is None:
        return None
    return parsed.soup.get_text(separator=" ", strip=True)
