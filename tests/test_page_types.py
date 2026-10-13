"""
تست‌های ثبت نوع صفحه (utils/page_type.py): تشخیص محصول سخت‌گیرانه، رگرسیون ایراد «تومان»،
اولویت ویدیو، و رفتار خط لوله برای محصول. شبکه بسته است.
"""
import json
from unittest.mock import patch

import pytest

import pipeline
from extractors.experience_extractor import ExperienceExtractor
from fetcher.page_downloader import FetchResult
from parser.html_parser import parse_html
from utils.page_type import PAGE_TYPES, detect_page_type
from webapp.app import build_report_context

EQUAL = {"experience": 0.25, "expertise": 0.25, "authority": 0.25, "trust": 0.25}
LONG = "<p>" + " ".join(["من این کار را خودم امتحان کردم و نتیجه خوب بود"] * 40) + "</p>"


def _page(body, ld=None):
    script = ""
    if ld is not None:
        script = '<script type="application/ld+json">' + json.dumps(ld) + "</script>"
    return parse_html(f"<html><head><title>t</title>{script}</head><body><main>{body}</main></body></html>",
                      "http://shop.test/p/1")


class TestDetection:
    def test_product_schema_with_offers_is_product(self):
        info = detect_page_type(_page("<p>گوشی</p>", {"@type": "Product", "name": "x", "offers": {"price": "1"}}))
        assert info["type"] == "product" and info["signal"] == "json_ld_product_with_offers"

    def test_review_article_with_product_schema_but_no_offers_is_not_product(self):
        assert detect_page_type(_page(LONG, {"@type": "Product", "name": "x",
                                              "aggregateRating": {"ratingValue": 4}})) is None

    def test_add_to_cart_phrase_is_product(self):
        assert detect_page_type(_page("<button>افزودن به سبد خرید</button>"))["type"] == "product"

    def test_regression_news_with_toman_and_price_word_is_not_product(self):
        """ایراد قدیمی: «تومان» یا «قیمت:» به‌تنهایی صفحه را محصول می‌کرد و E2 را کنار می‌گذاشت."""
        page = _page("<p>قیمت: دلار امروز ۶۰ هزار تومان شد. " + "خبر " * 50 + "</p>")
        assert detect_page_type(page) is None

    def test_e2_is_judged_on_news_page_mentioning_toman(self):
        page = _page("<p>قیمت: ۶۰ هزار تومان. من خودم این را تجربه کردم. " + "متن " * 60 + "</p>")
        e2 = next(r for r in ExperienceExtractor().extract(page) if r.code == "E2")
        assert e2.applicable is True

    def test_video_wins_over_product(self):
        page = _page("<p>کوتاه</p><button>افزودن به سبد خرید</button>",
                     {"@type": "VideoObject", "name": "v", "uploadDate": "2026-09-01"})
        assert detect_page_type(page)["type"] == "video"

    def test_registry_has_persian_labels_and_reasons_for_every_excluded_indicator(self):
        for info in PAGE_TYPES.values():
            assert info["label"] and info["reason"] and info["excluded"]
            assert all(reason.strip() for reason in info["excluded"].values())


def _run(html, url="http://shop.test/p/1"):
    fake = FetchResult(url=url, html=html, status_code=200, response_time_ms=1, fetch_method="requests")
    with patch("pipeline.fetch", return_value=fake), \
         patch("extractors.trust_extractor.fetch_linked_page_text", return_value=None), \
         patch("extractors.trust_extractor.fetch_linked_page", return_value=None), \
         patch("extractors.trust_extractor.estimate_last_content_change", return_value=None), \
         patch("extractors.authority_extractor.fetch_linked_page_text", return_value=None, create=True), \
         patch("extractors.authority_extractor.fetch_linked_page", return_value=None, create=True):
        return pipeline.process_single_url(url, EQUAL, weights_label="equal")


class TestPipelineOnProductPage:
    HTML = ("<html><head><title>p</title></head><body><main><h1>گوشی</h1>"
            "<button>افزودن به سبد خرید</button></main></body></html>")

    def test_e2_x3_x5_not_applicable_others_judged(self):
        score = _run(self.HTML)
        assert score.page_type == "product"
        for code in ("E2", "X3", "X5"):
            d = score.indicator_details[code]
            assert d["applicable"] is False and d["raw_details"]["reason"] == "product_page"
        for code in ("E1", "E3", "E4", "X1", "X2", "X4", "A1", "T1", "T7"):
            assert score.indicator_details[code]["applicable"] is True

    def test_effective_weights_follow_the_kept_fraction(self):
        w = _run(self.HTML).effective_weights
        assert sum(w.values()) == pytest.approx(1.0)
        # تجربه ۳ از ۴، تخصص ۲ از ۵ (X3 و X5 رفتند)، بقیه کامل
        raw = {"Experience": 0.75, "Expertise": 0.6, "Authoritativeness": 1.0, "Trustworthiness": 1.0}
        tot = sum(raw.values())
        for k, v in raw.items():
            assert w[k] == pytest.approx(v / tot)

    def test_note_uses_persian_indicator_names_not_codes(self):
        note = build_report_context(_run(self.HTML))["type_note"]
        assert "محصول" in note and "زبان تجربه‌محور" in note
        assert "E2" not in note and "X3" not in note

    def test_standard_page_has_no_note(self):
        html = "<html><head><title>m</title></head><body><main>" + LONG + "</main></body></html>"
        ctx = build_report_context(_run(html, "http://blog.test/a"))
        assert ctx["type_note"] is None and ctx["page_type"] == "standard"
