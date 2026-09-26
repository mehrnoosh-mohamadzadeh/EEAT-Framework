# -*- coding: utf-8 -*-
"""
تست‌های واحد fetcher/page_downloader.py — تمرکز روی رفع باگ استراتژی
wait در fetch_rendered (Playwright).

رگرسیون: نسخه‌ی قبل فقط از page.goto(..., wait_until="networkidle")
استفاده می‌کرد. خیلی از صفحات واقعی (آنالیتیکس، polling، وب‌سوکت) هرگز
واقعاً idle نمی‌شوند، پس goto() تا انتهای کل timeout صبر می‌کرد و کل
fetch شکست می‌خورد. حالا باید: goto با "domcontentloaded"، سپس یک تلاش
جداگانه و محدود برای networkidle، سپس یک صبر کوتاه و جداگانه برای
رسیدن متن body به آستانه‌ی کافی — و هیچ‌کدام از این دو تلاش نباید با
شکست‌شان کل fetch_rendered را متوقف کنند.
"""

from unittest.mock import patch, MagicMock

from fetcher import page_downloader


def _install_fake_playwright(monkeypatch_target="playwright.sync_api.sync_playwright"):
    """
    یک sync_playwright جعلی می‌سازد که یک browser/page mock برمی‌گرداند،
    تا بتوان دقیقاً بررسی کرد fetch_rendered با چه آرگومان‌هایی page را
    صدا می‌زند، بدون باز کردن مرورگر واقعی.
    """
    fake_page = MagicMock()
    fake_page.content.return_value = "<html><body>rendered content</body></html>"

    fake_browser = MagicMock()
    fake_browser.new_page.return_value = fake_page

    fake_pw_context = MagicMock()
    fake_pw_context.chromium.launch.return_value = fake_browser

    fake_sync_playwright_cm = MagicMock()
    fake_sync_playwright_cm.__enter__.return_value = fake_pw_context
    fake_sync_playwright_cm.__exit__.return_value = False

    fake_sync_playwright = MagicMock(return_value=fake_sync_playwright_cm)
    return fake_sync_playwright, fake_page, fake_browser


class TestFetchRenderedWaitStrategy:

    def test_goto_uses_domcontentloaded_not_networkidle(self):
        """
        goto نباید مستقیماً wait_until="networkidle" بگیرد — این دقیقاً
        همان چیزی بود که باعث timeout کامل روی صفحات با فعالیت شبکه‌ی
        دائمی می‌شد.
        """
        fake_sync_playwright, fake_page, fake_browser = _install_fake_playwright()
        with patch("playwright.sync_api.sync_playwright", fake_sync_playwright):
            page_downloader.fetch_rendered("https://example.com", timeout=10)

        goto_call = fake_page.goto.call_args
        assert goto_call.kwargs.get("wait_until") == "domcontentloaded"

    def test_attempts_networkidle_separately_after_domcontentloaded(self):
        fake_sync_playwright, fake_page, fake_browser = _install_fake_playwright()
        with patch("playwright.sync_api.sync_playwright", fake_sync_playwright):
            page_downloader.fetch_rendered("https://example.com", timeout=10)

        assert fake_page.wait_for_load_state.called
        args, kwargs = fake_page.wait_for_load_state.call_args
        assert "networkidle" in args or kwargs.get("state") == "networkidle" \
            or (args and args[0] == "networkidle")

    def test_networkidle_timeout_does_not_fail_fetch(self):
        """
        اگر صفحه هیچ‌وقت networkidle نشود (PlaywrightTimeoutError)، باید
        fetch_rendered همچنان موفق باشد و همان DOM فعلی را برگرداند —
        نه اینکه با خطا کامل شکست بخورد.
        """
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

        fake_sync_playwright, fake_page, fake_browser = _install_fake_playwright()
        fake_page.wait_for_load_state.side_effect = PlaywrightTimeoutError("never idle")

        with patch("playwright.sync_api.sync_playwright", fake_sync_playwright):
            result = page_downloader.fetch_rendered("https://example.com", timeout=10)

        assert result.success
        assert result.error is None
        assert "rendered content" in result.html

    def test_content_stability_wait_timeout_does_not_fail_fetch(self):
        """
        اگر متن body هیچ‌وقت به آستانه‌ی «کافی» نرسد (مثلاً یک صفحه‌ی
        واقعاً کم‌محتوا)، fetch_rendered نباید شکست بخورد — تصمیم درباره‌ی
        کافی‌بودن محتوا به عهده‌ی مراحل بعدی (Parser/Extractors) است.
        """
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

        fake_sync_playwright, fake_page, fake_browser = _install_fake_playwright()
        fake_page.wait_for_function.side_effect = PlaywrightTimeoutError("never enough text")

        with patch("playwright.sync_api.sync_playwright", fake_sync_playwright):
            result = page_downloader.fetch_rendered("https://example.com", timeout=10)

        assert result.success
        assert result.error is None

    def test_browser_closed_even_if_content_wait_raises_unexpectedly(self):
        """رفع باگ قبلی (زامبی‌های کروم) نباید با این تغییرات دوباره برگردد."""
        fake_sync_playwright, fake_page, fake_browser = _install_fake_playwright()
        fake_page.goto.side_effect = RuntimeError("boom")

        with patch("playwright.sync_api.sync_playwright", fake_sync_playwright):
            result = page_downloader.fetch_rendered("https://example.com", timeout=10)

        assert fake_browser.close.called
        assert not result.success
        assert "playwright_error" in result.error
