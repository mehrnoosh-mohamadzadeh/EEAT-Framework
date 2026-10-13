# -*- coding: utf-8 -*-
"""
تشخیص «نوع صفحه» و شاخص‌هایی که برای آن نوع قضاوت‌پذیر نیستند.

اصل: شاخصی «غیرقابل اعمال» می‌شود فقط وقتی آنچه می‌سنجد (مثلاً متن بلند، ارجاع
متنی، تصاویر داخل متن) اصلاً جزو ماهیت آن نوع صفحه نیست؛ نه وقتی صفحه صرفاً
ضعیف است. برای همین هر نوع، تشخیص سخت‌گیرانه (نشانه‌ی صریح + شرط مکمل) و دلیل
نوشته‌شده برای هر شاخص دارد. نوع‌های فعلی: ویدیومحور و محصول.

⚠️ عمداً نوع «خبر کوتاه/اطلاعیه» یا «صفحه‌ی کم‌محتوا» اضافه نشده: چنین قاعده‌ای
صفحه‌ی ضعیف و اسپم را «معاف» می‌کند و ابزار را قابل‌دور‌زدن می‌سازد.

ویدیومحور (هر دو شرط): ۱) نشانه‌ی صریح ویدیو (JSON-LD از نوع VideoObject، یا
og:type که با video شروع شود، یا twitter:card=player، یا تگ <video>/iframe
پخش‌کننده‌ی شناخته‌شده) و ۲) متن محتوای اصلی کمتر از video_page_max_words کلمه.

محصول: JSON-LD از نوع Product که فیلد offers (پیشنهاد فروش) دارد، یا عبارت صریح
خرید («افزودن به سبد خرید» و مشابه). وجود «تومان» یا «قیمت:» به‌تنهایی کافی نیست
(در خبر و مقاله‌ی مالی هم می‌آید). مقاله‌ی نقد محصول معمولاً Product بدون offers
دارد و محصول حساب نمی‌شود.
"""

from utils.json_ld_utils import flatten_json_ld_blocks
from utils.settings_loader import get_threshold
from utils.text_utils import tokenize_words

# شاخص‌هایی که برای هر نوع صفحه قضاوت نمی‌شوند، با دلیل هرکدام
VIDEO_EXCLUDED_INDICATORS = {
    "E1": "شواهد تجربه‌ی عملی در متن می‌آید؛ در ویدیو این شواهد دیده/شنیده می‌شود، نه نوشته.",
    "E2": "زبان اول‌شخص را در متن می‌سنجد؛ متن صفحه‌ی ویدیو فقط توضیح کوتاه است.",
    "E4": "تصاویر داخل متن را می‌شمارد؛ محتوای اصلی ویدیو است، نه تصویر.",
    "X3": "نسبت ارجاع به منابع معتبر را از لینک‌های متن می‌سنجد؛ لینک‌های صفحه‌ی ویدیو عمدتاً پیشنهاد و منو است، نه ارجاع.",
    "X4": "طول، خوانایی، عنوان‌بندی و تنوع واژگان متن را می‌سنجد؛ توضیح کوتاه ویدیو برای این سنجش جا ندارد.",
    "X5": "بافت متنی ارجاع را می‌سنجد؛ بدون متن ارجاع‌دار معنایی ندارد.",
}

_VIDEO_IFRAME_HOSTS = ("aparat.com", "youtube.com", "youtu.be", "vimeo.com",
                       "namava.ir", "dailymotion.com")


def _has_video_signal(parsed_page) -> str | None:
    """نام نشانه‌ی ویدیو را برمی‌گرداند، یا None اگر نشانه‌ای نیست."""
    for block in flatten_json_ld_blocks(parsed_page.json_ld_blocks):
        if not isinstance(block, dict):
            continue
        t = block.get("@type", "")
        types = t if isinstance(t, list) else [t]
        if "VideoObject" in types:
            return "json_ld_video_object"

    soup = parsed_page.soup
    og = soup.find("meta", attrs={"property": "og:type"})
    if og and str(og.get("content", "")).strip().lower().startswith("video"):
        return "og_type_video"
    tw = soup.find("meta", attrs={"name": "twitter:card"})
    if tw and str(tw.get("content", "")).strip().lower() == "player":
        return "twitter_card_player"

    main = parsed_page.main_content_soup
    if main.find("video") is not None or soup.find("video") is not None:
        return "video_tag"
    for iframe in soup.find_all("iframe"):
        src = (iframe.get("src") or iframe.get("data-src") or "").lower()
        if any(host in src for host in _VIDEO_IFRAME_HOSTS):
            return "video_iframe"
    return None


def detect_video_page(parsed_page) -> dict | None:
    """
    اگر صفحه ویدیومحور است {"signal": ..., "word_count": ...} برمی‌گرداند،
    وگرنه None.
    """
    signal = _has_video_signal(parsed_page)
    if signal is None:
        return None
    words, _method = tokenize_words(parsed_page.main_content_text)
    word_count = len(words)
    if word_count >= get_threshold("video_page_max_words"):
        return None
    return {"signal": signal, "word_count": word_count}


PRODUCT_EXCLUDED_INDICATORS = {
    "E2": "زبان اول‌شخص را می‌سنجد؛ توضیح محصول بیانِ تجربه‌ی شخصی نیست و نباید باشد.",
    "X3": "نسبت ارجاع به منابع معتبر را می‌سنجد؛ صفحه‌ی محصول ارجاع علمی ندارد و لازم هم ندارد.",
    "X5": "بافت متنی ارجاع را می‌سنجد؛ در توضیح محصول ارجاع‌دادن مرسوم نیست.",
}

# ثبت نوع‌ها: نام داخلی ← برچسب فارسی و شاخص‌های قضاوت‌نشده
PAGE_TYPES = {
    "video": {"label": "ویدیومحور",
              "reason": "محتوای اصلی ویدیو است و متن آن کوتاه است",
              "excluded": VIDEO_EXCLUDED_INDICATORS},
    "product": {"label": "محصول",
                "reason": "صفحه‌ی فروش یک کالاست",
                "excluded": PRODUCT_EXCLUDED_INDICATORS},
}

_ADD_TO_CART_PHRASES = ("افزودن به سبد خرید", "add to cart", "خرید این محصول")


def _has_product_signal(parsed_page) -> str | None:
    for block in flatten_json_ld_blocks(parsed_page.json_ld_blocks):
        if not isinstance(block, dict):
            continue
        t = block.get("@type", "")
        types = t if isinstance(t, list) else [t]
        if "Product" in types and block.get("offers"):
            return "json_ld_product_with_offers"
    text = parsed_page.soup.get_text(separator=" ", strip=True).lower()
    if any(phrase in text for phrase in _ADD_TO_CART_PHRASES):
        return "add_to_cart_phrase"
    return None


def detect_page_type(parsed_page) -> dict | None:
    """
    نوع صفحه را برمی‌گرداند: {"type": "video"|"product", "signal": ..., ...} یا None
    (صفحه‌ی معمولی). ویدیو بر محصول اولویت دارد.
    """
    video = detect_video_page(parsed_page)
    if video:
        return {"type": "video", **video}
    signal = _has_product_signal(parsed_page)
    if signal:
        return {"type": "product", "signal": signal}
    return None
