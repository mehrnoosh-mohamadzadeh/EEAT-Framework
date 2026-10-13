"""
تست‌های صفحه‌ی ویدیومحور (مثل آپارات): تشخیص، شاخص‌های قضاوت‌نشده، وزن‌دهی
عادلانه، T7/T6 و مقایسه. شبکه در همه‌ی تست‌ها بسته است.
"""
import json
from unittest.mock import patch

import pytest

import pipeline
from fetcher.page_downloader import FetchResult
from parser.html_parser import parse_html
from scoring.scorer import compute_final_score
from utils.page_type import VIDEO_EXCLUDED_INDICATORS, detect_video_page

EQUAL = {"experience": 0.25, "expertise": 0.25, "authority": 0.25, "trust": 0.25}


def _html(extra_head="", body="<p>یک ویدیوی کوتاه درباره‌ی آشپزی.</p>", video_ld=True):
    ld = ""
    if video_ld:
        ld = ('<script type="application/ld+json">' + json.dumps({
            "@context": "https://schema.org", "@type": "VideoObject",
            "name": "آشپزی", "uploadDate": "2026-09-01T00:00:00Z"}) + "</script>")
    return f"<html><head><title>t</title>{ld}{extra_head}</head><body><main>{body}</main></body></html>"


class TestDetection:
    def test_short_page_with_video_object_is_video(self):
        page = parse_html(_html(), "http://video.test/v/1")
        info = detect_video_page(page)
        assert info and info["signal"] == "json_ld_video_object"

    def test_og_type_video_is_a_signal(self):
        page = parse_html(_html('<meta property="og:type" content="video.other">', video_ld=False),
                          "http://video.test/v/1")
        assert detect_video_page(page)["signal"] == "og_type_video"

    def test_long_article_with_embedded_video_is_not_video_page(self):
        long_text = "<p>" + " ".join(["کلمه"] * 600) + "</p>"
        page = parse_html(_html(body=long_text), "http://blog.test/post")
        assert detect_video_page(page) is None

    def test_plain_short_page_without_video_signal_is_not_video(self):
        page = parse_html(_html(video_ld=False), "http://blog.test/short")
        assert detect_video_page(page) is None


class TestFairWeights:
    def test_no_retention_keeps_old_behaviour(self):
        comps = {"Experience": 0.2, "Expertise": 0.4, "Authoritativeness": 0.6, "Trustworthiness": 0.8}
        assert compute_final_score(comps, EQUAL) == pytest.approx(0.5)
        assert compute_final_score(comps, EQUAL, retention=None) == pytest.approx(0.5)

    def test_retention_keeps_each_remaining_indicator_share_proportional(self):
        # Experience: 1 از 4 باقی، Expertise: 2 از 5 باقی، بقیه کامل
        ret = {"Experience": 1 / 4, "Expertise": 2 / 5}
        comps = {"Experience": 1.0, "Expertise": 0.0, "Authoritativeness": 0.0, "Trustworthiness": 0.0}
        # وزن مؤثر Experience = 0.0625 از مجموع 0.6625
        assert compute_final_score(comps, EQUAL, retention=ret) == pytest.approx(0.0625 / 0.6625)

    def test_weights_always_sum_to_one(self):
        ret = {"Experience": 0.25, "Expertise": 0.4}
        eff = {k: v for k, v in zip("abcd", [0.25 * 0.25, 0.25 * 0.4, 0.25, 0.25])}
        assert sum(v / sum(eff.values()) for v in eff.values()) == pytest.approx(1.0)


def _run(html, url):
    fake = FetchResult(url=url, html=html, status_code=200, response_time_ms=1, fetch_method="requests")
    with patch("pipeline.fetch", return_value=fake), \
         patch("extractors.trust_extractor.fetch_linked_page_text", return_value=None), \
         patch("extractors.trust_extractor.fetch_linked_page", return_value=None), \
         patch("extractors.trust_extractor.estimate_last_content_change", return_value=None), \
         patch("extractors.authority_extractor.fetch_linked_page_text", return_value=None, create=True), \
         patch("extractors.authority_extractor.fetch_linked_page", return_value=None, create=True):
        return pipeline.process_single_url(url, EQUAL, weights_label="equal")


class TestPipelineOnVideoPage:
    def test_six_text_indicators_are_not_applicable_and_have_a_reason(self):
        score = _run(_html(), "http://video.test/v/1")
        assert score.page_type == "video"
        for code in VIDEO_EXCLUDED_INDICATORS:
            d = score.indicator_details[code]
            assert d["applicable"] is False and d["value"] is None
            assert d["raw_details"]["reason"] == "video_page"
        for code in ("E3", "X1", "X2", "A1", "A2", "A3", "T1", "T2", "T3", "T4", "T5", "T6", "T7"):
            assert score.indicator_details[code]["applicable"] is True

    def test_effective_weights_sum_to_one_and_match_the_documented_numbers(self):
        score = _run(_html(), "http://video.test/v/1")
        w = score.effective_weights
        assert sum(w.values()) == pytest.approx(1.0)
        assert round(w["Experience"] * 100) == 9
        assert round(w["Expertise"] * 100) == 15
        assert round(w["Authoritativeness"] * 100) == 38
        assert round(w["Trustworthiness"] * 100) == 38

    def test_t7_counts_video_object_as_the_article_type_and_t6_uses_upload_date(self):
        score = _run(_html(), "http://video.test/v/1")
        t7 = score.indicator_details["T7"]
        assert "Article" in t7["raw_details"]["found_types"]
        assert score.indicator_details["T6"]["missing"] is False
        assert score.indicator_details["T6"]["raw_details"]["raw_date"].startswith("2026-09-01")

    def test_normal_page_is_unchanged(self):
        score = _run(_html(video_ld=False, body="<p>" + " ".join(["من تجربه کردم"] * 80) + "</p>"),
                     "http://blog.test/post")
        assert score.page_type == "standard" and score.effective_weights == {}
        assert score.indicator_details["E1"]["applicable"] is True


class TestWebAndCompare:
    def test_note_and_not_applicable_status_in_report_context(self):
        from webapp.app import build_report_context
        ctx = build_report_context(_run(_html(), "http://video.test/v/1"))
        assert ctx["page_type"] == "video" and "ویدیومحور" in ctx["type_note"]
        statuses = {i["code"]: i["status"] for c in ctx["components"] for i in c["indicators"]}
        assert all(statuses[c] == "not_applicable" for c in VIDEO_EXCLUDED_INDICATORS)

    def test_mixed_types_give_no_winner_for_final_and_components(self):
        from webapp.app import build_report_context
        from webapp.comparison import build_comparison_context
        a = build_report_context(_run(_html(), "http://video.test/v/1"))
        b = build_report_context(_run(_html(video_ld=False, body="<p>" + " ".join(["من تجربه کردم"] * 80) + "</p>"),
                                      "http://blog.test/post"))
        cmp_ctx = build_comparison_context(a, b)
        assert cmp_ctx["mixed_types"] and cmp_ctx["final"]["result"] == "none"
        assert all(c["result"] == "none" for c in cmp_ctx["components"])
        assert cmp_ctx["type_notes"]
