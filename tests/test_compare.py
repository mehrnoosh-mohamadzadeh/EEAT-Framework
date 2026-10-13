# -*- coding: utf-8 -*-
"""
تست‌های قابلیت «مقایسه‌ی دو صفحه»:
منطق برنده (تابع خالص)، ساخت ساختار مقایسه، مسیرهای وب (موفق/خطا/توکن
نامعتبر)، ساخت PDF مقایسه و شکست بی‌سروصدای PDF. هیچ‌کدام به شبکه نیاز
ندارند: process_single_url با نتیجه‌ی ساختگی جایگزین می‌شود.
"""

import os

import pytest

import webapp.app as appmod
from reporting.pdf_report import generate_comparison_pdf, comparison_tip_sides
from webapp.comparison import (
    decide_winner, build_comparison_context, normalize_url_for_compare,
    STATISTICAL_DISCLAIMER,
)
from webapp.recommendations import COMPONENT_INDICATOR_CODES

ALL_CODES = [c for codes in COMPONENT_INDICATOR_CODES.values() for c in codes]


class _FakeScore:
    def __init__(self, url, values, final=0.5):
        """values: {code: عدد ۰..۱ | None (missing) | "NA" (not_applicable)}"""
        self.url = url
        self.final_score = final
        details = {}
        for code in ALL_CODES:
            v = values.get(code, 0.5)
            if v == "NA":
                details[code] = {"value": None, "missing": False, "applicable": False,
                                 "raw_details": {}}
            elif v is None:
                details[code] = {"value": None, "missing": True, "applicable": True,
                                 "raw_details": {}}
            else:
                details[code] = {"value": v, "missing": False, "applicable": True,
                                 "raw_details": {"word_count": 100}}
        self.indicator_details = details
        self.component_scores = {k: 0.5 for k in COMPONENT_INDICATOR_CODES}


def _ctx(url, values, final=0.5):
    return appmod.build_report_context(_FakeScore(url, values, final))


@pytest.fixture
def client():
    appmod.app.config["TESTING"] = True
    return appmod.app.test_client()


@pytest.fixture
def fake_pipeline(monkeypatch):
    """process_single_url ساختگی؛ آدرس‌ها را به ترتیب فراخوانی ثبت می‌کند."""
    calls = []
    scores = {
        "https://a.example.com": _FakeScore("https://a.example.com", {"E1": 0.9, "E2": 0.2}, 0.7),
        "https://b.example.com": _FakeScore("https://b.example.com", {"E1": 0.3, "E2": 0.2}, 0.4),
    }

    def _fake(url, weights, **kw):
        calls.append(url)
        if url in scores:
            return scores[url]
        raise appmod.FetchFailedError(url, "ساختگی: ۴۰۳")

    monkeypatch.setattr(appmod, "process_single_url", _fake)
    return calls


class TestDecideWinner:

    def test_first_wins(self):
        assert decide_winner(80, 50) == {"result": "a", "diff": 30}

    def test_second_wins(self):
        assert decide_winner(20, 55) == {"result": "b", "diff": -35}

    def test_tie_has_no_winner(self):
        assert decide_winner(60, 60) == {"result": "tie", "diff": 0}

    @pytest.mark.parametrize("sa,sb", [("missing", "pass"), ("pass", "missing"),
                                       ("not_applicable", "pass"), ("pass", "not_applicable"),
                                       ("missing", "missing")])
    def test_missing_or_not_applicable_never_claims_winner(self, sa, sb):
        r = decide_winner(90, 10, sa, sb)
        assert r == {"result": "none", "diff": None}

    def test_none_percent_never_claims_winner(self):
        assert decide_winner(None, 40)["result"] == "none"
        assert decide_winner(40, None)["result"] == "none"

    def test_zero_is_a_real_value_not_missing(self):
        assert decide_winner(0, 30, "fail", "warn")["result"] == "b"


class TestUrlNormalization:

    def test_case_trailing_slash_and_fragment_ignored(self):
        assert (normalize_url_for_compare("HTTPS://Example.com/Page/#top")
                == normalize_url_for_compare("https://example.com/Page"))

    def test_different_paths_differ(self):
        assert (normalize_url_for_compare("https://example.com/a")
                != normalize_url_for_compare("https://example.com/b"))


