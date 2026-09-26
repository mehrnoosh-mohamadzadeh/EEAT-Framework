# -*- coding: utf-8 -*-
"""
تابع مشترک برای پیدا کردن اولین لینکی که با مجموعه‌ای از الگوهای
کلمه‌ی کلیدی (مثل «درباره»، «تماس»، «privacy») تطابق دارد.

استفاده در: authority_extractor.py (A3 — درباره ما)،
            trust_extractor.py (T3 — حریم خصوصی، T4 — تماس با ما)

رفع باگ (نمونه‌های واقعی نشان‌داده‌شده حین بررسی):
قبلاً هر دو محل به‌طور مستقل و با substring خام (`pattern in href`)
تطابق را چک می‌کردند — یعنی لینکی مثل «/blog/contact-lens-review» یا
متنی مثل «لنزهای تماسی» یا «Privacy Preserving AI» به‌اشتباه به‌عنوان
لینک «تماس با ما»/«حریم خصوصی» تشخیص داده می‌شد، چون این کلمات کاملاً
تصادفی به‌عنوان substring/پسوند کلمه در یک عبارت کاملاً بی‌ربط ظاهر
شده بودند. این هم روی href اتفاق می‌افتاد هم روی متن قابل‌مشاهده.

رفع (هر دو جنبه‌ی مسئله):
  ۱. href: فقط بخش مسیر+fragment (نه دامنه/کوئری‌استرینگ) با /، - و _
     به «کلمه» شکسته می‌شود. تطابق فقط وقتی پذیرفته می‌شود که کلمه(های)
     الگو پشت‌سرهم در این لیست ظاهر شوند و حداکثر یک کلمه‌ی اضافه غیر
     از خودِ الگو در همان بخش مسیر باشد — یعنی «about»، «about-us»،
     «contact-us»، «privacy-policy»، «درباره-ما» هنوز مچ می‌شوند، ولی
     یک اسلاگ ۳+ کلمه‌ای کاملاً نامرتبط مثل «contact-lens-review» یا
     «privacy-preserving-ai» یا «درباره-یادگیری-ماشین» رد می‌شود.
  ۲. متن قابل‌مشاهده (text/parent_text/img_alt_text): به‌جای substring
     خام، جست‌وجوی مرزدار کلمه (`\\b`-مانند، سازگار با یونیکد/فارسی)
     انجام می‌شود — یعنی «تماسی» یا «contactless» دیگر با «تماس»/
     «contact» اشتباه گرفته نمی‌شوند.

⚠️ محدودیت پابرجا (نه یک باگ قابل‌رفع با regex ساده): یک متن لینک
طبیعی که خودِ کلمه را به‌طور کامل و مستقل دارد ولی معنایش چیز دیگری
است (مثلاً انگلیسی «Contact Lens» — «Contact» اینجا یک کلمه‌ی کامل و
مستقل است)، همچنان ممکن است اشتباه تشخیص داده شود؛ این ابهام ذاتیِ
تشخیص بر پایه‌ی کلمه‌ی کلیدی در متن آزاد است، نه چیزی که با تغییر
مرز کلمه رفع شود.
"""

import re
from urllib.parse import urlparse

_WORD_SPLIT_RE = re.compile(r"[/\-_\s]+")
_text_boundary_regex_cache: dict[str, re.Pattern] = {}


def _split_into_words(raw: str) -> list[str]:
    return [w for w in _WORD_SPLIT_RE.split(raw) if w]


def _href_path_words(href_lower: str) -> list[str]:
    """
    کلمه‌های بخش مسیر+fragment یک href (بدون دامنه/کوئری‌استرینگ).

    رفع باگ (پیدا شده حین تست، جدی‌تر از چیزی بود که این ماژول قرار
    بود رفع کند): وقتی fragment خالی باشد (که تقریباً همیشه همین‌طور
    است)، f"{parsed.path} {parsed.fragment}" یک فاصله‌ی خالی انتهایی
    واقعی به رشته اضافه می‌کرد (مثلاً "/تماس" می‌شد "/تماس "). چون
    _WORD_SPLIT_RE قبلاً فقط روی /، - و _ می‌شکست (نه فاصله)، این
    فاصله‌ی اضافه به آخرین کلمه می‌چسبید (مثلاً "تماس" -> "تماس ")
    و باعث می‌شد حتی ساده‌ترین حالت ممکن — href دقیقاً برابر با خودِ
    الگو (مثل href="/contact" یا href="/تماس") — دیگر هرگز مچ نشود؛
    فقط مواردی که کلمه‌ی الگو اولین کلمه بود (نه آخرین) کار می‌کردند.
    هیچ تست موجودی این حالت پایه را مستقیم چک نمی‌کرد، پس این رگرسیون
    قبل از انتشار پیدا نشده بود. حالا \\s هم به الگوی جداکننده اضافه
    شده تا این فاصله‌ی اضافه هم به‌عنوان جداکننده در نظر گرفته شود.
    """
    try:
        parsed = urlparse(href_lower)
        relevant_part = f"{parsed.path} {parsed.fragment}"
    except ValueError:
        relevant_part = href_lower
    return _split_into_words(relevant_part)


def _href_matches_pattern(href_words: list[str], pattern: str, max_extra_words: int = 1) -> bool:
    pattern_words = _split_into_words(pattern.lower())
    if not pattern_words:
        return False
    n = len(pattern_words)
    for i in range(len(href_words) - n + 1):
        if href_words[i:i + n] == pattern_words:
            return (len(href_words) - n) <= max_extra_words
    return False


def _text_matches_pattern(text: str, pattern: str) -> bool:
    if not text or not pattern:
        return False
    regex = _text_boundary_regex_cache.get(pattern)
    if regex is None:
        regex = re.compile(r"(?<!\w)" + re.escape(pattern.lower()) + r"(?!\w)")
        _text_boundary_regex_cache[pattern] = regex
    return regex.search(text.lower()) is not None


def find_matching_link_href(links: list, patterns: list,
                             non_fetchable_schemes: tuple = ()) -> str | None:
    """
    اولین href در links که با یکی از patterns تطابق دارد (طبق منطق
    بالا) را برمی‌گرداند. اگر non_fetchable_schemes داده شود، لینک‌هایی
    که با یکی از آن پروتکل‌ها شروع می‌شوند (مثل tel:, mailto:, #)
    نادیده گرفته می‌شوند و جست‌وجو به لینک بعدی ادامه می‌یابد.
    """
    for link in links:
        href = link.get("href", "")
        if not href:
            continue
        href_lower = href.lower()
        href_words = _href_path_words(href_lower)

        matched = any(
            _href_matches_pattern(href_words, p)
            or _text_matches_pattern(link.get("text", ""), p)
            or _text_matches_pattern(link.get("parent_text", ""), p)
            or _text_matches_pattern(link.get("img_alt_text", ""), p)
            for p in patterns
        )
        if not matched:
            continue
        if non_fetchable_schemes and href_lower.startswith(non_fetchable_schemes):
            continue
        return href
    return None
