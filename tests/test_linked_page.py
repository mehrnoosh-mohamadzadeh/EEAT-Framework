"""
تست‌های واحد utils/linked_page.py — تمرکز روی رفع باگ صفحات
جاوااسکریپتی (React/Next.js/Vue) که HTML خامشان تقریباً خالی است.
"""

from unittest.mock import patch, MagicMock

from utils.linked_page import fetch_linked_page, fetch_linked_page_text


EMPTY_SPA_HTML = '<html><body><div id="__next"><div class="SplashScreen"></div></div></body></html>'
REAL_CONTENT_HTML = (
    '<html><body><article>ما یک شرکت معتبر با شماره ثبت ۱۲۳۴۵ هستیم. '
    'آدرس: تهران خیابان ولیعصر</article></body></html>'
)
NORMAL_HTML = '<html><body><article>' + ("محتوای معمولی و کافی برای یک صفحه واقعی. " * 10) + '</article></body></html>'


class TestFetchLinkedPageJsFallback:

    def test_falls_back_to_playwright_when_linked_page_is_empty_spa_shell(self):
        """
        رگرسیون (نمونه واقعی rahavard365.com/aboutus — یک اپ Next.js):
        نسخه‌ی قبل فقط fetch_simple را امتحان می‌کرد و هرگز به
        Playwright سقوط نمی‌کرد، پس این‌جور صفحات همیشه خالی دیده
        می‌شدند.
        """
        mock_simple = MagicMock(success=True, html=EMPTY_SPA_HTML)
        mock_rendered = MagicMock(success=True, html=REAL_CONTENT_HTML)

        with patch("fetcher.page_downloader.fetch_simple", return_value=mock_simple), \
             patch("fetcher.page_downloader.fetch_rendered", return_value=mock_rendered) as mock_render_call:
            result = fetch_linked_page("https://example.com/article", "/aboutus")

        assert mock_render_call.called
        assert "شماره ثبت" in result.soup.get_text()

    def test_does_not_call_playwright_for_normal_pages(self):
        """برای صفحه‌ی معمولی با محتوای کافی، نباید اصلاً Playwright صدا زده شود (سرعت حفظ شود)."""
        mock_simple = MagicMock(success=True, html=NORMAL_HTML)

        with patch("fetcher.page_downloader.fetch_simple", return_value=mock_simple), \
             patch("fetcher.page_downloader.fetch_rendered") as mock_render_call:
            result = fetch_linked_page("https://example.com/article", "/about")

        assert not mock_render_call.called
        assert result is not None

    def test_falls_back_to_raw_html_if_playwright_also_fails(self):
        """اگر Playwright هم شکست بخورد، به همان HTML خام (بهتر از هیچی) برمی‌گردد، نه None."""
        mock_simple = MagicMock(success=True, html=EMPTY_SPA_HTML)
        mock_rendered = MagicMock(success=False, html="")

        with patch("fetcher.page_downloader.fetch_simple", return_value=mock_simple), \
             patch("fetcher.page_downloader.fetch_rendered", return_value=mock_rendered):
            result = fetch_linked_page("https://example.com/article", "/aboutus")

        assert result is not None  # نه None — همان HTML خالی خام برگردانده می‌شود

    def test_returns_none_when_simple_fetch_fails_outright(self):
        """اگر حتی دانلود ساده هم شکست بخورد، None برمی‌گردد (رفتار قبلی حفظ شد)."""
        mock_simple = MagicMock(success=False, html="")

        with patch("fetcher.page_downloader.fetch_simple", return_value=mock_simple):
            result = fetch_linked_page("https://example.com/article", "/aboutus")

        assert result is None

    def test_no_href_returns_none_immediately(self):
        assert fetch_linked_page("https://example.com/article", None) is None
        assert fetch_linked_page_text("https://example.com/article", "") is None