class TestBuildComparisonContext:

    def test_tally_covers_all_19_indicators(self):
        cmp_ctx = build_comparison_context(_ctx("https://a", {"E1": 0.9}), _ctx("https://b", {"E1": 0.1}))
        assert sum(cmp_ctx["tally"].values()) == 19
        assert cmp_ctx["disclaimer"] == STATISTICAL_DISCLAIMER

    def test_indicator_results(self):
        a = _ctx("https://a", {"E1": 0.9, "E2": 0.5, "E3": None, "E4": "NA"})
        b = _ctx("https://b", {"E1": 0.1, "E2": 0.5, "E3": 0.8, "E4": 0.8})
        cmp_ctx = build_comparison_context(a, b)
        inds = {i["code"]: i for c in cmp_ctx["components"] for i in c["indicators"]}
        assert inds["E1"]["result"] == "a"
        assert inds["E2"]["result"] == "tie"
        assert inds["E3"]["result"] == "none"
        assert inds["E4"]["result"] == "none"

    def test_matches_indicators_by_code_not_position(self):
        a = _ctx("https://a", {"E1": 0.9})
        b = _ctx("https://b", {"E1": 0.1})
        b["components"][0]["indicators"].reverse()
        cmp_ctx = build_comparison_context(a, b)
        e1 = cmp_ctx["components"][0]["indicators"][0]
        assert e1["code"] == "E1" and e1["result"] == "a"

    def test_final_score_comparison(self):
        cmp_ctx = build_comparison_context(_ctx("https://a", {}, 0.7), _ctx("https://b", {}, 0.4))
        assert cmp_ctx["final"]["result"] == "a"
        assert cmp_ctx["final"]["diff"] == 30


class TestComparisonTipSides:

    def _ind(self, result, sa, sb):
        return {"result": result, "a": {"status": sa}, "b": {"status": sb}}

    def test_only_weaker_side_gets_tip(self):
        assert comparison_tip_sides(self._ind("a", "pass", "fail")) == ["b"]
        assert comparison_tip_sides(self._ind("b", "warn", "pass")) == ["a"]

    def test_tie_tips_only_for_weak_sides(self):
        assert comparison_tip_sides(self._ind("tie", "fail", "fail")) == ["a", "b"]
        assert comparison_tip_sides(self._ind("tie", "pass", "pass")) == []

    def test_none_result_skips_missing_side(self):
        assert comparison_tip_sides(self._ind("none", "missing", "fail")) == ["b"]
        assert comparison_tip_sides(self._ind("none", "not_applicable", "pass")) == []


class TestIndexModes:

    def test_default_is_single_mode_with_hidden_second_field(self, client):
        html = client.get("/").get_data(as_text=True)
        assert 'action="/analyze"' in html
        assert 'id="mode-single" value="single" checked' in html
        assert "hidden disabled" in html  # فیلد دوم در حالت پیش‌فرض نه نشان داده می‌شود نه ارسال

    def test_single_analyze_still_works(self, client, fake_pipeline):
        resp = client.post("/analyze", data={"url": "a.example.com"})
        assert resp.status_code == 200
        assert fake_pipeline == ["https://a.example.com"]
        assert "برنده" not in resp.get_data(as_text=True)


class TestCompareRoute:

    def test_success_shows_both_pages_winner_and_disclaimer(self, client, fake_pipeline):
        resp = client.post("/compare", data={"url": "a.example.com", "url2": "b.example.com"})
        html = resp.get_data(as_text=True)
        assert resp.status_code == 200
        assert "a.example.com" in html and "b.example.com" in html
        assert "برنده" in html
        assert "معنی آماری ندارد" in html
        assert "/download-compare-pdf/" in html

    def test_pages_fetched_sequentially_in_order(self, client, fake_pipeline):
        client.post("/compare", data={"url": "a.example.com", "url2": "b.example.com"})
        assert fake_pipeline == ["https://a.example.com", "https://b.example.com"]

    def test_first_url_failure_names_the_first_url(self, client, fake_pipeline):
        resp = client.post("/compare", data={"url": "bad.example.com", "url2": "b.example.com"})
        html = resp.get_data(as_text=True)
        assert resp.status_code == 200
        assert "صفحه‌ی اول" in html and "https://bad.example.com" in html
        assert fake_pipeline == ["https://bad.example.com"]  # صفحه‌ی دوم اصلاً گرفته نمی‌شود
        assert 'value="bad.example.com"' in html  # ورودی کاربر حفظ می‌شود

    def test_second_url_failure_names_the_second_url(self, client, fake_pipeline):
        resp = client.post("/compare", data={"url": "a.example.com", "url2": "bad.example.com"})
        html = resp.get_data(as_text=True)
        assert "صفحه‌ی دوم" in html and "https://bad.example.com" in html

    def test_unexpected_error_in_pipeline_gives_clear_message(self, client, monkeypatch):
        def _boom(url, weights, **kw):
            raise ValueError("خطای ساختگی")
        monkeypatch.setattr(appmod, "process_single_url", _boom)
        resp = client.post("/compare", data={"url": "a.example.com", "url2": "b.example.com"})
        assert resp.status_code == 200
        assert "خطای ساختگی" in resp.get_data(as_text=True)

    def test_identical_urls_warn_and_do_not_fetch(self, client, fake_pipeline):
        resp = client.post("/compare", data={"url": "a.example.com", "url2": "HTTPS://A.example.com/"})
        assert "یکسان" in resp.get_data(as_text=True)
        assert fake_pipeline == []

    def test_missing_second_url_is_rejected(self, client, fake_pipeline):
        resp = client.post("/compare", data={"url": "a.example.com", "url2": ""})
        assert "هر دو آدرس" in resp.get_data(as_text=True)
        assert fake_pipeline == []

    def test_error_page_stays_in_compare_mode(self, client, fake_pipeline):
        html = client.post("/compare", data={"url": "a.example.com", "url2": ""}).get_data(as_text=True)
        assert 'id="mode-compare" value="compare" checked' in html
        assert 'action="/compare"' in html


