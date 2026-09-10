"""
پایپ‌لاین اصلی پروژه — منطق مشترک بین main.py (خط فرمان) و webapp/app.py
(رابط وب). این فایل، تنها جایی است که مراحل معماری
(Fetcher -> Parser -> Extractors -> Normalizer -> Scorer) به هم وصل
می‌شوند، تا خط فرمان و وب‌اپ هرگز از دو منطق متفاوت استفاده نکنند.
"""

import sys

from fetcher.page_downloader import fetch
from parser.html_parser import parse_html
from extractors.experience_extractor import ExperienceExtractor
from extractors.expertise_extractor import ExpertiseExtractor
from extractors.authority_extractor import AuthorityExtractor
from extractors.trust_extractor import TrustExtractor
from normalization.normalizer import normalize_component_scores
from scoring.scorer import compute_component_score, compute_final_score, PageScore


EXTRACTORS = {
    "Experience": ExperienceExtractor(),
    "Expertise": ExpertiseExtractor(),
    "Authoritativeness": AuthorityExtractor(),
    "Trustworthiness": TrustExtractor(),
}


class FetchFailedError(Exception):
    """وقتی دانلود صفحه ناموفق باشد (برای وب‌اپ که نیاز به نمایش پیام خطا دارد)."""
    def __init__(self, url: str, reason: str):
        self.url = url
        self.reason = reason
        super().__init__(f"دانلود ناموفق برای {url}: {reason}")


def process_single_url(url: str, weights: dict, render_js: bool = False,
                        weights_label: str = "", auto_detect_js: bool = False) -> PageScore:
    """
    اجرای کامل پایپ‌لاین برای یک URL.

    نکته پایداری: auto_detect_js پیش‌فرض False است. اگر True شود،
    Fetcher به‌طور خودکار برای صفحات به‌شدت وابسته به جاوااسکریپت
    سراغ Playwright می‌رود — این قابلیت مفید است اما در ترکیب با
    برخی محیط‌های اجرا (مثلاً سرور توسعه Flask روی ویندوز) می‌تواند
    ناپایدار باشد، پس در وب‌اپ به‌صورت پیش‌فرض خاموش نگه داشته می‌شود.

    اگر دانلود ناموفق باشد، FetchFailedError پرتاب می‌شود (به‌جای
    بازگرداندن None) تا فراخوان (main.py یا webapp) خودش تصمیم بگیرد
    چطور این حالت را به کاربر نشان دهد.
    """
    fetch_result = fetch(url, render_js=render_js, auto_detect=auto_detect_js)
    if not fetch_result.success:
        raise FetchFailedError(url, fetch_result.error or f"status_code={fetch_result.status_code}")

    parsed_page = parse_html(fetch_result.html, url)

    component_scores = {}
    excluded_indicators = {}
    missing_indicators = {}
    indicator_details = {}

    for component_name, extractor in EXTRACTORS.items():
        indicator_results = extractor.extract(parsed_page)

        for result in indicator_results:
            indicator_details[result.code] = {
                "value": result.value,
                "missing": result.is_missing,
                "applicable": result.applicable,
                "raw_details": result.raw_details,
            }

        normalized = normalize_component_scores(indicator_results)
        component_scores[component_name] = compute_component_score(normalized["usable_indicators"])
        if normalized["excluded_indicators"]:
            excluded_indicators[component_name] = normalized["excluded_indicators"]
        if normalized["missing_indicators"]:
            missing_indicators[component_name] = normalized["missing_indicators"]

    final_score = compute_final_score(component_scores, weights)

    return PageScore(
        url=url,
        component_scores=component_scores,
        final_score=final_score,
        weights_used=weights_label,
        excluded_indicators=excluded_indicators,
        missing_indicators=missing_indicators,
        indicator_details=indicator_details,
    )


def process_single_url_safe(url: str, weights: dict, render_js: bool = False):
    """
    نسخه‌ای از process_single_url که به‌جای پرتاب Exception، در صورت
    شکست دانلود، None برمی‌گرداند و پیام را در stderr چاپ می‌کند —
    برای استفاده در main.py (اجرای دسته‌ای که نباید با یک URL خراب
    کامل متوقف شود).
    """
    try:
        return process_single_url(url, weights, render_js=render_js)
    except FetchFailedError as e:
        print(f"[هشدار] {e}", file=sys.stderr)
        return None
