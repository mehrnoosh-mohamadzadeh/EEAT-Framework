"""
توابع کمکی برای تحلیل دامنه — استفاده در شاخص‌های A1 و X3.

نکته طراحی: به‌جای وابستگی به کتابخانه بیرونی tldextract، این ماژول
فقط از urllib.parse (کتابخانه استاندارد پایتون) استفاده می‌کند. این
تصمیم آگاهانه است: چون لیست پسوندهای مورد نیاز ما (.ac.ir, .gov.ir,
.org.ir, .co.ir, .ir, .com, .edu, .gov) کوچک و ثابت است، منطق تشخیص
Public Suffix List کامل (که دلیل اصلی وجود tldextract است) اینجا لازم
نیست و صرفاً یک وابستگی اضافه غیرضروری ایجاد می‌کرد.
"""

import re
from urllib.parse import urlparse


# دامنه‌های معتبر برای شاخص X3 (نسبت ارجاع به منابع معتبر)
# مرجع: feature_dictionary_v3.md, X3
# دو نوع نگاشت: پسوندهای عمومی (endswith) و میزبان‌های دقیق شناخته‌شده
AUTHORITATIVE_SUFFIXES = ["ac.ir", "gov.ir", "edu", "gov"]
AUTHORITATIVE_EXACT_HOSTS = ["doi.org", "ncbi.nlm.nih.gov"]

# نگاشت پسوند دامنه به امتیاز A1
# مرجع: feature_dictionary_v3.md, A1 — بر پایه سیاست ثبت IRNIC
# ترتیب از خاص به عام مهم است چون تشخیص بر اساس طولانی‌ترین تطابق انجام می‌شود
IRNIC_DOMAIN_SCORES = {
    "ac.ir": 1.0,
    "gov.ir": 1.0,
    "org.ir": 0.7,
    "co.ir": 0.7,
    "ir": 0.4,      # دامنه عمومی .ir
    "com": 0.4,
}
DEFAULT_DOMAIN_SCORE = 0.2


def _extract_hostname(url: str) -> str:
    """
    استخراج hostname خام از یک URL (بدون پروتکل، بدون پورت، بدون مسیر).
    مثال: "https://example.ac.ir:443/page?x=1" -> "example.ac.ir"
    """
    parsed = urlparse(url if "//" in url else f"//{url}")
    hostname = parsed.hostname or ""
    return hostname.lower()


def get_domain_suffix(url: str) -> str:
    """
    استخراج پسوند دامنه با تطابق طولانی‌ترین پسوند شناخته‌شده در
    IRNIC_DOMAIN_SCORES. اگر هیچ پسوند شناخته‌شده‌ای تطابق نداشت،
    رشته خالی برمی‌گرداند (که بعداً به DEFAULT_DOMAIN_SCORE نگاشت می‌شود).
    """
    hostname = _extract_hostname(url)
    if not hostname:
        return ""

    # مرتب‌سازی پسوندها از طولانی به کوتاه تا "ac.ir" قبل از "ir" چک شود
    known_suffixes = sorted(IRNIC_DOMAIN_SCORES.keys(), key=len, reverse=True)
    for suffix in known_suffixes:
        if hostname == suffix or hostname.endswith("." + suffix):
            return suffix
    return ""


def score_institutional_verification(url: str) -> float:
    """شاخص A1 — نگاشت پسوند دامنه به امتیاز طبق IRNIC_DOMAIN_SCORES."""
    suffix = get_domain_suffix(url)
    return IRNIC_DOMAIN_SCORES.get(suffix, DEFAULT_DOMAIN_SCORE)


def is_authoritative_domain(url: str) -> bool:
    """
    بررسی اینکه آیا یک URL خروجی به یکی از دامنه‌های معتبر
    (برای شاخص X3) اشاره دارد یا نه. دو نوع بررسی انجام می‌شود:
      ۱. تطابق پسوند عمومی (.ac.ir, .gov.ir, .edu, .gov)
      ۲. تطابق دقیق میزبان‌های شناخته‌شده (doi.org, ncbi.nlm.nih.gov)
    """
    hostname = _extract_hostname(url)
    if not hostname:
        return False

    for suffix in AUTHORITATIVE_SUFFIXES:
        if hostname == suffix or hostname.endswith("." + suffix):
            return True

    for exact_host in AUTHORITATIVE_EXACT_HOSTS:
        if hostname == exact_host or hostname.endswith("." + exact_host):
            return True

    return False
