"""
Extractor مؤلفه Authoritativeness — شاخص‌های A1 تا A3.

مرجع فرمول‌ها: feature_dictionary_v3.md، بخش «مؤلفه ۳: Authoritativeness»

نکته مهم: طبق نسخه ۳ فرهنگ شاخص‌ها، A1 (تایید هویت نهادی) معادل
کامل Authority نیست، فقط یکی از سه شاخص این مؤلفه است.
"""

import re

from extractors.base import BaseExtractor, IndicatorResult
from utils.domain_utils import score_institutional_verification
from utils.linked_page import fetch_linked_page_text


# الگوهای تشخیص لینک صفحه «درباره ما»
ABOUT_LINK_PATTERNS = ["about", "درباره", "درباره-ما", "درباره_ما", "aboutus"]

# الگوهای تشخیص ۳ جزئیات قابل‌راستی‌آزمایی (طبق A3 در فرهنگ شاخص‌ها)
REGISTRATION_NUMBER_PATTERN = re.compile(r"شماره\s*ثبت\s*[:\-]?\s*\d+")
FOUNDING_YEAR_PATTERN = re.compile(r"(تأسیس|تاسیس)\s*[:\-]?\s*(1[34]\d{2}|\d{4})")
# نشانه آدرس فیزیکی: یا کلمه «آدرس» به همراه متن قابل توجه بعدش، یا کدپستی ۱۰ رقمی
ADDRESS_KEYWORD_PATTERN = re.compile(r"آدرس\s*[:\-]?\s*\S+")
POSTAL_CODE_PATTERN = re.compile(r"\b\d{10}\b")


