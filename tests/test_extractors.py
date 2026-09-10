"""
تست‌های واحد برای ماژول‌های Extractor.

اجرا: pytest tests/
"""

from parser.html_parser import parse_html
from extractors.experience_extractor import ExperienceExtractor


SAMPLE_HTML_WITH_EXPERIENCE = """
<html><body>
<article>
<p>من به مدت ۱۰ سال در حوزه تعمیر خودرو کار کرده‌ام و این تجربه به من کمک زیادی کرد.</p>
</article>
</body></html>
"""

SAMPLE_HTML_WITHOUT_EXPERIENCE = """
<html><body>
<article>
<p>این محصول دارای مشخصات فنی زیر است.</p>
</article>
</body></html>
"""

SAMPLE_HTML_PRODUCT_PAGE = """
<html><body>
<article>
<p>قیمت: ۲۵۰,۰۰۰ تومان</p>
<button>افزودن به سبد خرید</button>
</article>
</body></html>
"""


class TestExperienceExtractor:

    def test_e1_detects_explicit_experience_phrase(self):
        """E1 باید برای متنی با عبارت صریح تجربه، امتیاز کامل (۱.۰) برگرداند."""
        parsed = parse_html(SAMPLE_HTML_WITH_EXPERIENCE, "https://test.ir/article")
        result = ExperienceExtractor()._e1_practical_experience_evidence(parsed)
        assert result.value == 1.0
        assert result.raw_details["has_explicit_duration"] is True

    def test_e1_zero_when_no_experience_evidence(self):
        """E1 باید برای متن بدون هیچ شاهد تجربه، امتیاز ۰ برگرداند."""
        parsed = parse_html(SAMPLE_HTML_WITHOUT_EXPERIENCE, "https://test.ir/page")
        result = ExperienceExtractor()._e1_practical_experience_evidence(parsed)
        assert result.value == 0.0

    def test_e2_not_applicable_for_product_page(self):
        """E2 باید برای صفحه‌ای با نشانه‌های صفحه محصول، applicable=False برگرداند."""
        parsed = parse_html(SAMPLE_HTML_PRODUCT_PAGE, "https://test.ir/product/1")
        result = ExperienceExtractor()._e2_first_person_density(parsed)
        assert result.applicable is False

    def test_e2_applicable_for_article_page(self):
        """E2 باید برای یک صفحه مقاله معمولی، applicable=True بماند."""
        parsed = parse_html(SAMPLE_HTML_WITH_EXPERIENCE, "https://test.ir/article")
        result = ExperienceExtractor()._e2_first_person_density(parsed)
        assert result.applicable is True
