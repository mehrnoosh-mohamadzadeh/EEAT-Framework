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

from utils.settings_loader import get_fetcher_setting


DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
)
def _get_configured_user_agent() -> str:
    """
    خواندن user_agent از config/settings.yaml؛ اگر نبود یا فایل در
    دسترس نبود، همان User-Agent واقعی کروم که همیشه پیش‌فرض این پروژه
    بوده برمی‌گردد (رجوع به یافته‌ی مستندشده: نسخه‌ی رباتی باعث
    مسدودشدن توسط بعضی سایت‌ها می‌شد).
    """
    return get_fetcher_setting("user_agent", DEFAULT_USER_AGENT)


def _build_headers() -> dict:
    return {
        "User-Agent": _get_configured_user_agent(),
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


def fetch_simple(url: str, timeout: int = None) -> FetchResult:
    """
    دانلود HTML با کتابخانه requests (بدون اجرای جاوااسکریپت).

    timeout=None یعنی از config/settings.yaml (fetcher.timeout_seconds)
    خوانده شود؛ رفع باگ: قبلاً این تابع همیشه ۲۵ ثانیه‌ی هاردکد را
    استفاده می‌کرد، بدون توجه به مقدار ۱۵ ثانیه‌ی مستندشده در config.
    """
    if timeout is None:
        timeout = get_fetcher_setting("timeout_seconds", 25)
    headers = _build_headers()
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


def fetch_rendered(url: str, timeout: int = None) -> FetchResult:
    """
    دانلود HTML با Playwright (برای صفحاتی که با JS رندر می‌شوند).

    نکته: playwright به‌صورت lazy import می‌شود چون یک وابستگی سنگین
    است و فقط وقتی واقعاً لازم باشد (render_js=True یا تشخیص خودکار)
    بارگذاری می‌شود.

    timeout=None یعنی از config/settings.yaml (fetcher.timeout_seconds)
    خوانده شود — رفع باگ: قبلاً این تابع همیشه ۲۰ ثانیه‌ی هاردکد را
    استفاده می‌کرد، بدون توجه به مقدار ۱۵ ثانیه‌ی مستندشده در config.

    استراتژی wait: رفع باگ — قبلاً page.goto() فقط با
    wait_until="networkidle" صدا زده می‌شد. networkidle یعنی صبر تا
    هیچ درخواست شبکه‌ای برای ۵۰۰ میلی‌ثانیه در جریان نباشد؛ خیلی از
    سایت‌های واقعی (آنالیتیکس، تبلیغات، polling، وب‌سوکت) هرگز واقعاً
    به این حالت نمی‌رسند، پس goto() تا سررسید کامل timeout (که همان
    fetcher.timeout_seconds کل است) صبر می‌کرد و کل fetch شکست می‌خورد،
    حتی اگر محتوای اصلی صفحه خیلی زودتر (مثلاً با DOMContentLoaded)
    کامل رندر شده باشد. حالا ابتدا فقط تا "domcontentloaded" (سبک‌تر و
    قابل‌اعتمادتر) صبر می‌شود، سپس یک تلاش جداگانه و با سقف کوتاه‌تر
    برای رسیدن به networkidle انجام می‌شود؛ اگر این تلاش دوم هم به
    سررسید بخورد، به‌جای شکست کل fetch، همان DOM فعلی (که معمولاً تا
    این مرحله محتوای اصلی را دارد) گرفته و برگردانده می‌شود.

    نکته‌ی دوم (تست شده با یک صفحه‌ی شبیه‌سازی‌شده که محتوا را با
    setTimeout و بدون هیچ درخواست شبکه‌ای تزریق می‌کند): «networkidle»
    فقط درخواست‌های شبکه را می‌بیند، نه اجرای کد جاوااسکریپت. اگر
    محتوای اصلی صفحه با تایمر/state داخلی (نه یک درخواست شبکه‌ی جدید)
    بعد از رندر اولیه ظاهر شود، ممکن است هیچ درخواست شبکه‌ای بعد از
    domcontentloaded رخ ندهد و networkidle بلافاصله (خیلی زودتر از
    ظاهرشدن محتوای واقعی) برآورده شود. برای همین، بعد از تلاش برای
    networkidle، یک صبر محدود و اضافه هم انجام می‌شود تا متن قابل‌مشاهده
    body به همان آستانه‌ای برسد که _looks_like_js_rendered برای «کافی
    بودن محتوا» استفاده می‌کند — اگر تا سررسید این صبر اضافه هم به آن
    نرسد، باز همان DOM فعلی (بهتر از هیچی) گرفته می‌شود، نه شکست کامل.
    """
    from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

    if timeout is None:
        timeout = get_fetcher_setting("timeout_seconds", 20)

    # سقف صبر جداگانه برای رسیدن به networkidle بعد از domcontentloaded؛
    # حداکثر نیمی از کل timeout (و حداقل ۳ ثانیه) — عمداً محدود، تا
    # صفحاتی که هیچ‌وقت واقعاً idle نمی‌شوند کل fetch را قفل نکنند.
    idle_wait_ms = max(3000, int(timeout * 1000 / 2))

    # سقف صبر «متن کافی» — عمداً ثابت و کوتاه (نه وابسته به idle_wait_ms).
    # رفع باگ (پیدا شده حین تست با یک صفحه‌ی About Us واقعی و کوتاه):
    # اگر این سقف را برابر idle_wait_ms می‌گذاشتیم، هر صفحه‌ی کوتاهِ
    # واقعی (که هیچ‌وقت به آستانه‌ی ۲۰۰ کاراکتر نمی‌رسد چون واقعاً همین
    # مقدار محتوا دارد) باید تا انتهای همان سقف طولانی صبر می‌کرد و
    # fetch را چند ثانیه بی‌دلیل کند می‌کرد. این صبر فقط یک شبکه‌ی
    # ایمنی برای مهلت‌دادن به تزریق محتوای JS (هیدریشن/state داخلی) است،
    # نه یک انتظار اصلی — پس کوتاه نگه داشته می‌شود.
    CONTENT_STABILITY_WAIT_MS = 2000

    start = time.monotonic()
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            try:
                page = browser.new_page(user_agent=_get_configured_user_agent())
                page.goto(url, timeout=timeout * 1000, wait_until="domcontentloaded")
                try:
                    page.wait_for_load_state("networkidle", timeout=idle_wait_ms)
                except PlaywrightTimeoutError:
                    # صفحه هرگز کاملاً idle نشد (مثلاً به‌خاطر polling/
                    # آنالیتیکس دائمی) — DOM فعلی معمولاً محتوای اصلی
                    # را دارد، پس همین را استفاده می‌کنیم به‌جای شکست کامل
                    pass
                try:
                    page.wait_for_function(
                        "document.body && document.body.innerText "
                        f"&& document.body.innerText.trim().length > {MIN_BODY_TEXT_LENGTH_FOR_SIMPLE_FETCH}",
                        timeout=CONTENT_STABILITY_WAIT_MS,
                    )
                except PlaywrightTimeoutError:
                    # محتوا هیچ‌وقت به آستانه‌ی «کافی» نرسید (یا صفحه
                    # واقعاً همین‌قدر کم‌محتوا است) — همان DOM فعلی گرفته
                    # می‌شود؛ تصمیم نهایی درباره‌ی کافی‌بودن محتوا به عهده‌ی
                    # تحلیل بعدی (Parser/Extractors) است، نه این تابع
                    pass
                html = page.content()
            finally:
                # رفع باگ: قبلاً browser.close() فقط در مسیر موفق صدا
                # زده می‌شد؛ اگر page.goto() timeout بدهد (محتمل روی
                # سایت‌های خارجی با فیلترشکن)، مرورگر headless بسته
                # نمی‌شد و در اجرای دسته‌ای روی چند ده URL، چندین
                # پردازش کروم زامبی باز می‌ماند
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
