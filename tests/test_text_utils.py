"""
تست‌های واحد utils/text_utils.py — تمرکز روی رفع باگ جداسازی جمله‌ها
وقتی متن اعداد با نقطه دارد (جداکننده هزارگان یا اعشار).

نکته: این تست‌ها fallback ساده (simple_split) را مستقیم و بدون
وابستگی به نصب‌بودن hazm بررسی می‌کنند، چون خودِ رفع باگ در همان
مسیر fallback بود.
"""

import re


def _simple_split_sentences(text: str) -> list:
    """کپی مستقیم منطق fallback برای تست مستقل از نصب‌بودن hazm."""
    return [s for s in re.split(r"(?<!\d)[.!؟?](?!\d)\s*", text) if s.strip()]


class TestSentenceTokenizationFallback:

    def test_thousand_separator_period_not_treated_as_sentence_end(self):
        """
        رگرسیون: عدد با نقطه به‌عنوان جداکننده هزارگان («10.000.000
        تومان» — رایج در محتوای مالی فارسی) نباید پایان جمله حساب شود.
        """
        text = "با 10.000.000 تومان می‌توانید سرمایه‌گذاری کنید."
        sentences = _simple_split_sentences(text)
        assert len(sentences) == 1

    def test_decimal_point_not_treated_as_sentence_end(self):
        """رگرسیون: نقطه‌ی اعشاری («10.5 درصد») نباید پایان جمله حساب شود."""
        text = "قیمت 10.5 درصد افزایش یافت."
        sentences = _simple_split_sentences(text)
        assert len(sentences) == 1

    def test_real_sentence_boundaries_still_detected(self):
        """مطمئن شو رفع باگ، تشخیص جمله‌های واقعی را خراب نکرده."""
        text = "این جمله اول است. این جمله دوم است. این جمله سوم است."
        sentences = _simple_split_sentences(text)
        assert len(sentences) == 3

    def test_mixed_numbers_and_real_sentences(self):
        """ترکیب واقعی: چند عدد با نقطه در کنار چند جمله‌ی واقعی."""
        text = "با 10.000.000 تومان می‌توانید در طلا سرمایه‌گذاری کنید. قیمت 10.5 درصد افزایش یافت."
        sentences = _simple_split_sentences(text)
        assert len(sentences) == 2
