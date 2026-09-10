"""
Extractor مؤلفه Experience — شاخص‌های E1 تا E4.

مرجع فرمول‌ها: feature_dictionary_v3.md، بخش «مؤلفه ۱: Experience»
"""

import re

from extractors.base import BaseExtractor, IndicatorResult
from utils.text_utils import tokenize_words
from utils.settings_loader import get_threshold


# الگوی E1: عدد + "سال" + فعل/اسم تجربه‌محور در فاصله نزدیک
# مرجع: feature_dictionary_v3.md, E1
EXPERIENCE_DURATION_PATTERN = re.compile(
    r"\d+\s*سال[ه]?(?:\s+[\u0600-\u06FF]+){0,4}?\s+"
    r"(است|کار کرده|فعالیت|سابقه|تجربه|مشغول|فعالیت می‌کند)"
)
EXPERIENCE_GENERAL_PATTERN = re.compile(r"سابقه|تجربه عملی|سال‌ها|چند سال")

# الگوی E2: ضمایر و افعال اول‌شخص رایج فارسی که نشانه بیان تجربه شخصی‌اند
FIRST_PERSON_PATTERNS = [
    r"\bمن\b", r"تجربه من", r"من امتحان کردم", r"من استفاده کردم",
    r"وقتی من", r"در تجربه‌ام", r"به نظر من", r"من متوجه شدم",
]
FIRST_PERSON_REGEX = re.compile("|".join(FIRST_PERSON_PATTERNS))

# نشانه‌های صفحه محصول (برای قابلیت‌اعمال شرطی E2 — طبق نسخه ۳)
PRODUCT_PAGE_INDICATORS = ["افزودن به سبد خرید", "add to cart", "قیمت:", "تومان"]

GENERIC_ALT_PATTERNS = ["img_", "image", "photo", "دانلود عکس", ""]

# کلمات کلیدی برای heuristic بصری E3 — وقتی schema.org Review/AggregateRating
# پیدا نشود اما بخش نظرات به‌صورت بصری در صفحه وجود دارد
REVIEW_KEYWORDS = [
    "نظرات", "دیدگاه‌ها", "دیدگاه ها", "دیدگاهها", "دیدگاه",
    "نظر کاربران", "امتیاز کاربران", "بررسی خریداران",
]

# عبارت‌های فعلی دقیق («ثبت نظر» و مشابه) — به‌جای کلمه‌ی تنهای «نظر»
# که بیش‌ازحد کلی بود و با جمله‌هایی مثل «به نظر من»، «نظرسنجی»، یا
# فرم‌های نامرتبط (مثل «لطفا ایمیل خود را ثبت کنید») اشتباه گرفته می‌شد
REVIEW_ACTION_PATTERN = re.compile(
    r"ثبت\s+(?:کردن\s+)?نظر|ارسال\s+نظر|درج\s+نظر|افزودن\s+نظر|نوشتن\s+نظر"
)

NEGATION_WORDS_NEAR_REVIEW = ["بدون", "فاقد", "هیچ"]

# الگوهای ساختاری رایج بخش نظرات/دیدگاه در HTML — مستقل از زبان صفحه،
# چون این‌ها اسم کلاس/آیدی هستند که اغلب انگلیسی نوشته می‌شوند
# (حتی تو سایت‌های فارسی، مثل CMSهای وردپرس‌محور)
COMMENT_SECTION_STRUCTURAL_PATTERNS = ["comment", "review", "nazar", "didgah", "نظر", "دیدگاه"]

# این کلمات نشان می‌دهند بخش مورد نظر احتمالاً «خبرنامه/عضویت ایمیلی»
# است، نه واقعاً بخش نظرات — حتی اگر تصادفاً کلمه‌ای مثل «نظر» هم
# نزدیکش باشد یا کلاس CSS مشترکی با فرم نظرات داشته باشد
NEWSLETTER_EXCLUSION_PATTERNS = ["خبرنامه", "newsletter", "عضویت در ایمیل", "ایمیل مارکتینگ"]


