# -*- coding: utf-8 -*-
"""
تست‌های واحد utils/link_matching.py.

این ماژول قبلاً هیچ تستی نداشت — همین نبود تست باعث شد یک باگ حیاتی
(فاصله‌ی اضافی در _href_path_words که حتی ساده‌ترین حالت ممکن،
href="/contact" را می‌شکست) قبل از انتشار پیدا نشود. این فایل هم آن
رگرسیون و هم رفتار صحیح مورد انتظار (رد اسلاگ‌های نامرتبط، پذیرش
ترکیب‌های رایج) را قفل می‌کند.
"""

from utils.link_matching import find_matching_link_href


def _link(href="", text="", parent_text="", img_alt_text=""):
    return {"href": href, "text": text, "parent_text": parent_text, "img_alt_text": img_alt_text}


class TestHrefBasicMatching:
    """
    رگرسیون حیاتی: ساده‌ترین حالت ممکن — href دقیقاً برابر با خودِ
    الگو — باید همیشه مچ شود. این دقیقاً همان حالتی بود که باگ
    فاصله‌ی اضافی می‌شکست (چون کلمه‌ی الگو هم اولین و هم آخرین کلمه
    بود، جایی که فاصله‌ی اضافی می‌چسبید).
    """

    def test_bare_persian_word_href(self):
        assert find_matching_link_href([_link(href="/تماس")], ["تماس"]) == "/تماس"

    def test_bare_english_word_href(self):
        assert find_matching_link_href([_link(href="/contact")], ["contact"]) == "/contact"

    def test_bare_word_href_with_trailing_slash(self):
        assert find_matching_link_href([_link(href="/about/")], ["about"]) == "/about/"


class TestHrefCompoundMatching:
    """ترکیب‌های رایج و مشروع (یک یا دو کلمه‌ی اضافه‌ی شناخته‌شده) باید مچ شوند."""

    def test_about_us(self):
        assert find_matching_link_href([_link(href="/about-us")], ["about"]) == "/about-us"

    def test_contact_us(self):
        assert find_matching_link_href([_link(href="/contact-us")], ["contact"]) == "/contact-us"

    def test_privacy_policy(self):
        assert find_matching_link_href([_link(href="/privacy-policy")], ["privacy"]) == "/privacy-policy"

    def test_persian_about_ma_compound(self):
        assert find_matching_link_href([_link(href="/درباره-ما")], ["درباره", "درباره-ما"]) == "/درباره-ما"

    def test_persian_contact_ba_ma_compound_via_explicit_pattern(self):
        """
        رگرسیون: «تماس-با-ما» دو کلمه‌ی اضافه («با» و «ما») دارد که
        از سقفِ پیش‌فرض یک‌کلمه‌ای بیشتر است — باید از طریق الگوی
        مرکب صریح «تماس-با-ما» در CONTACT_LINK_PATTERNS مچ شود.
        """
        patterns = ["contact", "تماس", "تماس-با-ما", "تماس_با_ما"]
        assert find_matching_link_href([_link(href="/تماس-با-ما")], patterns) == "/تماس-با-ما"
        assert find_matching_link_href([_link(href="/تماس_با_ما")], patterns) == "/تماس_با_ما"


class TestHrefRejectsUnrelatedSlugs:
    """
    رگرسیون اصلی (نمونه‌های واقعی پیدا شده حین بررسی): اسلاگ‌های
    کاملاً نامرتبط که فقط تصادفاً کلمه‌ی الگو را در خود دارند، نباید
    مچ شوند.
    """

    def test_contact_lens_not_matched_as_contact_page(self):
        result = find_matching_link_href([_link(href="/glossary/contact-lens")], ["contact", "تماس"])
        assert result is None

    def test_about_machine_learning_not_matched_as_about_page(self):
        result = find_matching_link_href([_link(href="/blog/about-machine-learning")], ["about", "درباره"])
        assert result is None

    def test_privacy_preserving_ai_not_matched_as_privacy_page(self):
        result = find_matching_link_href([_link(href="/privacy-preserving-ai")], ["privacy", "حریم", "خصوصی"])
        assert result is None


class TestTextMatching:
    """تشخیص مبتنی بر متن لینک (وقتی href خودش شاهدی نیست، مثل اسلاگ‌های رمزنگاری‌شده)."""

    def test_natural_spacing_contact_text_matches(self):
        """رگرسیون واقعی dr-moghimi.com: «تماس با دکتر» باید مچ شود."""
        result = find_matching_link_href([_link(href="/x", text="تماس با دکتر")], ["contact", "تماس"])
        assert result == "/x"

    def test_persian_suffix_not_confused_with_base_word(self):
        """
        رگرسیون: «تماسی» (پسوند صفت‌ساز فارسی، مثل در «لنز تماسی»)
        یک کلمه‌ی کاملاً متفاوت از «تماس» است و نباید مچ شود.
        """
        result = find_matching_link_href([_link(href="/x", text="لنز تماسی چیست")], ["contact", "تماس"])
        assert result is None

    def test_parent_text_of_sibling_link_does_not_leak(self):
        """
        رگرسیون اصلی (بزرگ‌ترین باگ پیدا شده): چند لینک زیر یک والد
        مشترک (فوتر با «درباره ما | تماس با ما | حریم خصوصی») نباید
        parent_text یکسان و آلوده به متن هم بگیرند.
        """
        from parser.html_parser import parse_html

        html = """
        <html><body><footer>
        <a href="/about">درباره ما</a> |
        <a href="/contact">تماس با ما</a> |
        <a href="/privacy">حریم خصوصی</a>
        </footer></body></html>
        """
        parsed = parse_html(html, "https://example.com/article")
        contact_link = next(l for l in parsed.all_links if l["href"] == "/contact")
        assert "خصوصی" not in contact_link["parent_text"]
        assert "درباره" not in contact_link["parent_text"]


class TestNonFetchableSchemesSkipped:

    def test_tel_link_skipped_in_favor_of_fetchable_match(self):
        links = [
            _link(href="tel:0912", text="تماس"),
            _link(href="/contact", text="ارتباط با ما"),
        ]
        result = find_matching_link_href(links, ["contact", "تماس"],
                                          non_fetchable_schemes=("tel:", "mailto:", "#"))
        assert result == "/contact"

    def test_returns_none_when_only_match_is_non_fetchable(self):
        links = [_link(href="tel:0912", text="تماس")]
        result = find_matching_link_href(links, ["contact", "تماس"],
                                          non_fetchable_schemes=("tel:", "mailto:", "#"))
        assert result is None
