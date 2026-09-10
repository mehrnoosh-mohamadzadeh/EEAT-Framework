"""
Extractor مؤلفه Expertise — شاخص‌های X1 تا X5.

مرجع فرمول‌ها: feature_dictionary_v3.md، بخش «مؤلفه ۲: Expertise»
"""

import re

from extractors.base import BaseExtractor, IndicatorResult
from utils.domain_utils import is_authoritative_domain
from utils.text_utils import tokenize_words, tokenize_sentences
from utils.settings_loader import get_threshold


BIO_LINK_PATTERNS = ["درباره-نویسنده", "درباره_نویسنده", "author", "نویسنده:"]

# عناصر HTML که معمولاً «امضای نویسنده» را نگه می‌دارند (نه کل مقاله)
# مرجع: مشاهده عملی در قالب‌های خبری/وبلاگی فارسی — 🔵 تصمیم طراحی
AUTHOR_AREA_ATTR_PATTERN = re.compile(r"author|byline|نویسنده|vcard", re.IGNORECASE)

# تعداد کلمه‌ی ابتدا/انتهای متن که به‌عنوان fallback ناحیه بایلاین
# در نظر گرفته می‌شود، وقتی هیچ نشانه ساختاری (schema/class/id/لینک)
# پیدا نشد — چون در بسیاری از قالب‌ها بایلاین همان‌جاست
AUTHOR_AREA_FALLBACK_WORD_COUNT = 50

# واژه‌نامه عناوین تخصصی فارسی — مرجع: feature_dictionary_v3.md, X1
GENERAL_TITLES = ["کارشناس", "متخصص"]
SPECIALIZED_TITLES = ["دکتر", "مهندس", "استاد", "کارشناس ارشد", "فوق تخصص", "phd", "پی‌اچ‌دی"]

PROFESSIONAL_PROFILE_PATTERNS = ["linkedin.com/in/", "scholar.google.com/citations", "orcid.org"]

CITATION_CONTEXT_MARKERS = ["طبق", "بر اساس", "به نقل از", "منتشر شده در", "به گزارش", "مطالعه‌ای"]


