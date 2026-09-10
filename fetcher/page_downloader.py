"""
ماژول Fetcher — دانلود HTML خام از یک URL.

ورودی: یک URL
خروجی: HTML خام (str) + متادیتای پایه (کد وضعیت HTTP، زمان پاسخ)

دو حالت دانلود پشتیبانی می‌شود:
  ۱. حالت ساده (requests) — برای صفحاتی که HTML آن‌ها بدون اجرای
     جاوااسکریپت کامل است.
  ۲. حالت رندرشده (Playwright) — برای صفحاتی که محتوای اصلی‌شان
     توسط جاوااسکریپت (فریم‌ورک‌های React/Vue و مشابه) رندر می‌شود.
"""

import time
from dataclasses import dataclass

import requests
from requests.exceptions import RequestException


DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
)
DEFAULT_HEADERS = {
    "User-Agent": DEFAULT_USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "fa,en-US;q=0.9,en;q=0.8",
}

# اگر متن body اولیه HTML کمتر از این تعداد کاراکتر باشد، احتمالاً
# صفحه با جاوااسکریپت رندر می‌شود و باید از Playwright استفاده شود.
MIN_BODY_TEXT_LENGTH_FOR_SIMPLE_FETCH = 200


@dataclass
class FetchResult:
    """نتیجه دانلود یک صفحه."""
    url: str
    html: str
    status_code: int
    response_time_ms: float
    fetch_method: str  # "requests" یا "playwright"
    error: str | None = None

    @property
    def success(self) -> bool:
        """دانلود موفق یعنی خطایی نبوده و کد وضعیت در بازه ۲xx است."""
        return self.error is None and 200 <= self.status_code < 300


def fetch_simple(url: str, timeout: int = 25) -> FetchResult:
    """
    دانلود HTML با کتابخانه requests (بدون اجرای جاوااسکریپت).
    """
    headers = DEFAULT_HEADERS
    start = time.monotonic()
    try:
        response = requests.get(url, headers=headers, timeout=timeout)
        elapsed_ms = (time.monotonic() - start) * 1000
        return FetchResult(
            url=url,
            html=response.text,
            status_code=response.status_code,
            response_time_ms=elapsed_ms,
            fetch_method="requests",
            error=None,
        )
    except RequestException as exc:
        elapsed_ms = (time.monotonic() - start) * 1000
        return FetchResult(
            url=url,
            html="",
            status_code=0,
            response_time_ms=elapsed_ms,
            fetch_method="requests",
            error=str(exc),
        )


def fetch_rendered(url: str, timeout: int = 20) -> FetchResult:
    """
    دانلود HTML با Playwright (برای صفحاتی که با JS رندر می‌شوند).

    نکته: playwright به‌صورت lazy import می‌شود چون یک وابستگی سنگین
    است و فقط وقتی واقعاً لازم باشد (render_js=True یا تشخیص خودکار)
    بارگذاری می‌شود.
    """
    from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

    start = time.monotonic()
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(user_agent=DEFAULT_USER_AGENT)
            page.goto(url, timeout=timeout * 1000, wait_until="networkidle")
            html = page.content()
            browser.close()
        elapsed_ms = (time.monotonic() - start) * 1000
        return FetchResult(
            url=url,
            html=html,
            status_code=200,  # Playwright جزئیات status code را به همین سادگی نمی‌دهد
            response_time_ms=elapsed_ms,
            fetch_method="playwright",
            error=None,
        )
    except PlaywrightTimeoutError as exc:
        elapsed_ms = (time.monotonic() - start) * 1000
        return FetchResult(
            url=url,
            html="",
            status_code=0,
            response_time_ms=elapsed_ms,
            fetch_method="playwright",
            error=f"timeout: {exc}",
        )
    except Exception as exc:
        # هر خطای دیگر Playwright (DNS نامعتبر، رد اتصال، بسته‌شدن
        # ناگهانی مرورگر و غیره) — باید اینجا گرفته شود تا کل برنامه
        # (یا وب‌اپ) به‌خاطر یک URL خراب کرش نکند.
        elapsed_ms = (time.monotonic() - start) * 1000
        return FetchResult(
            url=url,
            html="",
            status_code=0,
            response_time_ms=elapsed_ms,
            fetch_method="playwright",
            error=f"playwright_error: {exc}",
        )


def _looks_like_js_rendered(html: str) -> bool:
    """
    heuristic ساده: اگر متن قابل‌مشاهده body خیلی کوتاه باشد، احتمالاً
    محتوای اصلی با جاوااسکریپت تزریق می‌شود.

    این یک heuristic است، نه تشخیص قطعی — باید در محدودیت‌های پژوهش
    ذکر شود.
    """
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "lxml")
    body = soup.find("body")
    if body is None:
        return True
    text = body.get_text(strip=True)
    return len(text) < MIN_BODY_TEXT_LENGTH_FOR_SIMPLE_FETCH


def fetch(url: str, render_js: bool = False, auto_detect: bool = True,
          fallback_to_playwright_on_failure: bool = True) -> FetchResult:
    """
    نقطه ورود اصلی ماژول Fetcher.

    اگر render_js=True باشد مستقیماً از Playwright استفاده می‌شود.
    در غیر این صورت ابتدا با requests تلاش می‌شود. دو حالت باعث
    سوییچ خودکار به Playwright می‌شوند:
      ۱. fallback_to_playwright_on_failure=True و درخواست requests
         کامل شکست بخورد (مثل SSLError یا ConnectionError) — چون
         بعضی سایت‌ها بر اساس امضای TLS درخواست‌های غیرمرورگری را رد
         می‌کنند؛ Playwright یک مرورگر Chromium واقعی با امضای TLS
         واقعی است، پس می‌تواند این نوع مسدودسازی را دور بزند.
      ۲. auto_detect=True و heuristic تشخیص دهد صفحه احتمالاً
         JS-rendered است (محتوای خیلی کم).
    """
    if render_js:
        return fetch_rendered(url)

    result = fetch_simple(url)

    if result.error is not None and fallback_to_playwright_on_failure:
        rendered_result = fetch_rendered(url)
        if rendered_result.error is None:
            return rendered_result
        return result

    if auto_detect and result.error is None and _looks_like_js_rendered(result.html):
        rendered_result = fetch_rendered(url)
        if rendered_result.error is None:
            return rendered_result
        # اگر رندر JS هم شکست خورد، همان نتیجه ساده (هرچند ناقص) را برگردان
        return result

    return result
