# -*- coding: utf-8 -*-
"""
تشخیص نشانه‌های فنی خاص وردپرس در HTML — بر پایه ساختار فنی وردپرس
(action فرم، id استاندارد)، نه حدس زبانی از روی نام کلاس/کلمه‌ی
فارسی. این‌ها بخش هسته‌ای خودِ وردپرس‌اند و برخلاف نام کلاس‌ها که
قالب‌به‌قالب فرق می‌کنند، ثابت می‌مانند.

استفاده در دو extractor با دو هدف متفاوت:
  - experience_extractor.py (E3): تشخیص *مثبت* — «آیا این صفحه اصلاً
    قابلیت نظردهی دارد؟» (برای تفکیک «فرم خالی» از «هیچ نشانه‌ای نیست»)
  - trust_extractor.py (T4): تشخیص *منفی* — «این فرم خاص را از شمارش
    فرم تماس کنار بگذار، چون فرم ثبت نظر است نه فرم تماس»

یافته‌ی رفع باگ: قبلاً این منطق فقط داخل experience_extractor.py بود؛
trust_extractor.py (T4) هیچ فیلتری نداشت و هر <form> روی صفحه (از
جمله همین فرم ثبت نظر وردپرسی) را «فرم تماس» حساب می‌کرد. حالا هر دو
از همین یک تعریف مشترک استفاده می‌کنند تا دوباره از هم واگرا نشوند.
"""

WP_COMMENT_FORM_ACTION_PATTERN = "wp-comments-post.php"


def is_wp_comment_form_tag(form_tag) -> bool:
    """آیا این تگ <form> خاص، فرم استاندارد ثبت نظر وردپرس است؟"""
    action = (form_tag.get("action") or "").lower()
    form_id = (form_tag.get("id") or "").lower()
    return WP_COMMENT_FORM_ACTION_PATTERN in action or form_id == "commentform"


def has_wp_comment_form(soup) -> bool:
    """
    آیا در کل صفحه (هر جایی)، یک فرم/بخش ثبت نظر وردپرسی وجود دارد؟
    شامل id="respond" هم می‌شود چون بخش پاسخ‌دهی وردپرس، حتی اگر خودِ
    فرم داخلش با ساختار غیرمعمول باشد، همیشه با همین id ساخته می‌شود.
    """
    for form in soup.find_all("form"):
        if is_wp_comment_form_tag(form):
            return True
    return soup.find(id="respond") is not None
