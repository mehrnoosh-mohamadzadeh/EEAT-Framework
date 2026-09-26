"""
توابع مشترک توکنایز متن فارسی — استفاده در E2 (experience_extractor)
و X4 (expertise_extractor).

هر دو تابع اول تلاش می‌کنند از Hazm (دقیق‌تر برای مرزهای کلمه در
فارسی، به‌خصوص با نیم‌فاصله) استفاده کنند. اگر Hazm نصب نباشد، به‌طور
خودکار به یک روش ساده‌تر (split در متن مبتنی بر فاصله) برمی‌گردند —
تا کد در هر دو حالت اجرا شود، فقط با دقت متفاوت. متد واقعاً استفاده‌شده
در raw_details هر شاخص ثبت می‌شود تا در گزارش/دیباگ مشخص باشد.
"""

import re


def tokenize_words(text: str) -> tuple[list[str], str]:
    """
    بازمی‌گرداند: (لیست کلمات, نام روش استفاده‌شده)
    نام روش یکی از: "hazm" یا "simple_split"
    """
    try:
        from hazm import word_tokenize as hazm_word_tokenize
        return hazm_word_tokenize(text), "hazm"
    except ImportError:
        return text.split(), "simple_split"


def tokenize_sentences(text: str) -> tuple[list[str], str]:
    """
    بازمی‌گرداند: (لیست جملات, نام روش استفاده‌شده)

    رفع باگ: fallback قبلی روی هر نقطه‌ای می‌شکست، حتی نقطه‌ای که
    بین دو رقم است (مثل جداکننده‌ی هزارگان در «10.000.000 تومان» یا
    اعشار در «10.5 درصد») — که در محتوای مالی فارسی خیلی رایج است.
    نتیجه‌اش این بود که یک متن مالی پر از عدد، به ده‌ها «جمله»ی
    تک‌کلمه‌ای (مثل «000») تقسیم می‌شد و میانگین طول جمله در X4 به‌شدت
    و به‌غلط پایین می‌آمد. حالا نقطه‌ای که بلافاصله قبل یا بعدش رقم
    باشد، پایان جمله حساب نمی‌شود.
    """
    try:
        from hazm import sent_tokenize as hazm_sent_tokenize
        sentences = hazm_sent_tokenize(text)
        return [s for s in sentences if s.strip()], "hazm"
    except ImportError:
        sentences = [s for s in re.split(r"(?<!\d)[.!؟?](?!\d)\s*", text) if s.strip()]
        return sentences, "simple_split"
