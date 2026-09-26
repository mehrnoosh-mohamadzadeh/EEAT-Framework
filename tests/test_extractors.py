"""
تست‌های واحد برای ماژول‌های Extractor.

اجرا: pytest tests/
"""

from unittest.mock import patch, MagicMock

from parser.html_parser import parse_html
from extractors.experience_extractor import ExperienceExtractor, _has_review_signal
from extractors.expertise_extractor import ExpertiseExtractor
from extractors.authority_extractor import AuthorityExtractor
from extractors.trust_extractor import TrustExtractor, CONTACT_LINK_PATTERNS, PRIVACY_LINK_PATTERNS


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


SAMPLE_HTML_WP_EMPTY_COMMENT_FORM = """
<html><body><article>
<p>یک مقاله معمولی که هیچ کلمه‌ی رایج نظرات در متنش نیست.</p>
<div id="comments">
<div id="respond" class="comment-respond">
<form action="https://example.com/wp-comments-post.php" method="post" id="commentform" class="comment-form">
<p class="comment-form-comment"><textarea id="comment" name="comment"></textarea></p>
<p class="form-submit"><input name="submit" type="submit" value="ثبت کردن نظر" /></p>
</form>
</div>
</div>
</article></body></html>
"""

SAMPLE_HTML_WP_WITH_REAL_COMMENT = SAMPLE_HTML_WP_EMPTY_COMMENT_FORM.replace(
    '<div id="comments">',
    '<div id="comments"><ol class="comment-list"><li class="comment">'
    '<div class="comment-body"><div class="comment-author">علی</div>خیلی مفید بود</div></li></ol>'
)

SAMPLE_HTML_NO_COMMENT_FEATURE_AT_ALL = """
<html><body><article><p>یک مقاله ساده درباره آشپزی ایتالیایی و دستور پخت پاستا.</p></article></body></html>
"""


