"""
Extractor مؤلفه Experience — شاخص‌های E1 تا E4.

مرجع فرمول‌ها: feature_dictionary_v3.md، بخش «مؤلفه ۱: Experience»
"""

import re
from collections import Counter, defaultdict

from extractors.base import BaseExtractor, IndicatorResult
from utils.text_utils import tokenize_words
from utils.settings_loader import get_threshold
from utils.json_ld_utils import flatten_json_ld_blocks
from utils.wordpress_signals import has_wp_comment_form as _has_wp_comment_form


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

# نشانه‌ی فنی و مطمئن «این صفحه قابلیت نظردهی وردپرسی دارد» — منتقل
# شده به utils/wordpress_signals.py چون trust_extractor.py (T4) هم به
# همین تشخیص نیاز داشت (برای رد کردن فرم نظر از شمارش فرم تماس)

# شمارنده‌ی عددی نظرات (مثل «۱۲ دیدگاه» یا «3 Comments») — نشانه‌ی
# قوی‌تر از صرفاً وجود کلمه، چون خودِ عدد یعنی واقعاً نظر ثبت شده
NUMERIC_COMMENT_COUNT_PATTERN = re.compile(
    r"(\d+|[۰-۹]+)\s*(?:دیدگاه|نظر|comments?)", re.IGNORECASE
)

# کلاس‌های استاندارد وردپرس برای خودِ آیتم‌های نظر (نه فرم، نه بخش‌بندی
# کلی) — اگر این‌ها باشند یعنی واقعاً حداقل یک نظر ثبت‌شده وجود دارد
ACTUAL_REVIEW_ITEM_CLASS_PATTERNS = ["comment-list", "comment-body", "comment-author"]

# این کلمات نشان می‌دهند بخش مورد نظر احتمالاً «خبرنامه/عضویت ایمیلی»
# است، نه واقعاً بخش نظرات — حتی اگر تصادفاً کلمه‌ای مثل «نظر» هم
# نزدیکش باشد یا کلاس CSS مشترکی با فرم نظرات داشته باشد
NEWSLETTER_EXCLUSION_PATTERNS = ["خبرنامه", "newsletter", "عضویت در ایمیل", "ایمیل مارکتینگ"]


def _has_review_signal(full_text: str, max_words_before: int = 5, exclusion_window: int = 5) -> bool:
    """جستجوی کلمات کلیدی نظرات با بررسی دقیق ۵ کلمه‌ی قبلش (نه یک
    بازه‌ی حرفی گنگ) برای جلوگیری از تشخیص غلط جمله‌هایی مثل «این
    صفحه بدون بخش نظرات است». مثال‌هایی مثل «نظرات خودتون رو اعلام
    کنید» درست تشخیص داده می‌شوند چون کلمه‌ی منفی‌کننده‌ای نزدیکشان نیست.

    رفع باگ: این پنجره قبلاً فقط ۲ کلمه بود، پس جمله‌ی کاملاً طبیعی
    فارسی «بدون هیچ اشاره‌ای به نظرات» (که فاصله‌ی ۴ کلمه‌ای بین «بدون»
    و «نظرات» دارد) تشخیص داده نمی‌شد. حالا با exclusion_window
    (که برای تشخیص خبرنامه از قبل ۵ بود) هماهنگ شد.

    اگر کلمات مربوط به خبرنامه (مثل «خبرنامه») در فاصله‌ی نزدیک باشند،
    آن مورد نادیده گرفته می‌شود — چون احتمالاً بخش خبرنامه است، نه
    بخش نظرات واقعی (حتی اگر کلمه‌ی «نظر» هم تصادفاً آنجا آمده باشد)."""
    action_match = REVIEW_ACTION_PATTERN.search(full_text)
    if action_match:
        # هماهنگ‌شده با همان پنجره‌ی max_words_before؛ قبلاً این‌جا
        # عدد ۳ جدا و هاردکد بود، مستقل از پارامتر بالا
        before_words = full_text[:action_match.start()].split()[-max_words_before:]
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


def _extract_numeric_comment_count(full_text: str):
    """
    استخراج شمارنده‌ی عددی نظرات (مثل «۱۲ دیدگاه») از متن صفحه، اگر
    باشد. این از صرفاً وجود کلمه مطمئن‌تر است چون خودِ عدد یعنی واقعاً
    نظر ثبت شده، نه فقط یک برچسب/فرم خالی. اعداد فارسی هم پشتیبانی
    می‌شوند (۰-۹ به 0-9 تبدیل می‌شود).
    """
    match = NUMERIC_COMMENT_COUNT_PATTERN.search(full_text)
    if not match:
        return None
    persian_to_english_digits = str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789")
    normalized = match.group(1).translate(persian_to_english_digits)
    try:
        return int(normalized)
    except ValueError:
        return None


