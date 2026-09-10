"""
تست‌های واحد برای ماژول‌های Extractor.

اجرا: pytest tests/
"""

from parser.html_parser import parse_html
from extractors.experience_extractor import ExperienceExtractor
from extractors.expertise_extractor import ExpertiseExtractor
from extractors.authority_extractor import AuthorityExtractor
from extractors.trust_extractor import TrustExtractor


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

SAMPLE_HTML_TINY_ARTICLE = """
<html><body>
<article><p>من این محصول را دوست دارم زیاد.</p></article>
</body></html>
"""

# مقاله‌ای که فقط *موضوعش* پزشکان است، بدون هیچ بایلاین/امضای نویسنده —
# برای رگرسیون مورد ۹ (X1 قبلا کل صفحه را برای «دکتر» می‌گشت)
SAMPLE_HTML_DOCTOR_TOPIC_NO_BYLINE = """
<html><body><article><p>{filler_before} دکترها معمولا از چند آزمایش استفاده می‌کنند
و دکتر باید علائم بیمار را بررسی کند تا دکتر قلب بتواند تشخیص دقیق بدهد. {filler_after}</p></article></body></html>
""".format(filler_before=" ".join(["کلمه"] * 100), filler_after=" ".join(["کلمه"] * 100))

SAMPLE_HTML_WITH_AUTHOR_BYLINE = """
<html><body><article>
<p>این یک مقاله عادی است بدون هیچ اشاره‌ای به عناوین تخصصی در متن اصلی.</p>
<div class="author-box">نویسنده: دکتر علی رضایی</div>
</article></body></html>
"""

SAMPLE_HTML_WITH_VIDEO_IFRAMES = """
<html><body>
<div>محتوای اصلی صفحه اینجاست و کاملا معمولی است.</div>
<div><iframe src="https://www.youtube.com/embed/abc123"></iframe></div>
<div><iframe src="https://www.aparat.com/video/xyz"></iframe></div>
<div><iframe src="https://player.vimeo.com/video/999"></iframe></div>
</body></html>
"""

SAMPLE_HTML_WITH_AD_BANNER = """
<html><body>
<div class="ad-banner">تبلیغ اینجا</div>
<div>محتوای معمولی</div>
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

    def test_e2_missing_for_too_short_text(self):
        """
        رگرسیون مورد ۱۰: صفحه ۶-۷ کلمه‌ای با یک «من» نباید امتیاز کامل
        بگیرد؛ باید is_missing=True برگرداند (متن برای سنجش قابل‌اتکا نیست).
        """
        parsed = parse_html(SAMPLE_HTML_TINY_ARTICLE, "https://test.ir/tiny")
        result = ExperienceExtractor()._e2_first_person_density(parsed)
        assert result.is_missing is True
        assert result.value is None


class TestExpertiseExtractor:

    def test_x1_ignores_specialized_title_outside_byline_area(self):
        """
        رگرسیون مورد ۹: مقاله‌ای که فقط *موضوعش* پزشکان است (بدون نویسنده‌ی
        مشخص) دیگر نباید فقط به‌خاطر تکرار «دکتر» در بدنه‌ی متن امتیاز
        title_score بگیرد.
        """
        parsed = parse_html(SAMPLE_HTML_DOCTOR_TOPIC_NO_BYLINE, "https://test.ir/medical-article")
        result = ExpertiseExtractor()._x1_author_credentials(parsed)
        assert result.raw_details["title_score"] == 0.0

    def test_x1_detects_specialized_title_in_author_byline(self):
        """وقتی «دکتر» واقعاً در ناحیه‌ی امضای نویسنده (author-box) باشد، باید تشخیص داده شود."""
        parsed = parse_html(SAMPLE_HTML_WITH_AUTHOR_BYLINE, "https://test.ir/article-with-author")
        result = ExpertiseExtractor()._x1_author_credentials(parsed)
        assert result.raw_details["title_score"] == 1.0


class TestAuthorityExtractor:

    def test_a1_edu_domain_scores_top_tier_not_default(self):
        """
        رگرسیون مورد ۷: یک دامنه .edu باید هم‌تراز .ac.ir/.gov.ir (۱.۰)
        امتیاز بگیرد، نه امتیاز پیش‌فرض ۰.۲ (که پایین‌تر از یک .com
        معمولی با ۰.۴ بود).
        """
        parsed = parse_html("<html><body>صفحه</body></html>", "https://harvard.edu/research")
        result = AuthorityExtractor()._a1_institutional_verification(parsed)
        assert result.value == 1.0


class TestTrustExtractor:

    def test_t5_known_video_iframes_not_counted_as_ads(self):
        """
        رگرسیون مورد ۱۱: iframe های ویدیوی شناخته‌شده (یوتیوب/آپارات/ویمیو)
        نباید تبلیغ حساب شوند؛ صفحه‌ای با فقط این‌ها باید امتیاز کامل بگیرد.
        """
        parsed = parse_html(SAMPLE_HTML_WITH_VIDEO_IFRAMES, "https://test.ir/videos")
        result = TrustExtractor()._t5_ad_density(parsed)
        assert result.raw_details["ad_iframe_count"] == 0
        assert result.value == 1.0

    def test_t5_actual_ad_banner_still_detected(self):
        """یک div با class واقعاً تبلیغاتی (ad-banner) باید همچنان تبلیغ حساب شود."""
        parsed = parse_html(SAMPLE_HTML_WITH_AD_BANNER, "https://test.ir/with-ad")
        result = TrustExtractor()._t5_ad_density(parsed)
        assert result.raw_details["ad_elements"] == 1

    def test_t5_detects_ad_network_loader_script_without_rendered_iframe(self):
        """
        بهبود T5: وقتی تبلیغ هنوز با جاوااسکریپت رندر نشده ولی اسکریپت
        لودر یک شبکه‌ی تبلیغاتی شناخته‌شده (مثل گوگل ادسنس) در HTML خام
        هست، باید همین اسکریپت به‌عنوان نشانه‌ی تبلیغ شمرده شود.
        """
        html_with_adsense_script = """
        <html><head>
        <script async src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client=ca-pub-123"></script>
        </head><body><div>محتوای اصلی صفحه</div></body></html>
        """
        parsed = parse_html(html_with_adsense_script, "https://test.ir/page-with-ad-script")
        result = TrustExtractor()._t5_ad_density(parsed)
        assert "googlesyndication.com" in result.raw_details["ad_network_scripts_detected"]
        assert result.raw_details["ad_elements"] >= 1

    def test_t6_parses_schema_date_instead_of_discarding_it(self):
        """
        رگرسیون مورد ۸: وقتی dateModified در JSON-LD موجود است، T6 دیگر
        نباید آن را نادیده بگیرد و is_missing برگرداند؛ باید امتیاز واقعی
        بر پایه‌ی همان تاریخ محاسبه کند.
        """
        html_with_schema_date = """
        <html><head>
        <script type="application/ld+json">
        {"@type": "Article", "dateModified": "2024-01-01T00:00:00Z"}
        </script>
        </head><body>محتوا</body></html>
        """
        parsed = parse_html(html_with_schema_date, "https://test.ir/dated-article")
        result = TrustExtractor()._t6_content_freshness(parsed)
        assert result.is_missing is False
        assert result.raw_details["source"] == "schema_json_ld"
