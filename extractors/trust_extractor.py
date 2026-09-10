"""
Extractor مؤلفه Trustworthiness — شاخص‌های T1 تا T7.

مرجع فرمول‌ها: feature_dictionary_v3.md، بخش «مؤلفه ۴: Trustworthiness»
"""

import re
import ssl
import socket
from urllib.parse import urlparse

from extractors.base import BaseExtractor, IndicatorResult
from utils.persian_dates import find_jalali_date_in_text, jalali_to_gregorian, days_since
from utils.linked_page import fetch_linked_page_text, fetch_linked_page


PRIVACY_LINK_PATTERNS = ["privacy", "حریم-خصوصی", "حریم_خصوصی", "سیاست-حفظ-حریم"]
CONTACT_LINK_PATTERNS = ["contact", "تماس-با-ما", "تماس_با_ما"]

IRANIAN_PHONE_PATTERN = re.compile(
    r"(?:\+98[\s\-]?|0098[\s\-]?|0)?9\d{2}[\s\-]?\d{3}[\s\-]?\d{4}\b"   # موبایل
    r"|\(?0\d{2,3}\)?[\s\-]?\d{3,4}[\s\-]?\d{3,4}\b"                    # ثابت
)
EMAIL_PATTERN = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
# نشانه ایمیل محافظت‌شده با Cloudflare (که در HTML خام قابل رمزگشایی نیست
# ولی وجودش خودش شاهدی بر ارائه ایمیل توسط سایت است)
CLOUDFLARE_EMAIL_PROTECTION_PATTERN = re.compile(r"__cf_email__|data-cfemail")

ADDRESS_KEYWORD_PATTERN = re.compile(r"(آدرس|نشانی)\s*[:\-]?\s*\S+")
# نشانه‌های ساختاری آدرس فیزیکی حتی بدون کلمه «آدرس»/«نشانی» قبلش
ADDRESS_STRUCTURE_PATTERN = re.compile(r"خیابان|میدان|کوچه|بلوار|پلاک|بزرگراه")
POSTAL_CODE_PATTERN = re.compile(r"\b\d{10}\b")

# لینک‌های واتساپ — خودشان مدرک مستقیم یک کانال تماس هستند، نیازی به
# دانلود جداگانه صفحه‌ی مقصد نیست (که معمولاً هم قابل دانلود ساده نیست)
WHATSAPP_LINK_PATTERN = re.compile(r"wa\.me/|api\.whatsapp\.com|whatsapp\.com/send")

AD_CLASS_ID_PATTERN = re.compile(r"\b(ad|ads|advert|banner|sponsor)\b", re.IGNORECASE)

STRUCTURED_DATA_TYPES_EXPECTED = ["Article", "Person", "Organization"]


