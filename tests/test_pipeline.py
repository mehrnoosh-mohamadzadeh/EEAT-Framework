"""
تست‌های واحد pipeline.py — تمرکز روی process_single_url_safe که باید
هیچ‌وقت اجرای دسته‌ای main.py را با یک URL خراب کامل متوقف نکند، و
process_single_url که باید تشخیص خودکار صفحات جاوااسکریپتی (Next.js و
مشابه) را به‌طور پیش‌فرض روشن نگه دارد.
"""

from unittest.mock import patch, MagicMock

import pipeline
from pipeline import process_single_url, process_single_url_safe, FetchFailedError


class TestProcessSingleUrlSafe:

    def test_returns_none_on_fetch_failure(self):
        with patch("pipeline.process_single_url",
                   side_effect=FetchFailedError("https://example.com", "boom")):
            result = process_single_url_safe("https://example.com", {})
        assert result is None

    def test_returns_none_on_unexpected_exception_instead_of_crashing(self):
        """
        رگرسیون: یک خطای کاملاً غیرمنتظره (نه FetchFailedError) — مثلاً
        باگ در یکی از extractorها روی HTML عجیب یک سایت واقعی — نباید
        از process_single_url_safe بیرون درز کند؛ باید None برگرداند
        تا main.py بتواند به URL بعدی برود.
        """
        with patch("pipeline.process_single_url", side_effect=ValueError("unexpected bug")):
            result = process_single_url_safe("https://example.com", {})
        assert result is None

    def test_still_returns_real_result_on_success(self):
        with patch("pipeline.process_single_url", return_value="fake_page_score"):
            result = process_single_url_safe("https://example.com", {})
        assert result == "fake_page_score"


class TestProcessSingleUrlAutoDetectDefault:
    """
    رگرسیون (گزارش کاربر روی نمونه‌ی صفحه‌ی ره‌آورد — یک اپ Next.js):
    word_count=1، avg_sentence_length=1.0 و structure_score=0.0 چون
    process_single_url قبلاً auto_detect_js=False را صریحاً به fetch()
    پاس می‌داد، درحالی‌که خودِ fetch() (در fetcher/page_downloader.py)
    پیش‌فرض auto_detect=True دارد و از قبل برای تشخیص و رندر صفحات
    جاوااسکریپتی طراحی و تست شده بود. یعنی نه main.py (که این آرگومان
    را اصلاً پاس نمی‌دهد) و نه webapp/app.py (که هم همین‌طور) هرگز از
    این قابلیت موجود بهره نمی‌بردند.
    """

    def test_auto_detect_js_is_true_by_default(self):
        fake_result = MagicMock(success=True, html="<html><body>x</body></html>", error=None)
        with patch("pipeline.fetch", return_value=fake_result) as mock_fetch:
            try:
                process_single_url("https://example.com", {
                    "Experience": 1, "Expertise": 1,
                    "Authoritativeness": 1, "Trustworthiness": 1,
                })
            except Exception:
                # فقط فراخوانی fetch() برایمان مهم است؛ رفتار extractorها
                # روی HTML بی‌محتوا در تست‌های خودشان پوشش داده شده
                pass

        mock_fetch.assert_called_once()
        _, kwargs = mock_fetch.call_args
        assert kwargs.get("auto_detect") is True

    def test_auto_detect_js_can_still_be_disabled_explicitly(self):
        """امکان خاموش‌کردن صریح (مثلاً برای دیباگ سریع) باید باقی بماند."""
        fake_result = MagicMock(success=True, html="<html><body>x</body></html>", error=None)
        with patch("pipeline.fetch", return_value=fake_result) as mock_fetch:
            try:
                process_single_url("https://example.com", {
                    "Experience": 1, "Expertise": 1,
                    "Authoritativeness": 1, "Trustworthiness": 1,
                }, auto_detect_js=False)
            except Exception:
                pass

        _, kwargs = mock_fetch.call_args
        assert kwargs.get("auto_detect") is False