class TestExperienceExtractor:

    def test_e3_wp_comment_form_present_but_no_real_review_scores_zero_with_distinct_reason(self):
        """
        رگرسیون: سایت وردپرسی با فرم نظردهی خالی (نمونه‌ی واقعی
        dr-moghimi.com) باید صفر بگیرد، ولی با دلیل متفاوت از
        «هیچ نشانه‌ای از نظردهی نیست» — چون فرم واقعاً پیدا شده،
        فقط نظری ثبت نشده.
        """
        parsed = parse_html(SAMPLE_HTML_WP_EMPTY_COMMENT_FORM, "https://example.com/article")
        result = ExperienceExtractor()._e3_user_reviews(parsed)
        assert result.value == 0.0
        assert result.raw_details["reason"] == "comment_section_found_but_empty"
        assert result.raw_details["wp_comment_form_present"] is True

    def test_e3_detects_actual_review_when_comment_list_present(self):
        """همان صفحه، ولی با یک نظر واقعی ثبت‌شده در comment-list — باید امتیاز جزئی بگیرد، نه صفر."""
        parsed = parse_html(SAMPLE_HTML_WP_WITH_REAL_COMMENT, "https://example.com/article")
        result = ExperienceExtractor()._e3_user_reviews(parsed)
        assert result.value > 0.0
        assert result.raw_details["reason"] == "heuristic_match_no_schema"

    def test_e3_no_comment_feature_at_all_has_different_reason_than_empty_form(self):
        """صفحه‌ای که اصلاً فرم/بخش نظردهی ندارد باید دلیل متفاوتی از «پیدا شد ولی خالی است» داشته باشد."""
        parsed = parse_html(SAMPLE_HTML_NO_COMMENT_FEATURE_AT_ALL, "https://example.com/no-comments")
        result = ExperienceExtractor()._e3_user_reviews(parsed)
        assert result.value == 0.0
        assert result.raw_details["reason"] == "no_evidence_found"

    def test_e3_numeric_comment_count_detected(self):
        """شمارنده‌ی عددی («۳ دیدگاه») باید مستقیماً به‌عنوان تعداد نظر واقعی استفاده شود."""
        html = """
        <html><body><article><p>مقاله</p>
        <div class="comments-title">۳ دیدگاه</div>
        </article></body></html>
        """
        parsed = parse_html(html, "https://example.com/article-with-count")
        result = ExperienceExtractor()._e3_user_reviews(parsed)
        assert result.raw_details["reason"] == "heuristic_numeric_comment_count"
        assert result.raw_details["review_count"] == 3

    def test_negation_window_catches_farther_negation_words(self):
        """
        رگرسیون مورد ۱۱: پنجره‌ی تشخیص نفی قبلاً فقط ۲ کلمه بود، پس
        جمله‌ی طبیعی «بدون هیچ اشاره‌ای به نظرات» (۴ کلمه فاصله بین
        «بدون» و «نظرات») تشخیص داده نمی‌شد و اشتباهاً True برمی‌گشت.
        """
        text = "یک مقاله بدون هیچ اشاره‌ای به نظرات یا فرم نظردهی است."
        assert _has_review_signal(text) is False

    def test_negation_window_still_detects_real_positive_signal(self):
        """مطمئن شو رفع باگ نفی، جمله‌ی مثبت واقعی را کاذب رد نمی‌کند."""
        text = "نظرات خودتون رو برای ما بنویسید."
        assert _has_review_signal(text) is True

    def test_e4_counts_only_images_with_specific_non_generic_alt_text(self):
        """
        E4: تصویر با alt خاص (نه ژنریک) باید «واجد شرایط» حساب شود؛
        تصویر بدون alt یا با alt ژنریک (مثل «photo») نباید.
        """
        html = """
        <html><body><article>
        <img src="a.jpg" alt="نمودار رشد فروش سال ۱۴۰۲">
        <img src="b.jpg" alt="photo">
        <img src="c.jpg">
        </article></body></html>
        """
        parsed = parse_html(html, "https://example.com/article")
        result = ExperienceExtractor()._e4_original_images(parsed)
        assert result.raw_details["qualified_images"] == 1
        assert result.raw_details["total_images_in_content"] == 3

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

    def test_bio_link_pattern_matches_natural_spacing(self):
        """
        همان کلاس باگ CONTACT_LINK_PATTERNS: نسخه‌ی قبل BIO_LINK_PATTERNS
        فقط عبارت دقیق «درباره-نویسنده» (با خط‌تیره) را می‌پذیرفت؛ متن
        طبیعی لینک («درباره نویسنده» با فاصله) پیدا نمی‌شد.
        """
        from extractors.expertise_extractor import BIO_LINK_PATTERNS
        assert any(p in "درباره نویسنده" for p in BIO_LINK_PATTERNS)

    def test_x2_counts_only_personal_profile_links(self):
        """X2: فقط لینک‌های پروفایل شخصی (linkedin.com/in/, scholar, orcid) باید شمرده شوند، نه هر لینک لینکدین."""
        html = """
        <html><body>
        <a href="https://linkedin.com/in/johndoe">پروفایل من</a>
        <a href="https://linkedin.com/company/example">صفحه شرکت</a>
        <a href="https://orcid.org/0000-0001">ORCID</a>
        </body></html>
        """
        parsed = parse_html(html, "https://example.com/article")
        result = ExpertiseExtractor()._x2_professional_profile_links(parsed)
        assert result.raw_details["profile_links_found"] == 2

    def test_x3_ratio_of_authoritative_outbound_links(self):
        """X3: نسبت لینک‌های خروجی به دامنه معتبر از کل لینک‌های خروجی."""
        html = """
        <html><body>
        <a href="https://harvard.edu/paper">منبع معتبر</a>
        <a href="https://random-blog.com/post">منبع تصادفی</a>
        </body></html>
        """
        parsed = parse_html(html, "https://example.com/article")
        result = ExpertiseExtractor()._x3_authoritative_citations_ratio(parsed)
        assert result.raw_details["authoritative_count"] == 1
        assert result.raw_details["total_outbound_links"] == 2

    def test_x4_longer_well_structured_text_scores_higher(self):
        """X4: متن بلندتر و ساختاریافته‌تر (با تیتر) باید امتیاز بالاتری از متن کوتاه بدون تیتر بگیرد."""
        short_html = "<html><body><article><p>یک متن کوتاه.</p></article></body></html>"
        long_html = "<html><body><article><h2>بخش اول</h2><p>" + \
            (" ".join(["این یک جمله ی نمونه برای طولانی کردن متن است."] * 100)) + \
            "</p><h2>بخش دوم</h2><p>" + \
            (" ".join(["ادامه ی متن با جملات بیشتر برای رسیدن به طول کافی."] * 100)) + \
            "</p></article></body></html>"

        parsed_short = parse_html(short_html, "https://example.com/short")
        parsed_long = parse_html(long_html, "https://example.com/long")

        result_short = ExpertiseExtractor()._x4_content_depth_structure(parsed_short)
        result_long = ExpertiseExtractor()._x4_content_depth_structure(parsed_long)
        assert result_long.value > result_short.value

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

    def test_x5_detects_citation_marker_outside_anchor_tag(self):
        """
        رگرسیون: کلمه‌ی زمینه‌ساز («طبق») در جمله‌ی طبیعی فارسی بیرون
        از تگ لینک است («طبق <a>این گزارش</a>») — باید همچنان تشخیص
        داده شود، نه فقط وقتی داخل خودِ متن لینک باشد.
        """
        html = ('<html><body><article><p>طبق '
                '<a href="https://harvard.edu/research/study1">این پژوهش</a> '
                'نتایج جالبی به دست آمد.</p></article></body></html>')
        parsed = parse_html(html, "https://test.ir/article-with-citation")
        result = ExpertiseExtractor()._x5_citation_context(parsed)
        assert result.value == 1.0