def _has_actual_review_items(soup) -> bool:
    """
    تشخیص اینکه آیا واقعاً حداقل یک نظرِ ثبت‌شده (نه فقط فرم خالی)
    در صفحه هست — بر پایه‌ی کلاس‌های استاندارد وردپرس برای خودِ
    آیتم‌های نظر (comment-list/comment-body/comment-author).

    این تفکیک دقیقاً همان چیزی است که در نمونه‌ی dr-moghimi.com لازم
    بود: آن صفحه یک فرم نظردهی («comment-respond») داشت ولی هیچ
    نشانه‌ای از یک نظر واقعاً ثبت‌شده نداشت — یعنی نتیجه باید «بخش
    نظرات پیدا شد، ولی خالی است» باشد، نه یکسان با «هیچ نشانه‌ای از
    نظردهی در کل صفحه نیست».
    """
    for tag in soup.find_all(True):
        class_and_id_lower = (
            " ".join(tag.get("class", []) or []) + " " + (tag.get("id", "") or "")
        ).lower()
        if any(pattern in class_and_id_lower for pattern in ACTUAL_REVIEW_ITEM_CLASS_PATTERNS):
            return True
    return False


def _count_actual_review_items(soup) -> int:
    """
    شمارش تعداد نظرهای واقعاً ثبت‌شده (نه فقط تشخیص وجود حداقل یکی).

    رفع باگ (نمونه‌ی واقعی doctoreto.com — صفحه‌ای با ده‌ها نظر): وقتی
    schema رسمی و شمارنده‌ی عددی متنی نبود، نتیجه فقط «حداقل یک نظر
    هست» بود و امتیاز E3 برای هر تعداد نظر (یک نظر یا صدتا) یک عدد
    ثابت ۰.۴ می‌شد. حالا تعداد واقعی شمرده می‌شود تا با مسیرهای دیگر
    E3 (schema و شمارنده‌ی عددی) هم‌مقیاس باشد: min(count / N, 1).

    سه روش شمارش (حداکثرِ آن‌ها گرفته می‌شود، چون قالب‌های مختلف
    یکی از این ساختارها را دارند و شمردن هر سه با هم دوباره‌شماری
    ایجاد می‌کرد):
      ۱) تعداد عناصر با کلاسِ دقیق «comment-body»
      ۲) تعداد عناصر با کلاسِ دقیق «comment-author»
      ۳) تعداد شناسه‌های یکتای وردپرسی «comment-<عدد>» (با حذف
         پیشوند «div-» تا یک نظر دو بار شمرده نشود)
    اگر هیچ‌کدام عددی ندهد ولی وجود نظر قبلاً تأیید شده، حداقل ۱ برمی‌گردد.
    """
    body_count = 0
    author_count = 0
    wp_ids = set()
    wp_id_pattern = re.compile(r"^(?:div-)?comment-(\d+)$")

    for tag in soup.find_all(True):
        classes = tag.get("class", []) or []
        if "comment-body" in classes:
            body_count += 1
        if "comment-author" in classes:
            author_count += 1
        match = wp_id_pattern.match(tag.get("id", "") or "")
        if match:
            wp_ids.add(match.group(1))

    return max(body_count, author_count, len(wp_ids), 1)


# تگ‌هایی که هرگز خودِ «آیتم نظر» نیستند (فرم، دکمه، لینک، تصویر و مشابه)
_NON_ITEM_TAGS = {"script", "style", "form", "textarea", "input", "button", "a",
                  "select", "option", "svg", "path", "img", "label"}

# حداقل تعداد کلمه‌ی متن داخل یک عنصر تا «آیتم نظر» حساب شود؛ عناصر کوتاهِ
# تکراری (تاریخ، نام کاربر، دکمه‌ی پاسخ، ستاره) با این شرط کنار می‌روند
_MIN_WORDS_FOR_COMMENT_ITEM = 3


