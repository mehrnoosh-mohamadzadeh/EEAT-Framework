# -*- coding: utf-8 -*-
"""
تست‌های رابط کاربری (قالب‌ها و استایل‌های بازطراحی‌شده): این تست‌ها منطق
امتیازدهی را نمی‌سنجند؛ فقط مطمئن می‌شوند نمایش، داده‌ی واقعی را درست و
بی‌ابهام نشان می‌دهد — به‌ویژه تفکیک «امتیاز صفر»، «داده ناموجود» و
«غیرقابل اعمال»، و هم‌خوانی آستانه‌های رسم‌شده با get_status_level.
"""

import pytest

import webapp.app as appmod
from webapp.recommendations import (
    COMPONENT_INDICATOR_CODES, get_status_level,
)

ALL_CODES = [c for codes in COMPONENT_INDICATOR_CODES.values() for c in codes]


class _FakeScore:
    def __init__(self, url, values, final=0.5):
        self.url = url
        self.final_score = final
        details = {}
        for code in ALL_CODES:
            v = values.get(code, 0.7)
            if v == "NA":
                details[code] = {"value": None, "missing": False, "applicable": False, "raw_details": {}}
            elif v is None:
                details[code] = {"value": None, "missing": True, "applicable": True, "raw_details": {}}
            else:
                details[code] = {"value": v, "missing": False, "applicable": True,
                                 "raw_details": {"word_count": 100}}
        self.indicator_details = details
        self.component_scores = {k: 0.5 for k in COMPONENT_INDICATOR_CODES}


@pytest.fixture
def client():
    appmod.app.config["TESTING"] = True
    return appmod.app.test_client()


def _analyze(client, monkeypatch, values, final=0.5):
    monkeypatch.setattr(appmod, "process_single_url",
                        lambda url, weights, **kw: _FakeScore(url, values, final))
    return client.post("/analyze", data={"url": "example.com"}).get_data(as_text=True)


class TestThresholdsMatchStatusLogic:

    def test_drawn_thresholds_equal_get_status_level_boundaries(self):
        t = appmod.inject_ui_constants()["thresholds"]
        for percent in range(0, 101):
            expected = ("fail" if percent < t["fail"]
                        else "warn" if percent < t["pass"] else "pass")
            assert get_status_level(percent / 100.0, False, True) == expected, percent


class TestStatusesAreNeverConfused:

    def test_zero_missing_and_not_applicable_look_and_read_differently(self, client, monkeypatch):
        html = _analyze(client, monkeypatch,
                        {"E1": 0.0, "E2": None, "E3": "NA", "E4": 1.0})
        assert "امتیاز صفر" in html
        assert "داده ناموجود" in html
        assert "غیرقابل اعمال" in html
        # هر سه وضعیت نشانه‌ی شکلیِ متفاوت دارند
        for cls in ("mark-fail", "mark-missing", "mark-not_applicable", "mark-pass"):
            assert cls in html, cls
        # نوار هر وضعیت هم متفاوت است
        assert "track is-fail" in html
        assert "track is-missing" in html
        assert "track is-not_applicable" in html

    def test_zero_score_row_is_not_rendered_as_missing(self, client, monkeypatch):
        html = _analyze(client, monkeypatch, {"E1": 0.0})
        e1 = html.split('class="code" dir="ltr">E1<')[1].split("</li>")[0]
        assert "امتیاز صفر" in e1
        assert "داده ناموجود" not in e1
        assert "0٪" in e1

    def test_status_counts_add_up_to_19(self, client, monkeypatch):
        html = _analyze(client, monkeypatch, {"E1": 0.0, "E2": None, "E3": "NA", "E4": 1.0})
        assert "از 19 شاخص" in html


class TestResultsPage:

    def test_final_score_is_shown_in_gauge_and_label(self, client, monkeypatch):
        html = _analyze(client, monkeypatch, {}, final=0.37)
        assert 'aria-label="امتیاز نهایی 37 از 100"' in html
        assert ">37</text>" in html

    def test_single_page_report_never_declares_a_winner(self, client, monkeypatch):
        html = _analyze(client, monkeypatch, {})
        assert "برنده" not in html

    def test_all_four_components_have_sections(self, client, monkeypatch):
        html = _analyze(client, monkeypatch, {})
        for key in COMPONENT_INDICATOR_CODES:
            assert f'id="comp-{key}"' in html

    def test_sections_follow_the_logical_order(self, client, monkeypatch):
        """عنوان و صفحه ← امتیاز نهایی ← چهار مؤلفه ← جزئیات شاخص‌ها ← معنی وضعیت‌ها ← بررسی صفحه‌ی دیگر."""
        html = _analyze(client, monkeypatch, {})
        markers = ["نتیجه‌ی بررسی", "صفحه‌ی بررسی‌شده", "امتیاز نهایی", "چهار مؤلفه",
                   "جزئیات شاخص‌ها", "معنی وضعیت‌ها", "بررسی صفحه‌ی دیگر"]
        # «بررسی صفحه‌ی دیگر» در سرصفحه هم هست؛ نمونه‌ی آخر (بخش پایانی) ملاک است
        positions = [html.index(m) for m in markers[:-1]] + [html.rindex(markers[-1])]
        assert positions == sorted(positions), positions

    def test_page_url_is_shown_in_the_head(self, client, monkeypatch):
        html = _analyze(client, monkeypatch, {})
        assert 'class="page-url"' in html and "example.com" in html

    def test_quick_rescan_form_still_present(self, client, monkeypatch):
        html = _analyze(client, monkeypatch, {})
        assert 'class="again-form"' in html

    def test_download_button_still_present(self, client, monkeypatch):
        html = _analyze(client, monkeypatch, {})
        assert "/download-pdf/" in html


class TestIndexPage:

    def test_lists_all_real_indicators(self, client):
        html = client.get("/").get_data(as_text=True)
        for code in ALL_CODES:
            assert f'dir="ltr">{code}</span>' in html, code

    def test_does_not_depend_on_external_fonts_or_cdn(self, client):
        html = client.get("/").get_data(as_text=True)
        assert "googleapis" not in html and "gstatic" not in html
        css = client.get("/static/style.css").get_data(as_text=True)
        assert "http://" not in css and "https://" not in css

    def test_local_font_files_are_served(self, client):
        for name in ("vazirmatn-arabic-wght.woff2", "vazirmatn-latin-wght.woff2"):
            assert client.get(f"/static/fonts/{name}").status_code == 200


class TestErrorDisplay:

    def test_fetch_failure_shows_hints_and_folds_technical_details(self, client, monkeypatch):
        def _fail(url, weights, **kw):
            raise appmod.FetchFailedError(url, "HTTPConnectionPool(host='x'): Max retries exceeded")
        monkeypatch.setattr(appmod, "process_single_url", _fail)
        html = client.post("/analyze", data={"url": "example.com"}).get_data(as_text=True)
        assert "بررسی انجام نشد" in html
        assert "جزئیات فنی" in html and "Max retries exceeded" in html
        assert "مسدود" in html  # راهنمای رفع مشکل

    def test_input_mistake_does_not_show_network_hints(self, client):
        html = client.post("/compare", data={"url": "a.example.com", "url2": "A.example.com/"}).get_data(as_text=True)
        assert "یکسان" in html
        assert "مسدود" not in html
        assert "جزئیات فنی" not in html
