"""
کمک‌تابع برای دنبال‌کردن واقعی یک لینک (مثل «درباره ما» یا «تماس با ما»)
و بازگرداندن صفحه‌ی پارس‌شده‌ی مقصد — استفاده در A3 (authority_extractor)
و T3/T4 (trust_extractor).

نکته مهم طراحی: این تابع کل صفحه‌ی پارس‌شده (نه فقط متن) را برمی‌گرداند
تا فراخوان بتواند هم متن و هم تگ‌های خاص (مثل <form>) را از یک دانلود
واحد استخراج کند — قبلاً T4 برای همین کار دو بار جداگانه دانلود می‌کرد
که باعث کندی زیاد می‌شد.

timeout کوتاه (پیش‌فرض ۸ ثانیه) عمدی است: این‌ها بررسی‌های «امتیاز
اضافه اگر جواب داد» هستند، نه بخش اصلی تحلیل — نباید کل فرآیند را کند
کنند.

⚠️ نکته صادقانه درباره‌ی سرعت: از رفع باگ SPA (رجوع به fetch_linked_page)،
اگر صفحه‌ی مقصد یک اپ جاوااسکریپتی باشد، یک تلاش دوم با Playwright هم
انجام می‌شود که به‌مراتب کندتر از fetch_simple است (چون باید یک
مرورگر واقعی باز کند). این یعنی برای چنین صفحاتی، timeout مؤثر واقعی
بیشتر از همین عدد ۸ ثانیه‌ی مستندشده می‌شود — یک مصالحه‌ی آگاهانه بین
سرعت و دقت، نه یک ناهماهنگی.
"""

from urllib.parse import urljoin


def fetch_linked_page(base_url: str, href: str, timeout: int = 8):
    """
    دنبال‌کردن یک لینک نسبی/مطلق و بازگرداندن شیء ParsedPage کامل صفحه‌ی
    مقصد. در صورت هرگونه شکست (شبکه، تایم‌اوت، HTML نامعتبر) None
    برمی‌گرداند — تا فراخوان بدون کرش به شواهد صفحه‌ی فعلی بسنده کند.

    رفع باگ (نمونه‌ی واقعی rahavard365.com): صفحه‌ی مقصد می‌تواند خودش
    یک اپ جاوااسکریپتی (React/Next.js/Vue) باشد که HTML خامش تقریباً
    خالی است (فقط یک اسکلت لودینگ، محتوای واقعی با JS ساخته می‌شود).
    نسخه‌ی قبل این تابع فقط fetch_simple را امتحان می‌کرد و هرگز به
    Playwright سقوط نمی‌کرد — درحالی‌که خودِ صفحه‌ی اصلی (fetch() در
    fetcher/page_downloader.py) از قبل دقیقاً همین قابلیت را داشت.
    یعنی هر صفحه‌ی «درباره ما»/«تماس با ما»/«حریم خصوصی» که با
    جاوااسکریپت رندر می‌شد، همیشه خالی دیده می‌شد و امتیازش صفر
    می‌ماند. حالا همان تشخیص و fallback این‌جا هم اعمال می‌شود.
    """
    if not href:
        return None
    try:
        from fetcher.page_downloader import fetch_simple, fetch_rendered, _looks_like_js_rendered
        from parser.html_parser import parse_html

        full_url = urljoin(base_url, href)
        result = fetch_simple(full_url, timeout=timeout)
        if not result.success:
            return None

        if _looks_like_js_rendered(result.html):
            rendered_result = fetch_rendered(full_url, timeout=timeout)
            if rendered_result.success:
                result = rendered_result
            # اگر رندر با Playwright هم شکست بخورد، به همان HTML خام
            # ساده بسنده می‌کنیم (بهتر از هیچی) نه اینکه None برگردانیم

        return parse_html(result.html, full_url)
    except Exception:
        return None


def fetch_linked_page_text(base_url: str, href: str, timeout: int = 8) -> str | None:
    """نسخه‌ی سازگار با قبل — فقط متن صفحه را برمی‌گرداند."""
    parsed = fetch_linked_page(base_url, href, timeout=timeout)
    if parsed is None:
        return None
    return parsed.soup.get_text(separator=" ", strip=True)