class AuthorityExtractor(BaseExtractor):
    component_name = "Authoritativeness"

    def extract(self, parsed_page) -> list[IndicatorResult]:
        return [
            self._a1_institutional_verification(parsed_page),
            self._a2_organization_schema_completeness(parsed_page),
            self._a3_about_us_verifiability(parsed_page),
        ]

    def _a1_institutional_verification(self, parsed_page) -> IndicatorResult:
        """
        A1 — تایید هویت نهادی (بر پایه نوع دامنه).
        فرمول: طبق IRNIC_DOMAIN_SCORES در utils/domain_utils.py
        """
        score = score_institutional_verification(parsed_page.url)
        return IndicatorResult(code="A1", value=score)

    def _a2_organization_schema_completeness(self, parsed_page) -> IndicatorResult:
        """
        A2 — کامل‌بودن داده ساختاریافته سازمانی.
        فرمول: تعداد فیلدهای موجود از (name, url, logo, sameAs, address) / 5

        نکته: بلوک‌های JSON-LD از قبل توسط ماژول Parser استخراج و
        پارس شده‌اند (parsed_page.json_ld_blocks) — نیازی به کتابخانه
        جداگانه extruct نبود، چون خود Parser با json.loads این کار را
        انجام می‌دهد (تصمیم طراحی برای کاهش وابستگی‌های پروژه).
        """
        expected_fields = ["name", "url", "logo", "sameAs", "address"]

        org_block = self._find_organization_block(parsed_page.json_ld_blocks)
        if org_block is None:
            # مدرک ضعیف‌تر جایگزین: لینک‌های واقعی به پروفایل شبکه‌های
            # اجتماعی (مثل آیکون‌های فوتر) — این schema.org نیست، ولی
            # شاهدی از هویت سازمانی قابل‌بررسی است
            social_links_found = self._count_social_media_links(parsed_page)
            if social_links_found > 0:
                score = min(social_links_found / 3, 1.0) * 0.5  # حداکثر نیمی از امتیاز کامل
                return IndicatorResult(code="A2", value=score, raw_details={
                    "reason": "no_schema_but_social_links_found",
                    "social_links_found": social_links_found,
                    "note": "این امتیاز بر پایه لینک‌های واقعی شبکه اجتماعی است، نه "
                            "داده ساختاریافته رسمی schema.org — حداکثر ۵۰٪ از امتیاز "
                            "کامل، چون مدرک ضعیف‌تری نسبت به schema.org رسمی است.",
                })
            return IndicatorResult(code="A2", value=0.0,
                                    raw_details={"reason": "no_organization_schema_found",
                                                 "social_links_found": 0})

        found_fields = [f for f in expected_fields if org_block.get(f)]
        score = len(found_fields) / len(expected_fields)
        return IndicatorResult(code="A2", value=score,
                                raw_details={"found_fields": found_fields})

    def _find_organization_block(self, json_ld_blocks: list) -> dict | None:
        """
        جستجوی اولین بلوک JSON-LD از نوع Organization در میان بلوک‌های
        استخراج‌شده. برخی سایت‌ها این بلوک را در قالب یک لیست (@graph)
        قرار می‌دهند که این تابع هر دو حالت را پوشش می‌دهد.
        """
        for block in json_ld_blocks:
            candidates = block.get("@graph", [block]) if isinstance(block, dict) else []
            for candidate in candidates:
                if not isinstance(candidate, dict):
                    continue
                schema_type = candidate.get("@type", "")
                type_list = schema_type if isinstance(schema_type, list) else [schema_type]
                if "Organization" in type_list:
                    return candidate
        return None

    def _count_social_media_links(self, parsed_page) -> int:
        """شمارش لینک‌های خروجی به پلتفرم‌های شناخته‌شده شبکه اجتماعی."""
        social_domains = [
            "instagram.com", "telegram.me", "t.me", "twitter.com", "x.com",
            "linkedin.com", "aparat.com", "facebook.com", "youtube.com",
        ]
        count = 0
        for link in parsed_page.all_links:
            href = link["href"].lower()
            if any(domain in href for domain in social_domains):
                count += 1
        return count

    def _a3_about_us_verifiability(self, parsed_page) -> IndicatorResult:
        """
        A3 — وجود صفحه «درباره ما» با اطلاعات قابل راستی‌آزمایی.
        فرمول: 0 اگر لینک صفحه درباره‌ ما نباشد، وگرنه
               (تعداد جزئیات یافت‌شده از ۳) / 3

        این نسخه لینک درباره‌ما را واقعاً دنبال می‌کند (fetch جداگانه)
        و متن صفحه‌ی مقصد را هم به‌همراه متن صفحه‌ی فعلی بررسی می‌کند
        — چون جزئیات قابل‌راستی‌آزمایی (آدرس، شماره ثبت) معمولاً در
        خودِ صفحه‌ی «درباره ما» هستند، نه لزوماً در فوتر صفحه‌ی فعلی.
        اگر دنبال‌کردن لینک شکست بخورد (شبکه/تایم‌اوت)، فقط به شواهد
        صفحه‌ی فعلی بسنده می‌شود (بدون کرش).
        """
        about_href = self._find_about_link_href(parsed_page)
        if about_href is None:
            return IndicatorResult(code="A3", value=0.0,
                                    raw_details={"reason": "no_about_link_found"})

        current_page_text = parsed_page.soup.get_text(separator=" ", strip=True)
        linked_page_text = fetch_linked_page_text(parsed_page.url, about_href)
        combined_text = current_page_text + " " + (linked_page_text or "")

        details_found = []
        if ADDRESS_KEYWORD_PATTERN.search(combined_text) or POSTAL_CODE_PATTERN.search(combined_text):
            details_found.append("physical_address")
        if REGISTRATION_NUMBER_PATTERN.search(combined_text):
            details_found.append("registration_number")
        if FOUNDING_YEAR_PATTERN.search(combined_text):
            details_found.append("founding_year")

        score = len(details_found) / 3
        return IndicatorResult(code="A3", value=score, raw_details={
            "details_found": details_found,
            "about_page_fetched": linked_page_text is not None,
        })

    def _find_about_link_href(self, parsed_page) -> str | None:
        """پیدا کردن href اولین لینکی که با الگوهای درباره‌ما تطابق دارد."""
        for link in parsed_page.all_links:
            href = link["href"].lower()
            text = link["text"].lower()
            parent_text = link.get("parent_text", "").lower()
            img_alt_text = link.get("img_alt_text", "").lower()
            if any(pattern in href or pattern in text or pattern in parent_text or pattern in img_alt_text
                   for pattern in ABOUT_LINK_PATTERNS):
                return link["href"]
        return None
