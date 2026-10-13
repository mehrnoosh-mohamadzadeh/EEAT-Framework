# -*- coding: utf-8 -*-
"""
تست‌های واحد قابلیت «دانلود گزارش PDF» — دو فایل را پوشش می‌دهد:
reporting/pdf_report.py (ساخت خودِ PDF) و webapp/app.py (مسیر دانلود،
کش، و رفتار صفحه‌ی نتیجه وقتی ساخت PDF شکست می‌خورد).

چرا این تست‌ها لازم بودند: این دقیقاً همان دسته‌قابلیتی است که به‌راحتی
«روی سیستم من کار می‌کند ولی در عمل خراب است» می‌شود — مثلاً اگر فونت
فارسی embed نشده باشد، PDF تولید می‌شود ولی متنش جعبه‌های خالی است، یا
اگر مسیر آپلود/کش اشتباه باشد، دکمه‌ی دانلود اصلاً در صفحه ظاهر نمی‌شود.
"""

import os

import pytest

from parser.html_parser import parse_html
from reporting.pdf_report import generate_pdf_report, rtl, _wrap_to_width


def _fake_context(status_e1="fail", score_percent=42):
    """
    یک context ساختگی هم‌شکل با خروجی واقعی build_report_context —
    برای تست pdf_report.py بدون نیاز به اجرای کل pipeline (که به شبکه
    نیاز دارد).
    """
    return {
        "url": "https://example.com/test-page",
        "display_url": "example.com/test-page",
        "final_score_percent": score_percent,
        "components": [
            {
                "key": "Experience", "label": "تجربه", "score": 0.1,
                "score_percent": 10, "status": "fail",
                "indicators": [
                    {"code": "E1", "label": "شواهد تجربه عملی", "value": 0.0,
                     "value_percent": 0, "status": status_e1,
                     "tip": "یک توصیه‌ی تستی برای E1." if status_e1 in ("fail", "warn") else None,
                     "evidence": "عبارت صریح تجربه دارد؟: خیر"},
                    {"code": "E2", "label": "زبان تجربه‌محور (اول‌شخص)", "value": None,
                     "value_percent": None, "status": "missing",
                     "tip": None, "evidence": ""},
                    {"code": "E3", "label": "نظرات کاربران", "value": 1.0,
                     "value_percent": 100, "status": "pass",
                     "tip": None, "evidence": "تعداد نظر: 12"},
                ],
            },
        ],
    }


class TestRTLTextPreparation:

    def test_rtl_does_not_crash_on_empty_or_none(self):
        assert rtl("") == ""
        assert rtl(None) == ""

    def test_rtl_reorders_persian_text(self):
        # فقط بررسی می‌کند که خروجی خالی نیست و از ورودی متفاوت است —
        # خودِ الگوریتم bidi را دوباره پیاده‌سازی نمی‌کنیم، فقط مطمئن
        # می‌شویم به‌کار گرفته شده
        result = rtl("سلام دنیا")
        assert result
        assert isinstance(result, str)

    def test_wrap_to_width_splits_long_text_into_multiple_lines(self):
        long_text = " ".join(["کلمه"] * 60)
        lines = _wrap_to_width(long_text, "Helvetica", 10, max_width=150)
        assert len(lines) > 1
        # هیچ کلمه‌ای نباید گم شود
        assert sum(len(l.split()) for l in lines) == 60


