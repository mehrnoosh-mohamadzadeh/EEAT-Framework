"""
تست‌های واحد parser/html_parser.py — قبلاً هیچ تستی نداشت.
"""

from parser.html_parser import extract_main_content, parse_html
from bs4 import BeautifulSoup


class TestExtractMainContent:

    def test_picks_article_with_most_text_not_first(self):
        """
        رگرسیون: وقتی چند تگ <article> هست (رایج در صفحات آرشیو/لیست)،
        باید تگی که بیشترین متن را دارد انتخاب شود، نه لزوماً اولی.
        """
        html = (
            "<html><body>"
            "<article>خلاصه کوتاه ۱</article>"
            "<article>خلاصه کوتاه ۲</article>"
            "<article>" + ("این محتوای کامل مقاله است. " * 50) + "</article>"
            "</body></html>"
        )
        soup = BeautifulSoup(html, "lxml")
        main = extract_main_content(soup)
        assert len(main.get_text(strip=True)) > 200

    def test_single_article_tag_still_works(self):
        html = "<html><body><article><p>محتوای تک مقاله</p></article></body></html>"
        soup = BeautifulSoup(html, "lxml")
        main = extract_main_content(soup)
        assert "محتوای تک مقاله" in main.get_text(strip=True)

    def test_picks_highest_density_div_when_no_article_tag(self):
        """بدون تگ <article>، div با تراکم متن بالاتر (نه صرفاً بزرگ‌ترین) باید انتخاب شود."""
        html = (
            "<html><body>"
            '<div class="sidebar"><p>کوتاه</p></div>'
            '<div class="main"><p>' + ("این متن اصلی مقاله واقعی است. " * 30) + "</p></div>"
            "</body></html>"
        )
        soup = BeautifulSoup(html, "lxml")
        main = extract_main_content(soup)
        assert main.get("class") == ["main"]

    def test_excludes_divs_inside_non_content_tags(self):
        """div هایی که داخل header/footer/nav/aside/form هستند نباید انتخاب شوند، حتی اگر متن زیادی داشته باشند."""
        html = (
            "<html><body>"
            "<footer><div>" + ("متن زیاد داخل فوتر که نباید انتخاب شود. " * 30) + "</div></footer>"
            '<div class="real-content"><p>' + ("محتوای واقعی مقاله. " * 30) + "</p></div>"
            "</body></html>"
        )
        soup = BeautifulSoup(html, "lxml")
        main = extract_main_content(soup)
        assert main.get("class") == ["real-content"]

    def test_falls_back_to_whole_soup_when_no_good_candidate(self):
        html = "<html><body><p>خیلی کوتاه</p></body></html>"
        soup = BeautifulSoup(html, "lxml")
        main = extract_main_content(soup)
        assert main is soup

    def test_parse_html_end_to_end_still_works(self):
        """اطمینان از این‌که parse_html کامل (نه فقط extract_main_content) بعد از این تغییر هنوز درست کار می‌کند."""
        html = "<html><body><article><p>یک مقاله ساده با <a href='https://a.ir'>لینک</a></p></article></body></html>"
        parsed = parse_html(html, "https://test.ir/page")
        assert "یک مقاله ساده" in parsed.main_content_text
        assert len(parsed.all_links) == 1