class TestComparePdf:

    def test_pdf_download_works_after_compare(self, client, fake_pipeline):
        html = client.post("/compare", data={"url": "a.example.com", "url2": "b.example.com"}).get_data(as_text=True)
        token = html.split("/download-compare-pdf/")[1].split('"')[0]
        resp = client.get(f"/download-compare-pdf/{token}")
        assert resp.status_code == 200
        assert resp.content_type == "application/pdf"
        assert resp.data[:4] == b"%PDF"
        assert "attachment" in resp.headers.get("Content-Disposition", "")

    def test_invalid_token_returns_404(self, client):
        assert client.get("/download-compare-pdf/no-such-token").status_code == 404

    def test_generate_comparison_pdf_produces_real_multipage_pdf(self, tmp_path):
        a = _ctx("https://a.example.com", {c: 0.8 for c in ALL_CODES}, 0.8)
        b = _ctx("https://b.example.com", {c: 0.3 for c in ALL_CODES}, 0.3)
        out = str(tmp_path / "cmp.pdf")
        assert generate_comparison_pdf(build_comparison_context(a, b), out) == out
        data = open(out, "rb").read()
        assert data[:4] == b"%PDF"
        assert data.count(b"/Type /Page\n") + data.count(b"/Type /Page ") >= 2

    def test_pdf_handles_every_status_mix(self, tmp_path):
        values_a = {"E1": 0.9, "E2": None, "E3": "NA", "E4": 0.0, "X1": 0.5}
        values_b = {"E1": 0.9, "E2": 0.5, "E3": 0.5, "E4": None, "X1": "NA"}
        out = str(tmp_path / "mix.pdf")
        generate_comparison_pdf(
            build_comparison_context(_ctx("https://a", values_a), _ctx("https://b", values_b)), out)
        assert os.path.getsize(out) > 1000

    def test_pdf_failure_does_not_break_compare_page(self, client, fake_pipeline, monkeypatch):
        def _broken(*a, **kw):
            raise RuntimeError("شبیه‌سازی خطا")
        monkeypatch.setattr(appmod, "generate_comparison_pdf", _broken)
        resp = client.post("/compare", data={"url": "a.example.com", "url2": "b.example.com"})
        html = resp.get_data(as_text=True)
        assert resp.status_code == 200
        assert "برنده" in html
        assert "/download-compare-pdf/" not in html

    def test_failed_pdf_leaves_no_temp_file_behind(self, monkeypatch, tmp_path):
        import tempfile
        monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))

        def _broken(*a, **kw):
            raise RuntimeError("x")
        monkeypatch.setattr(appmod, "generate_comparison_pdf", _broken)
        cmp_ctx = build_comparison_context(_ctx("https://a", {}), _ctx("https://b", {}))
        assert appmod._generate_and_cache_comparison_pdf(cmp_ctx) is None
        assert list(tmp_path.iterdir()) == []

    def test_compare_pdfs_share_the_same_bounded_cache(self, tmp_path, monkeypatch):
        import collections
        monkeypatch.setattr(appmod, "_pdf_cache", collections.OrderedDict())
        monkeypatch.setattr(appmod, "PDF_CACHE_MAX_SIZE", 2)
        cmp_ctx = build_comparison_context(_ctx("https://a.example.com", {}), _ctx("https://b.example.com", {}))
        tokens = [appmod._generate_and_cache_comparison_pdf(cmp_ctx) for _ in range(4)]
        assert all(tokens)
        assert len(appmod._pdf_cache) == 2