class TrustExtractor(BaseExtractor):
    component_name = "Trustworthiness"

    def extract(self, parsed_page) -> list[IndicatorResult]:
        return [
            self._t1_https(parsed_page),
            self._t2_ssl_certificate_validity(parsed_page),
            self._t3_privacy_policy(parsed_page),
            self._t4_contact_us(parsed_page),
            self._t5_ad_density(parsed_page),
            self._t6_content_freshness(parsed_page),
            self._t7_structured_data_completeness(parsed_page),
        ]

    def _t1_https(self, parsed_page) -> IndicatorResult:
        """T1 — HTTPS. باینری، وزن پایین در weights.yaml."""
        is_https = parsed_page.url.strip().lower().startswith("https://")
        return IndicatorResult(code="T1", value=1.0 if is_https else 0.0)

    def _t2_ssl_certificate_validity(self, parsed_page) -> IndicatorResult:
        """
        T2 — اعتبار گواهی SSL (نه Self-Signed).

        نکته: این تابع نیازمند یک اتصال شبکه واقعی به سایت است (برای
        دریافت گواهی TLS) و در محیط توسعه بدون دسترسی اینترنت قابل
        اجرا/تست نیست؛ منطق آن بر پایه ماژول استاندارد ssl پایتون
        نوشته شده و باید روی یک ماشین با دسترسی اینترنت واقعی تست شود.
        """
        parsed_url = urlparse(parsed_page.url)
        if parsed_url.scheme != "https":
            return IndicatorResult(code="T2", value=0.0,
                                    raw_details={"reason": "not_https"})

        hostname = parsed_url.hostname
        try:
            context = ssl.create_default_context()
            with socket.create_connection((hostname, 443), timeout=5) as sock:
                with context.wrap_socket(sock, server_hostname=hostname) as ssock:
                    cert = ssock.getpeercert()
            # اگر گواهی با موفقیت از طریق create_default_context (که
            # زنجیره اعتماد سیستم‌عامل را بررسی می‌کند) دریافت شود،
            # یعنی گواهی self-signed نبوده و توسط یک CA معتبر صادر شده
            return IndicatorResult(code="T2", value=1.0,
                                    raw_details={"issuer": cert.get("issuer")})
        except ssl.SSLCertVerificationError:
            return IndicatorResult(code="T2", value=0.0,
                                    raw_details={"reason": "certificate_verification_failed"})
        except (socket.timeout, socket.gaierror, ConnectionRefusedError, OSError) as e:
            # خطای شبکه (نه مشکل گواهی) — نمی‌توان قضاوت کرد، پس missing
            return IndicatorResult(code="T2", value=None, is_missing=True,
                                    raw_details={"reason": f"network_error: {e}"})

    def _t3_privacy_policy(self, parsed_page) -> IndicatorResult:
        """
        T3 — وجود و کیفیت Privacy Policy.
        فرمول: 0 اگر نباشد، وگرنه min(word_count_of_linked_page / 300, 1)

        این نسخه لینک را واقعاً دنبال می‌کند و طول واقعی صفحه‌ی مقصد
        را می‌سنجد. اگر دنبال‌کردن لینک شکست بخورد، امتیاز ثابت ۰.۵
        (فقط برای وجود لینک) داده می‌شود.
        """
        privacy_href = self._find_matching_link_href(parsed_page, PRIVACY_LINK_PATTERNS)
        if privacy_href is None:
            return IndicatorResult(code="T3", value=0.0)

        linked_text = fetch_linked_page_text(parsed_page.url, privacy_href)
        if linked_text is None:
            return IndicatorResult(code="T3", value=0.5, raw_details={
                "note": "link_found_but_destination_page_fetch_failed",
            })

        word_count = len(linked_text.split())
        score = min(word_count / 300, 1.0)
        return IndicatorResult(code="T3", value=score, raw_details={
            "linked_page_word_count": word_count,
        })

    def _t4_contact_us(self, parsed_page) -> IndicatorResult:
        """
        T4 — وجود Contact Us با اطلاعات قابل راستی‌آزمایی.
        فرمول: (تعداد کانال یافت‌شده از ۴) / 4
        [تلفن، ایمیل، آدرس فیزیکی، فرم تماس]

        این شاخص هم صفحه‌ی فعلی و هم (در صورت وجود لینک «تماس با ما»)
        صفحه‌ی مقصد آن لینک را بررسی می‌کند. تصحیح مهم نسبت به نسخه
        قبل: صفحه‌ی مقصد فقط یک‌بار دانلود می‌شود (نه دو بار جداگانه
        برای متن و برای فرم) — این تغییر به‌تنهایی زمان بررسی این
        شاخص را نصف می‌کند.
        """
        current_page_text = parsed_page.soup.get_text(separator=" ", strip=True)

        contact_href = self._find_matching_link_href(parsed_page, CONTACT_LINK_PATTERNS)
        linked_page = fetch_linked_page(parsed_page.url, contact_href) if contact_href else None

        linked_text = linked_page.soup.get_text(separator=" ", strip=True) if linked_page else ""
        combined_text = current_page_text + " " + linked_text

        has_form_on_current_page = parsed_page.soup.find("form") is not None
        has_form_on_linked_page = linked_page is not None and linked_page.soup.find("form") is not None

        channels_found = []
        has_whatsapp_link = any(
            WHATSAPP_LINK_PATTERN.search(link["href"]) for link in parsed_page.all_links
        )
        has_tel_link = any(link["href"].lower().startswith("tel:") for link in parsed_page.all_links)
        has_mailto_link = any(link["href"].lower().startswith("mailto:") for link in parsed_page.all_links)

        if IRANIAN_PHONE_PATTERN.search(combined_text) or has_whatsapp_link or has_tel_link:
            # لینک tel: یا واتساپ خودش مدرک مستقیم و قوی یک کانال تماس
            # است — نیازی به دانلود صفحه‌ی مقصد نیست (که برای tel: اصلاً
            # امکان‌پذیر هم نیست، چون پروتکل وب نیست)
            channels_found.append("phone")
        # ایمیل معمولی، لینک mailto:، یا ایمیل محافظت‌شده با Cloudflare
        raw_html_str = str(parsed_page.soup)
        if (EMAIL_PATTERN.search(combined_text) or has_mailto_link
                or CLOUDFLARE_EMAIL_PROTECTION_PATTERN.search(raw_html_str)):
            channels_found.append("email")
        if (ADDRESS_KEYWORD_PATTERN.search(combined_text)
                or ADDRESS_STRUCTURE_PATTERN.search(combined_text)
                or POSTAL_CODE_PATTERN.search(combined_text)):
            channels_found.append("physical_address")
        if has_form_on_current_page or has_form_on_linked_page:
            channels_found.append("contact_form")

        score = len(channels_found) / 4
        return IndicatorResult(code="T4", value=score, raw_details={
            "channels_found": channels_found,
            "contact_page_fetched": linked_page is not None,
            "whatsapp_link_detected": has_whatsapp_link,
            "tel_link_detected": has_tel_link,
            "mailto_link_detected": has_mailto_link,
        })

    def _t5_ad_density(self, parsed_page) -> IndicatorResult:
        """
        T5 — تراکم تبلیغات (Heuristic — نه تشخیص قطعی).
        فرمول: 1 - min(ad_elements / content_blocks, 1)
        """
        all_blocks = parsed_page.soup.find_all(["div", "section", "aside"])
        if not all_blocks:
            return IndicatorResult(code="T5", value=1.0)

        ad_elements = 0
        for tag in all_blocks:
            class_and_id = " ".join(tag.get("class", []) or []) + " " + (tag.get("id", "") or "")
            if AD_CLASS_ID_PATTERN.search(class_and_id):
                ad_elements += 1
        ad_elements += len(parsed_page.soup.find_all("iframe"))

        ratio = ad_elements / len(all_blocks)
        score = 1 - min(ratio, 1.0)
        return IndicatorResult(code="T5", value=score,
                                raw_details={"ad_elements": ad_elements, "total_blocks": len(all_blocks)})

    def _t6_content_freshness(self, parsed_page) -> IndicatorResult:
        """
        T6 — تازگی محتوا (با پشتیبانی تقویم شمسی).
        فرمول: max(0, 1 - (days_since_update / 730))

        اگر هیچ تاریخی یافت نشود، is_missing=True برگردانده می‌شود
        (نه صفر) — طبق مدیریت داده گمشده در نسخه ۳ فرهنگ شاخص‌ها.
        """
        # اول تلاش برای یافتن تاریخ در JSON-LD (schema.org dateModified/datePublished)
        schema_date_str = self._find_schema_date(parsed_page.json_ld_blocks)
        if schema_date_str:
            # TODO: پارس تاریخ میلادی ISO 8601 با datetime.fromisoformat
            pass

        # سپس جستجوی تاریخ شمسی در کل متن صفحه
        full_text = parsed_page.soup.get_text(separator=" ", strip=True)
        try:
            jalali_date = find_jalali_date_in_text(full_text)
        except ImportError:
            # کتابخانه jdatetime نصب نیست — این شاخص را missing علامت
            # می‌زنیم (نه اینکه کل اجرای برنامه متوقف شود)
            return IndicatorResult(code="T6", value=None, is_missing=True,
                                    raw_details={"reason": "jdatetime_not_installed"})

        if jalali_date is None:
            return IndicatorResult(code="T6", value=None, is_missing=True,
                                    raw_details={"reason": "no_date_found"})

        gregorian_date = jalali_to_gregorian(jalali_date)
        elapsed_days = days_since(gregorian_date)
        score = max(0.0, 1 - (elapsed_days / 730))
        return IndicatorResult(code="T6", value=score,
                                raw_details={"days_since_update": elapsed_days})

    def _find_schema_date(self, json_ld_blocks: list) -> str | None:
        for block in json_ld_blocks:
            if isinstance(block, dict):
                date_value = block.get("dateModified") or block.get("datePublished")
                if date_value:
                    return date_value
        return None

    def _t7_structured_data_completeness(self, parsed_page) -> IndicatorResult:
        """
        T7 — کامل‌بودن داده ساختاریافته صفحه.
        فرمول: نسبت انواع مارک‌آپ موجود از ۳ نوع اصلی (Article/Person/Organization)
        """
        found_types = set()
        for block in parsed_page.json_ld_blocks:
            if not isinstance(block, dict):
                continue
            schema_type = block.get("@type", "")
            type_list = schema_type if isinstance(schema_type, list) else [schema_type]
            for t in type_list:
                if t in STRUCTURED_DATA_TYPES_EXPECTED:
                    found_types.add(t)

        score = len(found_types) / len(STRUCTURED_DATA_TYPES_EXPECTED)
        return IndicatorResult(code="T7", value=score,
                                raw_details={"found_types": list(found_types)})

    def _has_matching_link(self, parsed_page, patterns: list) -> bool:
        return self._find_matching_link_href(parsed_page, patterns) is not None

    # پروتکل‌هایی که اصلاً صفحه‌ی وب نیستند و نباید دانلود شوند —
    # تلاش برای دانلودشان همیشه شکست می‌خورد و فقط وقت تلف می‌کند
    NON_FETCHABLE_SCHEMES = ("tel:", "mailto:", "sms:", "javascript:", "#")

    def _find_matching_link_href(self, parsed_page, patterns: list) -> str | None:
        for link in parsed_page.all_links:
            href = link["href"].lower()
            text = link["text"].lower()
            parent_text = link.get("parent_text", "").lower()
            img_alt_text = link.get("img_alt_text", "").lower()
            if any(p in href or p in text or p in parent_text or p in img_alt_text for p in patterns):
                if href.startswith(self.NON_FETCHABLE_SCHEMES):
                    continue  # این لینک قابل دانلود نیست، دنبال بعدی بگرد
                return link["href"]
        return None