class TestAuthorityExtractor:

    def test_a2_full_organization_schema_scores_high(self):
        """A2: بلوک Organization با همه ۵ فیلد باید امتیاز کامل بگیرد."""
        html = """
        <html><head>
        <script type="application/ld+json">
        {"@type": "Organization", "name": "شرکت نمونه", "url": "https://example.com",
         "logo": "https://example.com/logo.png", "sameAs": ["https://twitter.com/example"],
         "address": "تهران"}
        </script>
        </head><body>صفحه</body></html>
        """
        parsed = parse_html(html, "https://example.com")
        result = AuthorityExtractor()._a2_organization_schema_completeness(parsed)
        assert result.value == 1.0

    def test_a2_falls_back_to_social_links_when_no_schema(self):
        """A2: بدون schema سازمانی، لینک‌های شبکه اجتماعی واقعی باید حداکثر نیمی از امتیاز کامل بدهند."""
        html = """
        <html><body>
        <a href="https://twitter.com/example">توییتر</a>
        <a href="https://instagram.com/example">اینستاگرام</a>
        <a href="https://facebook.com/example">فیسبوک</a>
        </body></html>
        """
        parsed = parse_html(html, "https://example.com")
        result = AuthorityExtractor()._a2_organization_schema_completeness(parsed)
        assert result.value <= 0.5
        assert result.raw_details["reason"] == "no_schema_but_social_links_found"

    def test_a2_zero_when_neither_schema_nor_social_links(self):
        """A2: بدون schema و بدون هیچ لینک شبکه اجتماعی، باید صفر بگیرد."""
        html = "<html><body><p>صفحه‌ای بدون هیچ نشانه‌ی هویت سازمانی.</p></body></html>"
        parsed = parse_html(html, "https://example.com")
        result = AuthorityExtractor()._a2_organization_schema_completeness(parsed)
        assert result.value == 0.0

    def test_a1_edu_domain_scores_top_tier_not_default(self):
        """
        رگرسیون مورد ۷: یک دامنه .edu باید هم‌تراز .ac.ir/.gov.ir (۱.۰)
        امتیاز بگیرد، نه امتیاز پیش‌فرض ۰.۲ (که پایین‌تر از یک .com
        معمولی با ۰.۴ بود).
        """
        parsed = parse_html("<html><body>صفحه</body></html>", "https://harvard.edu/research")
        result = AuthorityExtractor()._a1_institutional_verification(parsed)
        assert result.value == 1.0

    def test_a3_email_and_website_address_not_counted_as_physical_address(self):
        """
        رگرسیون مورد ۱۰: «آدرس ایمیل: ...» یا «آدرس سایت: ...» نباید
        به‌عنوان آدرس فیزیکی واقعی شمرده شود.
        """
        html = """
        <html><body>
        <a href="/about-us">درباره ما</a>
        <p>آدرس ایمیل ما: info@example.com است. آدرس سایت ما هم example.com می‌باشد.</p>
        </body></html>
        """
        parsed = parse_html(html, "https://example.com/page")
        result = AuthorityExtractor()._a3_about_us_verifiability(parsed)
        assert "physical_address" not in result.raw_details["details_found"]

    def test_a3_real_physical_address_still_detected(self):
        """یک آدرس فیزیکی واقعی (با کلمات ساختاری خیابان/میدان) باید همچنان تشخیص داده شود."""
        html = """
        <html><body>
        <a href="/about-us">درباره ما</a>
        <p>آدرس: تهران، خیابان ولیعصر، پلاک ۱۲۳</p>
        </body></html>
        """
        parsed = parse_html(html, "https://example.com/page")
        result = AuthorityExtractor()._a3_about_us_verifiability(parsed)
        assert "physical_address" in result.raw_details["details_found"]