def _has_review_signal(full_text: str, max_words_before: int = 2, exclusion_window: int = 5) -> bool:
    """جستجوی کلمات کلیدی نظرات با بررسی دقیق ۲ کلمه‌ی قبلش (نه یک
    بازه‌ی حرفی گنگ) برای جلوگیری از تشخیص غلط جمله‌هایی مثل «این
    صفحه بدون بخش نظرات است». مثال‌هایی مثل «نظرات خودتون رو اعلام
    کنید» درست تشخیص داده می‌شوند چون کلمه‌ی منفی‌کننده‌ای نزدیکشان نیست.

    اگر کلمات مربوط به خبرنامه (مثل «خبرنامه») در فاصله‌ی نزدیک باشند،
    آن مورد نادیده گرفته می‌شود — چون احتمالاً بخش خبرنامه است، نه
    بخش نظرات واقعی (حتی اگر کلمه‌ی «نظر» هم تصادفاً آنجا آمده باشد)."""
    action_match = REVIEW_ACTION_PATTERN.search(full_text)
    if action_match:
        before_words = full_text[:action_match.start()].split()[-3:]
        if not any(neg in before_words for neg in NEGATION_WORDS_NEAR_REVIEW):
            return True

    words = full_text.split()
    keyword_word_lists = [kw.split() for kw in REVIEW_KEYWORDS]

    for i in range(len(words)):
        for kw_words in keyword_word_lists:
            n = len(kw_words)
            if words[i:i + n] == kw_words:
                start = max(0, i - max_words_before)
                preceding_words = words[start:i]
                if any(neg in preceding_words for neg in NEGATION_WORDS_NEAR_REVIEW):
                    continue

                wide_start = max(0, i - exclusion_window)
                wide_end = min(len(words), i + n + exclusion_window)
                nearby_words = words[wide_start:wide_end]
                nearby_text = " ".join(nearby_words)
                if any(excl in nearby_text for excl in NEWSLETTER_EXCLUSION_PATTERNS):
                    continue

                return True
    return False


def _has_review_section_structurally(soup) -> bool:
    """
    تشخیص بخش نظرات از روی ساختار HTML (نام کلاس/آیدی)، مستقل از
    اینکه متن قابل‌مشاهده چه زبانی دارد یا دقیقاً چه کلمه‌ای نوشته
    شده. این روش قوی‌تر از جستجوی متنی است چون خیلی از سایت‌ها
    (خصوصاً وردپرس) نام کلاس‌های انگلیسی رایج (مثل "comment-list",
    "reviews-section") دارند، حتی وقتی خود صفحه فارسی است.

    نکته: این هم یک Heuristic است — نامگذاری کلاس‌ها استاندارد جهانی
    ندارد، پس تضمین ۱۰۰٪ نمی‌دهد. اگر کلاس/آیدی همزمان نشانه‌ی خبرنامه
    هم داشته باشد (مثلاً یک تم که کلاس‌های عمومی را بین فرم خبرنامه و
    فرم نظرات مشترک گذاشته)، نادیده گرفته می‌شود.
    """
    for tag in soup.find_all(True):
        class_and_id = " ".join(tag.get("class", []) or []) + " " + (tag.get("id", "") or "")
        class_and_id_lower = class_and_id.lower()
        if any(pattern in class_and_id_lower for pattern in COMMENT_SECTION_STRUCTURAL_PATTERNS):
            tag_text_lower = tag.get_text(separator=" ", strip=True).lower()
            if any(excl.lower() in class_and_id_lower or excl.lower() in tag_text_lower
                   for excl in NEWSLETTER_EXCLUSION_PATTERNS):
                continue
            return True
    return False