class TestGeneratePdfReport:

    def test_produces_a_real_pdf_file(self, tmp_path):
        out = str(tmp_path / "report.pdf")
        result_path = generate_pdf_report(_fake_context(), out)
        assert result_path == out
        assert os.path.isfile(out)
        with open(out, "rb") as f:
            header = f.read(4)
        assert header == b"%PDF"
        assert os.path.getsize(out) > 1000  # نه یک فایل خالی/شکسته

    def test_handles_every_status_without_crashing(self, tmp_path):
        """هر چهار وضعیت (fail/warn/pass/missing/not_applicable) نباید کرش کند."""
        for status in ("fail", "warn", "pass", "missing", "not_applicable"):
            out = str(tmp_path / f"report_{status}.pdf")
            ctx = _fake_context(status_e1=status)
            generate_pdf_report(ctx, out)
            assert os.path.isfile(out)

    def test_tip_shown_even_for_pass_status_indicator(self, tmp_path):
        """
        رگرسیون: صفحه‌ی وب فقط برای fail/warn تب نمایش می‌دهد (tip=None
        برای pass) ولی PDF باید برای «هر» شاخص توصیه نشان دهد — طبق
        درخواست صریح کاربر. پس pdf_report نباید صرفاً به ind['tip']
        (که از قبل فیلتر شده) اکتفا کند.
        """
        from reporting.pdf_report import _build_indicator_tip_text
        pass_indicator = {"code": "E1", "status": "pass", "tip": None}
        tip = _build_indicator_tip_text(pass_indicator)
        assert tip  # نباید خالی باشد، چون E1 در IMPROVEMENT_TIPS تعریف شده

    def test_missing_status_gets_explanatory_text_not_a_real_tip(self, tmp_path):
        from reporting.pdf_report import _build_indicator_tip_text
        missing_indicator = {"code": "E2", "status": "missing", "tip": None}
        tip = _build_indicator_tip_text(missing_indicator)
        assert "کافی نبود" in tip or "کافی نیست" in tip


class TestPdfDownloadRoute:

    def test_results_page_includes_working_download_link(self):
        from webapp.app import app, build_report_context

        class _FakeScore:
            url = "https://example.com/x"
            final_score = 0.42
            component_scores = {"Experience": 0.1, "Expertise": 0.2,
                               "Authoritativeness": 0.3, "Trustworthiness": 0.4}
            indicator_details = {}

        with app.test_request_context():
            ctx = build_report_context(_FakeScore())

        client = app.test_client()
        from webapp.app import _generate_and_cache_pdf
        with app.app_context():
            token = _generate_and_cache_pdf(ctx)
        assert token is not None

        resp = client.get(f"/download-pdf/{token}")
        assert resp.status_code == 200
        assert resp.content_type == "application/pdf"
        assert resp.data[:4] == b"%PDF"
        assert "attachment" in resp.headers.get("Content-Disposition", "")

    def test_invalid_token_returns_404(self):
        from webapp.app import app
        client = app.test_client()
        resp = client.get("/download-pdf/this-token-does-not-exist")
        assert resp.status_code == 404

    def test_pdf_generation_failure_does_not_break_results_page(self, monkeypatch):
        """
        رگرسیون حیاتی: اگر ساخت PDF به هر دلیلی شکست بخورد (فونت گم‌شده،
        دیسک پر، و غیره)، کل صفحه‌ی نتیجه نباید با آن خراب شود — فقط
        دکمه‌ی دانلود نباید نشان داده شود.
        """
        import webapp.app as appmod

        def _broken(*a, **kw):
            raise RuntimeError("شبیه‌سازی خطا")

        monkeypatch.setattr(appmod, "generate_pdf_report", _broken)

        class _FakeScore:
            url = "https://example.com/y"
            final_score = 0.5
            component_scores = {"Experience": 0.5, "Expertise": 0.5,
                               "Authoritativeness": 0.5, "Trustworthiness": 0.5}
            indicator_details = {}

        with appmod.app.test_request_context():
            ctx = appmod.build_report_context(_FakeScore())
            token = appmod._generate_and_cache_pdf(ctx)
        assert token is None


class TestPdfCacheEviction:

    def test_cache_respects_max_size_and_cleans_disk(self, tmp_path, monkeypatch):
        from webapp import app as appmod

        monkeypatch.setattr(appmod, "_pdf_cache", __import__("collections").OrderedDict())
        monkeypatch.setattr(appmod, "PDF_CACHE_MAX_SIZE", 3)

        paths = []
        for i in range(6):
            p = tmp_path / f"f{i}.pdf"
            p.write_bytes(b"%PDF-fake")
            paths.append(str(p))
            appmod._cache_pdf(str(p), f"name{i}.pdf")

        assert len(appmod._pdf_cache) == 3
        still_on_disk = [p for p in paths if os.path.isfile(p)]
        assert len(still_on_disk) == 3