class ExpertiseExtractor(BaseExtractor):
    component_name = "Expertise"

    def extract(self, parsed_page) -> list[IndicatorResult]:
        return [
            self._x1_author_credentials(parsed_page),
            self._x2_professional_profile_links(parsed_page),
            self._x3_authoritative_citations_ratio(parsed_page),
            self._x4_content_depth_structure(parsed_page),
            self._x5_citation_context(parsed_page),
        ]

    def _x1_author_credentials(self, parsed_page) -> IndicatorResult:
        """
        X1 — شواهد صلاحیت و هویت حرفه‌ای نویسنده.
        فرمول: 0.4 * bio_score + 0.6 * title_score

        رفع باگ: title_score قبلاً کل متن صفحه را برای عناوین تخصصی
        (مثل «دکتر») می‌گشت، پس مقاله‌ای که فقط *موضوعش* پزشکان بود
        (بدون این‌که نویسنده‌اش مشخص باشد) هم امتیاز می‌گرفت. حالا این
        جستجو فقط در ناحیه‌ی محتمل «امضای نویسنده» انجام می‌شود.
        """
        has_bio = self._has_author_bio(parsed_page)
        author_area_text = self._extract_author_area_text(parsed_page)
        title_score = self._detect_title_score(author_area_text)

        score = 0.4 * (1.0 if has_bio else 0.0) + 0.6 * title_score
        return IndicatorResult(code="X1", value=score,
                                raw_details={"has_bio": has_bio, "title_score": title_score,
                                             "author_area_text_length": len(author_area_text)})

    def _extract_author_area_text(self, parsed_page) -> str:
        """
        استخراج متنی که احتمالاً «امضای نویسنده» است، نه کل بدنه مقاله.
        اولویت با نشانه‌های ساختاری قوی‌تر است؛ نتایج همه منابع با هم
        ترکیب می‌شوند (نه فقط اولین مورد یافت‌شده):

          ۱. فیلد author در JSON-LD (اگر به‌صورت نام متنی باشد)
          ۲. عناصر HTML با class/id حاوی author/byline/نویسنده/vcard
          ۳. متن لینک‌های «درباره نویسنده» + متن والدشان (برچسب کنار آیکون)
          ۴. fallback: فقط ابتدا/انتهای main_content_text (نه کل آن) —
             چون در نبود هر نشانه ساختاری، بایلاین معمولاً همان‌جاست
        """
        parts = []

        for block in parsed_page.json_ld_blocks:
            if isinstance(block, dict):
                author_field = block.get("author")
                if isinstance(author_field, dict):
                    name = author_field.get("name")
                    if isinstance(name, str):
                        parts.append(name)
                elif isinstance(author_field, str):
                    parts.append(author_field)

        for tag in parsed_page.soup.find_all(attrs={"class": AUTHOR_AREA_ATTR_PATTERN}):
            parts.append(tag.get_text(separator=" ", strip=True))
        for tag in parsed_page.soup.find_all(attrs={"id": AUTHOR_AREA_ATTR_PATTERN}):
            parts.append(tag.get_text(separator=" ", strip=True))

        for link in parsed_page.all_links:
            href = link["href"].lower()
            text = link["text"].lower()
            if any(p in href or p in text for p in BIO_LINK_PATTERNS):
                parts.append(link["text"])
                if link.get("parent_text"):
                    parts.append(link["parent_text"])

        if not parts:
            words, _ = tokenize_words(parsed_page.main_content_text)
            if words:
                n = AUTHOR_AREA_FALLBACK_WORD_COUNT
                parts.append(" ".join(words[:n]))
                parts.append(" ".join(words[-n:]))

        return " ".join(parts)

    def _has_author_bio(self, parsed_page) -> bool:
        # بررسی وجود schema.org Person
        for block in parsed_page.json_ld_blocks:
            if isinstance(block, dict):
                schema_type = block.get("@type", "")
                type_list = schema_type if isinstance(schema_type, list) else [schema_type]
                if "Person" in type_list:
                    return True
                # حالت رایج: author به‌عنوان فیلد تودرتو
                author_field = block.get("author")
                if isinstance(author_field, dict) and "Person" in str(author_field.get("@type", "")):
                    return True

        # بررسی لینک/متن «درباره نویسنده»
        for link in parsed_page.all_links:
            href = link["href"].lower()
            text = link["text"].lower()
            if any(p in href or p in text for p in BIO_LINK_PATTERNS):
                return True
        return False

    def _detect_title_score(self, text: str) -> float:
        text_lower = text.lower()
        if any(title.lower() in text_lower for title in SPECIALIZED_TITLES):
            return 1.0
        if any(title.lower() in text_lower for title in GENERAL_TITLES):
            return 0.5
        return 0.0

    def _x2_professional_profile_links(self, parsed_page) -> IndicatorResult:
        """
        X2 — لینک به پروفایل حرفه‌ای معتبر.
        فرمول: min(count_verified_profile_links / 2, 1)
        """
        count = 0
        for link in parsed_page.all_links:
            href = link["href"].lower()
            if any(pattern in href for pattern in PROFESSIONAL_PROFILE_PATTERNS):
                count += 1

        score = min(count / 2, 1.0)
        return IndicatorResult(code="X2", value=score, raw_details={"profile_links_found": count})

    def _x3_authoritative_citations_ratio(self, parsed_page) -> IndicatorResult:
        """
        X3 — نسبت ارجاع به منابع معتبر.
        فرمول: min(authoritative_outbound_links / total_outbound_links * N, 1) با N از config/settings.yaml (پیش‌فرض ۳)
        """
        outbound_links = [link for link in parsed_page.all_links
                           if link["href"].startswith("http")]

        if not outbound_links:
            return IndicatorResult(code="X3", value=0.0, raw_details={"total_outbound_links": 0})

        authoritative_count = sum(1 for link in outbound_links if is_authoritative_domain(link["href"]))
        ratio = authoritative_count / len(outbound_links)
        score = min(ratio * get_threshold("x3_authoritative_ratio_multiplier"), 1.0)
        return IndicatorResult(code="X3", value=score, raw_details={
            "authoritative_count": authoritative_count,
            "total_outbound_links": len(outbound_links),
        })

    def _x4_content_depth_structure(self, parsed_page) -> IndicatorResult:
        """
        X4 — عمق و ساختار محتوا (شاخص ترکیبی).
        فرمول: 0.3*length + 0.25*readability + 0.2*structure + 0.25*ttr

        نکته پیاده‌سازی: شمارش کلمه/جمله با Hazm (word_tokenize/
        sent_tokenize) انجام می‌شود؛ اگر Hazm نصب نباشد، به‌طور خودکار
        به یک روش ساده‌تر برمی‌گردد (رجوع کنید به utils/text_utils.py).
        """
        text = parsed_page.main_content_text
        words, word_method = tokenize_words(text)
        word_count = len(words)

        sentences, sentence_method = tokenize_sentences(text)

        length_score = min(word_count / get_threshold("x4_word_count_for_full_score"), 1.0)

        if sentences:
            avg_sentence_length = word_count / len(sentences)
        else:
            avg_sentence_length = 0
        sentence_length_cap = get_threshold("x4_avg_sentence_length_cap")
        readability_score = 1 - min(avg_sentence_length / sentence_length_cap, 1.0)

        structure_score = self._score_heading_structure(parsed_page.headings)

        ttr_window = get_threshold("x4_ttr_window_words")
        ttr_score = self._compute_ttr(words[:ttr_window])

        x4 = (0.3 * length_score + 0.25 * readability_score
              + 0.2 * structure_score + 0.25 * ttr_score)

        return IndicatorResult(code="X4", value=x4, raw_details={
            "word_count": word_count,
            "avg_sentence_length": round(avg_sentence_length, 1),
            "structure_score": structure_score,
            "ttr_score": round(ttr_score, 3),
            "tokenize_method": word_method,
        })

    def _score_heading_structure(self, headings: list) -> float:
        """
        بررسی سلسله‌مراتب منطقی H1-H6 (بدون پرش، مثلاً H1 مستقیم به H4).
        """
        if not headings:
            return 0.0

        levels = [level for level, _ in headings]
        has_jump = any(levels[i + 1] - levels[i] > 1 for i in range(len(levels) - 1))
        return 0.5 if has_jump else 1.0

    def _compute_ttr(self, words: list) -> float:
        """Type-Token Ratio روی یک پنجره ثابت کلمه (پیش‌فرض ۵۰۰ کلمه اول)."""
        if not words:
            return 0.0
        unique_words = set(w.lower().strip(".,!؟?") for w in words)
        return len(unique_words) / len(words)

    def _x5_citation_context(self, parsed_page) -> IndicatorResult:
        """
        X5 — کیفیت زمینه ارجاع (Citation Context).
        فرمول: citation_context_links / total_outbound_links

        تصحیح مهم: قبلاً فقط متن لینک («طبق مقاله...») بررسی می‌شد،
        بدون توجه به این‌که مقصد لینک واقعاً معتبر است یا نه — یعنی
        نوشتن «طبق منبع معتبر» با لینک به یک سایت تصادفی هم امتیاز
        می‌گرفت. حالا یک لینک فقط وقتی «ارجاع معتبر» حساب می‌شود که
        هر دو شرط را داشته باشد: هم بافت متنی ارجاعی، هم مقصد واقعاً
        یک دامنه معتبر (طبق is_authoritative_domain در X3).
        """
        outbound_links = [link for link in parsed_page.all_links
                           if link["href"].startswith("http")]

        if not outbound_links:
            return IndicatorResult(code="X5", value=0.0)

        citation_context_count = sum(
            1 for link in outbound_links
            if any(marker in link["text"] for marker in CITATION_CONTEXT_MARKERS)
            and is_authoritative_domain(link["href"])
        )
        score = citation_context_count / len(outbound_links)
        return IndicatorResult(code="X5", value=score, raw_details={
            "citation_context_count": citation_context_count,
            "total_outbound_links": len(outbound_links),
        })