def _count_repeated_comment_items(soup) -> int:
    """
    شمارش نظرها بر پایه‌ی «ساختار تکرارشونده»، مستقل از نام دقیق کلاس‌ها —
    برای سایت‌هایی که وردپرس نیستند (پلتفرم‌های سفارشی، Next.js با کلاس‌های
    هش‌شده مثل Comments_item__a1b2 و غیره).

    ایده: آیتم‌های یک لیست نظر همیشه یک قالب یکسان دارند و چندبار تکرار
    می‌شوند. پس:
      ۱) همه‌ی عناصری که کلاسشان کلمه‌ی مرتبط با نظر دارد جمع می‌شوند؛
      ۲) بر اساس (نام تگ + کوتاه‌ترین کلاس مرتبط) گروه‌بندی می‌شوند —
         کوتاه‌ترین، چون وردپرس کلاس‌های متغیر مثل «comment-author-admin»
         یا «depth-2» هم اضافه می‌کند که نباید گروه را بشکند؛
      ۳) فقط عناصر دارای متن واقعی (حداقل ۳ کلمه) و بدون فرم داخلشان
         حساب می‌شوند؛
      ۴) بین گروه‌های تکرارشونده (حداقل ۲ عضو)، اندازه‌ای انتخاب می‌شود که
         در بیشترین گروه‌ها مشترک است (مثلاً «آیتم»، «بدنه» و «متن» هرکدام
         N بار)، تا زیرعنصری که در هر نظر چندبار آمده، عدد را باد نکند.
    اگر هیچ ساختار تکراری پیدا نشود، ۰ برمی‌گردد.
    """
    groups = defaultdict(list)
    for tag in soup.find_all(True):
        if tag.name in _NON_ITEM_TAGS:
            continue
        classes = [c.lower() for c in (tag.get("class", []) or [])]
        keyword_tokens = [c for c in classes
                          if any(k in c for k in COMMENT_SECTION_STRUCTURAL_PATTERNS)]
        if not keyword_tokens:
            continue
        signature = (tag.name, min(keyword_tokens, key=len))
        groups[signature].append(tag)

    sizes = []
    for members in groups.values():
        valid = []
        for tag in members:
            text = tag.get_text(separator=" ", strip=True)
            if len(text.split()) < _MIN_WORDS_FOR_COMMENT_ITEM:
                continue
            if tag.find(["form", "textarea"]) is not None:
                continue
            if any(excl in text.lower() for excl in NEWSLETTER_EXCLUSION_PATTERNS):
                continue
            valid.append(tag)
        if len(valid) >= 2:
            sizes.append(len(valid))

    if not sizes:
        return 0
    size_frequency = Counter(sizes)
    # بیشترین تکرار؛ در تساوی، عدد کوچک‌تر (محتاطانه‌تر)
    return max(size_frequency.items(), key=lambda kv: (kv[1], -kv[0]))[0]


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
        comment_blocks_count = 0
        comment_schema_max = 0

        # باز کردن @graph در صورت وجود (رجوع به utils/json_ld_utils.py)
        flattened_blocks = flatten_json_ld_blocks(parsed_page.json_ld_blocks)

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

            # نظرهای وبلاگی/مقاله‌ای در schema.org نوع «Comment» هستند (نه Review):
            # هم به‌صورت بلاک مستقل، هم فیلد commentCount، هم فیلد comment داخل Article
            if "Comment" in type_list or "UserComments" in type_list:
                comment_blocks_count += 1
            declared_comment_count = block.get("commentCount")
            try:
                declared_comment_count = int(declared_comment_count)
            except (TypeError, ValueError):
                declared_comment_count = 0
            nested_comments = block.get("comment")
            if nested_comments is not None:
                nested_comment_items = nested_comments if isinstance(nested_comments, list) else [nested_comments]
                declared_comment_count = max(
                    declared_comment_count,
                    len([c for c in nested_comment_items if isinstance(c, dict)]),
                )
            comment_schema_max = max(comment_schema_max, declared_comment_count)

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

        schema_comment_total = max(comment_blocks_count, comment_schema_max)
        if schema_comment_total > 0:
            has_review_schema = True
            review_count = max(review_count, schema_comment_total)

        # Microdata: نوع Comment و فیلد commentCount
        microdata_comments = parsed_page.soup.find_all(
            attrs={"itemtype": lambda v: v and "schema.org/Comment" in v}
        )
        microdata_comment_count = len(microdata_comments)
        comment_count_tag = parsed_page.soup.find(attrs={"itemprop": "commentCount"})
        if comment_count_tag is not None:
            raw_count = comment_count_tag.get("content") or comment_count_tag.get_text(strip=True)
            try:
                microdata_comment_count = max(microdata_comment_count, int(raw_count))
            except (TypeError, ValueError):
                pass
        if microdata_comment_count > 0:
            has_review_schema = True
            review_count = max(review_count, microdata_comment_count)

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

        # رفع باگ (نمونه‌ی واقعی doctoreto.com): افزونه‌های ستاره‌دهی اغلب یک
        # AggregateRating با ratingCount=0 در صفحه می‌گذارند. قبلاً همین وجودِ
        # schema، حتی با تعداد صفر، کل شمارش نظرهای واقعی HTML را کنار می‌زد و
        # صفحه‌ای با ده‌ها نظر امتیاز ۰ می‌گرفت. schema فقط وقتی مسیر اصلی است که
        # واقعاً تعداد مثبتی اعلام کرده باشد.
        if has_review_schema and review_count == 0:
            has_review_schema = False

        if not has_review_schema:
            full_text = parsed_page.soup.get_text(separator=" ", strip=True)
            # متن دکمه‌ها/ورودی‌ها (مثل <input type="submit" value="ثبت نظر">)
            # جزو get_text() نیست چون داخل attribute است، نه محتوای تگ
            button_texts = " ".join(
                tag.get("value", "") for tag in parsed_page.soup.find_all("input")
            )
            full_text = full_text + " " + button_texts

            # اول شمارنده‌ی عددی («۱۲ دیدگاه») را چک می‌کنیم — قوی‌ترین
            # نشانه، چون خودِ عدد یعنی نظر واقعاً ثبت شده
            numeric_count = _extract_numeric_comment_count(full_text)
            if numeric_count is not None and numeric_count > 0:
                score = min(numeric_count / get_threshold("e3_review_count_for_full_score"), 1.0)
                return IndicatorResult(code="E3", value=score, raw_details={
                    "reason": "heuristic_numeric_comment_count",
                    "review_count": numeric_count,
                    "note": "بر پایه شمارنده عددی نظرات در متن صفحه (نه schema.org).",
                })

            text_signal = _has_review_signal(full_text)
            structural_signal = _has_review_section_structurally(parsed_page.soup)
            wp_comment_form_present = _has_wp_comment_form(parsed_page.soup)
            comment_feature_detected = text_signal or structural_signal or wp_comment_form_present

            if not comment_feature_detected:
                return IndicatorResult(code="E3", value=0.0, raw_details={
                    "reason": "no_evidence_found",
                    "text_signal": False,
                    "structural_signal": False,
                    "wp_comment_form_present": False,
                })

            # بخش/فرم نظردهی پیدا شد؛ حالا باید تفکیک شود که آیا واقعاً
            # نظری هم ثبت شده یا فقط یک فرم خالی است — رفع باگ: قبلاً
            # این دو حالت هر دو یکسان ۰ می‌گرفتند و قابل‌تفکیک نبودند
            # دو روش شمارش مستقل: ساختار استاندارد وردپرس، و ساختار تکرارشونده‌ی
            # عمومی (برای سایت‌های غیر وردپرسی) — بزرگ‌ترین عدد معتبر می‌شود
            wordpress_count = (_count_actual_review_items(parsed_page.soup)
                               if _has_actual_review_items(parsed_page.soup) else 0)
            repeated_count = _count_repeated_comment_items(parsed_page.soup)
            actual_count = max(wordpress_count, repeated_count)

            if actual_count > 0:
                score = min(actual_count / get_threshold("e3_review_count_for_full_score"), 1.0)
                return IndicatorResult(code="E3", value=score, raw_details={
                    "reason": "heuristic_match_no_schema",
                    "review_count": actual_count,
                    "counting_method": ("wordpress_standard" if wordpress_count >= repeated_count
                                        else "repeated_structure"),
                    "text_signal": text_signal,
                    "structural_signal": structural_signal,
                    "wp_comment_form_present": wp_comment_form_present,
                    "note": "بر پایه‌ی شمارش نظرهای واقعی در ساختار HTML صفحه است "
                            "(نه تایید رسمی از طریق داده ساختاریافته schema.org).",
                })

            return IndicatorResult(code="E3", value=0.0, raw_details={
                "reason": "comment_section_found_but_empty",
                "text_signal": text_signal,
                "structural_signal": structural_signal,
                "wp_comment_form_present": wp_comment_form_present,
                "note": "بخش/فرم نظردهی در صفحه پیدا شد، ولی هیچ نظر واقعاً "
                        "ثبت‌شده‌ای یافت نشد — امتیاز صفر است چون شاهدی از "
                        "تجربه‌ی واقعی کاربران وجود ندارد، اما این با «هیچ "
                        "قابلیت نظردهی‌ای نیست» فرق دارد.",
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