class ExperienceExtractor(BaseExtractor):
    component_name = "Experience"

    def extract(self, parsed_page) -> list[IndicatorResult]:
        return [
            self._e1_practical_experience_evidence(parsed_page),
            self._e2_first_person_density(parsed_page),
            self._e3_user_reviews(parsed_page),
            self._e4_original_images(parsed_page),
        ]

    def _e1_practical_experience_evidence(self, parsed_page) -> IndicatorResult:
        """
        E1 — شواهد تجربه عملی مستقیم.
        فرمول: 0.4 * has_experience_phrase + 0.6 * has_explicit_duration
        """
        text = parsed_page.main_content_text

        has_explicit_duration = bool(EXPERIENCE_DURATION_PATTERN.search(text))
        has_experience_phrase = has_explicit_duration or bool(EXPERIENCE_GENERAL_PATTERN.search(text))

        score = 0.4 * has_experience_phrase + 0.6 * has_explicit_duration
        return IndicatorResult(code="E1", value=score, raw_details={
            "has_experience_phrase": has_experience_phrase,
            "has_explicit_duration": has_explicit_duration,
        })

    def _e2_first_person_density(self, parsed_page) -> IndicatorResult:
        """
        E2 — تراکم زبان تجربه‌محور (اول‌شخص).
        فرمول: min(count / word_count * 1000 / K, 1)   با K از config/settings.yaml (پیش‌فرض ۱۵)

        نکته: طبق نسخه ۳، این شاخص فقط برای صفحات مقاله فعال است؛
        برای صفحات محصول applicable=False برمی‌گرداند.

        نکته پیاده‌سازی: شمارش کلمات با Hazm word_tokenize انجام
        می‌شود (اگر Hazm نصب نباشد، به‌طور خودکار به split ساده
        برمی‌گردد — رجوع کنید به utils/text_utils.py).
        """
        full_text_lower = parsed_page.soup.get_text(separator=" ", strip=True).lower()
        if any(indicator in full_text_lower for indicator in PRODUCT_PAGE_INDICATORS):
            return IndicatorResult(code="E2", value=None, applicable=False,
                                    raw_details={"reason": "detected_as_product_page"})

        text = parsed_page.main_content_text
        words, tokenize_method = tokenize_words(text)
        word_count = len(words)

        min_words = get_threshold("e2_min_word_count_for_scoring")
        if word_count < min_words:
            # رفع باگ: قبلاً فقط word_count == 0 رد می‌شد، پس یک صفحه‌ی
            # ۶ کلمه‌ای با یک «من» امتیاز کامل می‌گرفت (نسبت غیرقابل‌اتکا
            # روی نمونه‌ی خیلی کوچک). متن به این کوتاهی برای سنجش تراکم
            # قابل‌اتکا نیست، پس is_missing است، نه صفر یا امتیاز کامل.
            return IndicatorResult(code="E2", value=None, is_missing=True,
                                    raw_details={"reason": "not_enough_text_for_reliable_density",
                                                 "word_count": word_count, "min_required": min_words})

        matches = len(FIRST_PERSON_REGEX.findall(text))
        K = get_threshold("e2_first_person_per_1000_words")  # مرجع: config/settings.yaml
        score = min((matches / word_count * 1000) / K, 1.0)
        return IndicatorResult(code="E2", value=score,
                                raw_details={"matches": matches, "word_count": word_count,
                                             "tokenize_method": tokenize_method})

    def _e3_user_reviews(self, parsed_page) -> IndicatorResult:
        """
        E3 — وجود و کیفیت نظرات کاربران.
        فرمول: 0 اگر schema نباشد، وگرنه min(review_count / N, 1) با N از config/settings.yaml (پیش‌فرض ۱۰)
        """
        review_count = 0
        has_review_schema = False

        # برخی سایت‌ها چند بلوک JSON-LD را داخل یک ساختار @graph می‌گذارند
        # (مثلاً {"@graph": [ {...}, {...} ]}) — باید این حالت را هم باز کنیم،
        # وگرنه بلوک‌های تودرتوی @graph اصلاً دیده نمی‌شوند.
        flattened_blocks = []
        for block in parsed_page.json_ld_blocks:
            if isinstance(block, dict) and isinstance(block.get("@graph"), list):
                flattened_blocks.extend(block["@graph"])
            else:
                flattened_blocks.append(block)

        for block in flattened_blocks:
            if not isinstance(block, dict):
                continue
            schema_type = block.get("@type", "")
            type_list = schema_type if isinstance(schema_type, list) else [schema_type]

            if "AggregateRating" in type_list:
                has_review_schema = True
                review_count = max(review_count, int(block.get("reviewCount", 0) or block.get("ratingCount", 0) or 0))
            if "Review" in type_list:
                has_review_schema = True
                review_count += 1

            # حالت تودرتو ۱: AggregateRating به‌عنوان فیلد داخل Product/Article
            nested_rating = block.get("aggregateRating")
            if isinstance(nested_rating, dict):
                has_review_schema = True
                review_count = max(review_count, int(nested_rating.get("reviewCount", 0) or 0))

            # حالت تودرتو ۲ (قبلاً پشتیبانی نمی‌شد): یک یا چند Review به‌صورت
            # فیلد "review" داخل Product/Article — بدون هیچ خلاصه‌ی
            # aggregateRating، فقط خودِ نظر(ها) مستقیم نوشته شده باشند
            nested_review = block.get("review")
            if nested_review is not None:
                review_items = nested_review if isinstance(nested_review, list) else [nested_review]
                valid_reviews = [r for r in review_items if isinstance(r, dict)]
                if valid_reviews:
                    has_review_schema = True
                    review_count = max(review_count, len(valid_reviews))

        # علاوه بر JSON-LD، بعضی سایت‌ها (خصوصاً قالب‌های وردپرسی فارسی)
        # به‌جای JSON-LD از فرمت Microdata استفاده می‌کنند — یعنی به‌جای
        # یک تگ <script> جدا، مستقیم attribute های itemscope/itemtype
        # روی تگ‌های معمولی HTML می‌گذارند. این فرمت را هم باید جدا بررسی کنیم.
        microdata_reviews = parsed_page.soup.find_all(
            attrs={"itemtype": lambda v: v and "schema.org/Review" in v}
        )
        if microdata_reviews:
            has_review_schema = True
            review_count = max(review_count, len(microdata_reviews))

        microdata_agg_rating = parsed_page.soup.find(
            attrs={"itemtype": lambda v: v and "schema.org/AggregateRating" in v}
        )
        if microdata_agg_rating is not None:
            has_review_schema = True
            count_tag = microdata_agg_rating.find(attrs={"itemprop": "reviewCount"})
            if count_tag is not None:
                count_text = count_tag.get("content") or count_tag.get_text(strip=True)
                if count_text and count_text.isdigit():
                    review_count = max(review_count, int(count_text))

        if not has_review_schema:
            full_text = parsed_page.soup.get_text(separator=" ", strip=True)
            # متن دکمه‌ها/ورودی‌ها (مثل <input type="submit" value="ثبت نظر">)
            # جزو get_text() نیست چون داخل attribute است، نه محتوای تگ
            button_texts = " ".join(
                tag.get("value", "") for tag in parsed_page.soup.find_all("input")
            )
            full_text = full_text + " " + button_texts

            text_signal = _has_review_signal(full_text)
            structural_signal = _has_review_section_structurally(parsed_page.soup)

            if text_signal or structural_signal:
                return IndicatorResult(code="E3", value=0.4, raw_details={
                    "reason": "heuristic_match_no_schema",
                    "text_signal": text_signal,
                    "structural_signal": structural_signal,
                    "note": "امتیاز جزئی بر پایه شواهد بصری/ساختاری نظرات است "
                            "(نه تایید رسمی از طریق داده ساختاریافته schema.org).",
                })
            return IndicatorResult(code="E3", value=0.0, raw_details={
                "reason": "no_evidence_found",
                "text_signal": False,
                "structural_signal": False,
            })

        score = min(review_count / get_threshold("e3_review_count_for_full_score"), 1.0)

        # شفافیت: اگر schema ادعای نظر دارد ولی هیچ نشونه‌ی بصری/ساختاری
        # نظر در صفحه نیست، این تناقض مستند می‌شود — ممکن است سایت یک
        # ادعای فنی نوشته باشد که با آنچه کاربر واقعی می‌بیند فرق دارد.
        full_text_check = parsed_page.soup.get_text(separator=" ", strip=True)
        visible_signal_present = (_has_review_signal(full_text_check)
                                   or _has_review_section_structurally(parsed_page.soup))

        return IndicatorResult(code="E3", value=score, raw_details={
            "review_count": review_count,
            "visible_signal_present": visible_signal_present,
            "note": None if visible_signal_present else (
                "هشدار: داده ساختاریافته ادعای نظر می‌کند اما هیچ نشونه‌ی "
                "بصری/ساختاری نظر در صفحه یافت نشد — ممکن است این عدد "
                "بازتاب‌دهنده تجربه واقعی کاربر نباشد."
            ),
        })

    def _e4_original_images(self, parsed_page) -> IndicatorResult:
        """
        E4 — تصاویر اختصاصی داخل محتوا.
        فرمول: min(qualified_images / N, 1) با N از config/settings.yaml (پیش‌فرض ۳)

        نکته: شمارش فقط روی تصاویر داخل main_content_soup انجام می‌شود
        (نه تصاویر هدر/فوتر/سایدبار/تبلیغات).
        """
        images_in_main_content = parsed_page.main_content_soup.find_all("img")

        qualified = 0
        for img in images_in_main_content:
            alt = (img.get("alt") or "").strip().lower()
            if alt and not any(generic in alt for generic in GENERIC_ALT_PATTERNS if generic):
                qualified += 1

        score = min(qualified / get_threshold("e4_qualified_images_for_full_score"), 1.0)
        return IndicatorResult(code="E4", value=score,
                                raw_details={"qualified_images": qualified,
                                             "total_images_in_content": len(images_in_main_content)})