class TestTrustExtractor:

    def test_contact_link_found_with_natural_spacing_not_just_dashed_slug(self):
        """
        رگرسیون (نمونه واقعی dr-moghimi.com): نسخه‌ی قبل فقط عبارت
        دقیق «تماس-با-ما» را می‌پذیرفت. سایت واقعی متن لینک «تماس با
        دکتر» (با فاصله، نه خط‌تیره، و کلمه‌ی متفاوت) داشت که اصلاً
        پیدا نمی‌شد. حالا کلمه‌ی پایه «تماس» به‌تنهایی کافی است.
        """
        html = """
        <html><body>
        <aside><a href="https://dr-moghimi.com/%d8%aa%d9%85%d8%a7%d8%b3-%d8%a8%d8%a7-%d8%af%da%a9%d8%aa%d8%b1/">تماس با دکتر</a></aside>
        </body></html>
        """
        parsed = parse_html(html, "https://dr-moghimi.com/article")
        href = TrustExtractor()._find_matching_link_href(parsed, CONTACT_LINK_PATTERNS)
        assert href is not None

    def test_privacy_link_found_with_natural_spacing(self):
        """همان کلاس باگ برای PRIVACY_LINK_PATTERNS: «حریم خصوصی» با فاصله باید پیدا شود، نه فقط «حریم-خصوصی»."""
        html = '<html><body><a href="/privacy-page">حریم خصوصی</a></body></html>'
        parsed = parse_html(html, "https://example.com/article")
        href = TrustExtractor()._find_matching_link_href(parsed, PRIVACY_LINK_PATTERNS)
        assert href is not None

    def test_t1_https_binary(self):
        """T1: صفحه با https باید ۱.۰ و صفحه با http باید ۰.۰ بگیرد."""
        parsed_https = parse_html("<html><body>صفحه</body></html>", "https://example.com/page")
        parsed_http = parse_html("<html><body>صفحه</body></html>", "http://example.com/page")
        assert TrustExtractor()._t1_https(parsed_https).value == 1.0
        assert TrustExtractor()._t1_https(parsed_http).value == 0.0

    def test_t2_zero_for_non_https_url_without_network_call(self):
        """T2: برای URL غیر https باید بدون هیچ تلاش شبکه‌ای مستقیم صفر برگرداند."""
        parsed = parse_html("<html><body>صفحه</body></html>", "http://example.com/page")
        result = TrustExtractor()._t2_ssl_certificate_validity(parsed)
        assert result.value == 0.0
        assert result.raw_details["reason"] == "not_https"

    def test_t2_valid_certificate_scores_full_with_mocked_network(self):
        """T2: با mock کردن اتصال شبکه (بدون نیاز به اینترنت واقعی)، گواهی معتبر باید امتیاز کامل بدهد."""
        parsed = parse_html("<html><body>صفحه</body></html>", "https://example.com/page")
        fake_cert = {"issuer": (("organizationName", "Fake CA"),)}

        mock_ssock = MagicMock()
        mock_ssock.getpeercert.return_value = fake_cert
        mock_ssock.__enter__ = MagicMock(return_value=mock_ssock)
        mock_ssock.__exit__ = MagicMock(return_value=False)

        mock_context = MagicMock()
        mock_context.wrap_socket.return_value = mock_ssock

        mock_sock = MagicMock()
        mock_sock.__enter__ = MagicMock(return_value=mock_sock)
        mock_sock.__exit__ = MagicMock(return_value=False)

        with patch("extractors.trust_extractor.ssl.create_default_context", return_value=mock_context), \
             patch("extractors.trust_extractor.socket.create_connection", return_value=mock_sock):
            result = TrustExtractor()._t2_ssl_certificate_validity(parsed)

        assert result.value == 1.0
        assert result.raw_details["issuer"] == fake_cert["issuer"]

    def test_t2_missing_on_network_error_not_crash(self):
        """T2: خطای شبکه (نه مشکل گواهی) باید is_missing بدهد، نه کرش یا صفر قطعی."""
        import socket as socket_module
        parsed = parse_html("<html><body>صفحه</body></html>", "https://example.com/page")

        with patch("extractors.trust_extractor.socket.create_connection",
                   side_effect=socket_module.timeout("timed out")):
            result = TrustExtractor()._t2_ssl_certificate_validity(parsed)

        assert result.is_missing is True

    def test_t3_zero_when_no_privacy_link(self):
        """T3: بدون لینک حریم خصوصی، باید صفر بگیرد (بدون تلاش برای دانلود چیزی)."""
        html = "<html><body><p>صفحه‌ای بدون هیچ لینک حریم خصوصی.</p></body></html>"
        parsed = parse_html(html, "https://example.com/page")
        result = TrustExtractor()._t3_privacy_policy(parsed)
        assert result.value == 0.0

    def test_t3_scores_by_linked_page_word_count(self):
        """T3: با mock کردن دانلود صفحه‌ی حریم خصوصی، امتیاز باید بر اساس طول واقعی آن صفحه باشد."""
        html = '<html><body><a href="/privacy">حریم خصوصی</a></body></html>'
        parsed = parse_html(html, "https://example.com/page")

        long_privacy_text = " ".join(["کلمه"] * 300)
        with patch("extractors.trust_extractor.fetch_linked_page_text", return_value=long_privacy_text):
            result = TrustExtractor()._t3_privacy_policy(parsed)

        assert result.value == 1.0
        assert result.raw_details["linked_page_word_count"] == 300

    def test_t4_email_address_not_counted_as_physical_address(self):
        """رگرسیون مورد ۱۰: «آدرس ایمیل» نباید کانال «آدرس فیزیکی» را در T4 فعال کند."""
        html = "<html><body><p>آدرس ایمیل ما: info@example.com است.</p></body></html>"
        parsed = parse_html(html, "https://example.com/page")
        result = TrustExtractor()._t4_contact_us(parsed)
        assert "physical_address" not in result.raw_details["channels_found"]
        assert "email" in result.raw_details["channels_found"]

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

    def test_t6_falls_back_to_wayback_when_no_date_on_page(self, monkeypatch):
        """
        فاز ۵: وقتی صفحه نه schema date دارد نه تاریخ شمسی در متن، و
        wayback_fallback_for_t6 در settings فعال است، باید تلاش کند
        از Wayback Machine تخمین بزند. شبکه واقعی mock می‌شود.
        """
        import datetime
        import extractors.trust_extractor as trust_module

        monkeypatch.setattr(trust_module, "get_external_data_setting",
                             lambda key, default=None: True if key == "wayback_fallback_for_t6" else default)
        monkeypatch.setattr(trust_module, "estimate_last_content_change",
                             lambda url, timeout=10: datetime.date(2024, 1, 1))

        html_no_date = "<html><body><p>صفحه‌ای بدون هیچ تاریخ قابل‌استخراج</p></body></html>"
        parsed = parse_html(html_no_date, "https://test.ir/no-date-page")
        result = TrustExtractor()._t6_content_freshness(parsed)
        assert result.is_missing is False
        assert result.raw_details["source"] == "wayback_machine_estimate"

    def test_t6_still_missing_when_wayback_disabled_and_no_date_found(self, monkeypatch):
        """وقتی wayback_fallback_for_t6 غیرفعال است و هیچ تاریخی نیست، رفتار قبلی (is_missing) حفظ می‌شود."""
        import extractors.trust_extractor as trust_module

        monkeypatch.setattr(trust_module, "get_external_data_setting",
                             lambda key, default=None: default)

        html_no_date = "<html><body><p>صفحه‌ای بدون هیچ تاریخ قابل‌استخراج</p></body></html>"
        parsed = parse_html(html_no_date, "https://test.ir/no-date-page-2")
        result = TrustExtractor()._t6_content_freshness(parsed)
        assert result.is_missing is True

    def test_t6_missing_when_wayback_enabled_but_returns_nothing(self, monkeypatch):
        """اگر Wayback فعال باشد ولی هیچ تاریخچه‌ای پیدا نکند (یا شبکه در دسترس نباشد)، همچنان باید is_missing برگردد، نه کرش."""
        import extractors.trust_extractor as trust_module

        monkeypatch.setattr(trust_module, "get_external_data_setting",
                             lambda key, default=None: True if key == "wayback_fallback_for_t6" else default)
        monkeypatch.setattr(trust_module, "estimate_last_content_change",
                             lambda url, timeout=10: None)

        html_no_date = "<html><body><p>صفحه‌ای بدون هیچ تاریخ قابل‌استخراج</p></body></html>"
        parsed = parse_html(html_no_date, "https://test.ir/no-date-page-3")
        result = TrustExtractor()._t6_content_freshness(parsed)
        assert result.is_missing is True

    def test_t6_finds_date_inside_at_graph(self):
        """رگرسیون: dateModified داخل @graph (الگوی رایج Yoast SEO) باید پیدا شود، نه نادیده گرفته شود."""
        html = """
        <html><head>
        <script type="application/ld+json">
        {"@graph": [{"@type": "Article", "dateModified": "2024-01-01T00:00:00Z"}]}
        </script>
        </head><body>محتوا</body></html>
        """
        parsed = parse_html(html, "https://test.ir/graph-dated-article")
        result = TrustExtractor()._t6_content_freshness(parsed)
        assert result.is_missing is False
        assert result.raw_details["source"] == "schema_json_ld"

    def test_t7_finds_types_inside_at_graph(self):
        """رگرسیون: انواع schema (Article/Person/Organization) داخل @graph باید همه پیدا شوند."""
        html = """
        <html><head>
        <script type="application/ld+json">
        {"@graph": [
            {"@type": "Organization", "name": "X"},
            {"@type": "Person", "name": "Y"},
            {"@type": "Article", "headline": "Z"}
        ]}
        </script>
        </head><body>محتوا</body></html>
        """
        parsed = parse_html(html, "https://test.ir/graph-full-article")
        result = TrustExtractor()._t7_structured_data_completeness(parsed)
        assert result.value == 1.0
        assert set(result.raw_details["found_types"]) == {"Organization", "Person", "Article"}

    def test_t4_wp_comment_form_not_counted_as_contact_form(self):
        """
        رگرسیون (نمونه واقعی dr-moghimi.com): فرم ثبت نظر وردپرسی
        نباید به‌عنوان فرم تماس شمرده شود.
        """
        html = """
        <html><body><article>
        <p>محتوای مقاله بدون هیچ اطلاعات تماسی.</p>
        <div id="respond" class="comment-respond">
        <form action="https://example.com/wp-comments-post.php" method="post" id="commentform" class="comment-form">
        <textarea name="comment"></textarea>
        </form>
        </div>
        </article></body></html>
        """
        parsed = parse_html(html, "https://example.com/article")
        result = TrustExtractor()._t4_contact_us(parsed)
        assert "contact_form" not in result.raw_details["channels_found"]

    def test_t4_real_contact_form_still_detected(self):
        """یک فرم تماس واقعی (نه فرم نظر/جستجو) باید همچنان شناسایی شود."""
        html = """
        <html><body><form id="contact-form-7" class="wpcf7-form">
        <input type="text" name="your-name" />
        <input type="email" name="your-email" />
        </form></body></html>
        """
        parsed = parse_html(html, "https://example.com/contact")
        result = TrustExtractor()._t4_contact_us(parsed)
        assert "contact_form" in result.raw_details["channels_found"]

    def test_t4_search_form_not_counted_as_contact_form(self):
        """جعبه جست‌وجو نباید به‌عنوان فرم تماس شمرده شود."""
        html = '<html><body><form role="search"><input type="search" name="s"/></form></body></html>'
        parsed = parse_html(html, "https://example.com/page")
        result = TrustExtractor()._t4_contact_us(parsed)
        assert "contact_form" not in result.raw_details["channels_found"]
