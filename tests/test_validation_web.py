"""
تست‌های صفحه‌ی اعتبارسنجی وب (فایل‌های جدولی، اسپیرمن، فاصله‌ی اطمینان، نمودار).
داده‌ها همه ساختگیِ آزمون‌اند و هیچ ربطی به نتیجه‌ی پایان‌نامه ندارند.
"""
import io
import math
import random

import pytest

from scoring.validation import (
    ValidationInputError, analyze_pairs, build_blank_rating_sheet, decode_csv_bytes,
    normalize_url_key, strength_label, thesis_paragraph, validate_uploaded,
)
from webapp.app import app

HEAD = "url,category,experience_score,expertise_score,authority_score,trust_score,final_score\n"
HHEAD = "url,human_experience,human_expertise,human_authority,human_trust\n"


def _datasets(n=40, seed=3):
    rnd = random.Random(seed)
    fw, hu = [HEAD], [HHEAD]
    for i in range(n):
        base = rnd.random()
        vals = [min(1, max(0, base + rnd.gauss(0, 0.1))) for _ in range(4)]
        fin = sum(vals) / 4
        fw.append(f"https://s{i}.test/p,x," + ",".join(f"{v:.3f}" for v in vals) + f",{fin:.3f}\n")
        h = [min(5, max(1, round(1 + 4 * v + rnd.gauss(0, 0.5)))) for v in vals]
        hu.append(f"s{i}.test/p/," + ",".join(str(x) for x in h) + "\n")   # آدرس با شکل کمی متفاوت
    return "".join(fw), "".join(hu)


class TestCore:
    def test_url_key_ignores_scheme_www_slash_and_case(self):
        assert normalize_url_key("HTTPS://www.Site.test/a/") == normalize_url_key("site.test/a")

    def test_strength_words_and_sign(self):
        assert strength_label(0.1) == "بسیار ضعیف"
        assert strength_label(0.5) == "متوسط"
        assert strength_label(0.9) == "بسیار قوی"
        assert strength_label(-0.7).endswith("(منفی)")

    def test_ci_contains_rho_and_needs_ten_pairs(self):
        xs = [i / 20 for i in range(20)]
        ys = [1 + round(4 * x) for x in xs]
        r = analyze_pairs(xs, ys)
        assert r["ci_low"] < r["rho"] <= r["ci_high"] <= 1
        small = analyze_pairs(xs[:6], ys[:6])
        assert small["ci_low"] is None

    def test_constant_input_returns_none_not_a_fake_number(self):
        assert analyze_pairs([0.1, 0.2, 0.3, 0.4], [3, 3, 3, 3]) is None
        assert analyze_pairs([0.1, 0.2], [1, 2]) is None

    def test_validate_matches_urls_in_different_shapes(self):
        fw, hu = _datasets()
        rep = validate_uploaded(fw, hu)
        assert rep["counts"]["matched"] == 40
        assert rep["results"]["overall"]["rho"] > 0.7 and rep["results"]["overall"]["n"] == 40

    def test_out_of_range_and_duplicates_are_reported_not_hidden(self):
        fw, hu = _datasets(12)
        hu += "s0.test/p,9,3,3,3\n"   # تکراری
        lines = hu.splitlines()
        lines[2] = "s1.test/p/,9,3,3,3"   # نمره‌ی ۹ نامعتبر
        rep = validate_uploaded(fw, "\n".join(lines) + "\n")
        assert any("خارج از بازه" in w for w in rep["warnings"])
        assert any("تکراری" in w for w in rep["warnings"])

    def test_small_sample_warning_and_single_rater_warning_always_present(self):
        fw, hu = _datasets(8)
        rep = validate_uploaded(fw, hu)
        assert any("یک داور" in w for w in rep["warnings"])
        assert any("کمتر است" in w for w in rep["warnings"])

    def test_missing_columns_give_a_clear_persian_error(self):
        with pytest.raises(ValidationInputError) as e:
            validate_uploaded("url,x\na,1\n", HHEAD)
        assert "ستون" in str(e.value)

    def test_blank_sheet_has_urls_only_and_no_tool_scores(self):
        fw, _ = _datasets(5)
        sheet = build_blank_rating_sheet(fw)
        lines = sheet.strip().splitlines()
        assert lines[0] == "url,human_experience,human_expertise,human_authority,human_trust"
        assert len(lines) == 6 and all(l.count(",") == 4 and l.endswith(",,,,") for l in lines[1:])
        assert not any(ch.isdigit() for l in lines[1:] for ch in l.split(",", 1)[1])  # هیچ نمره‌ای لو نرفته

    def test_non_utf8_bytes_are_rejected_with_hint(self):
        with pytest.raises(ValidationInputError) as e:
            decode_csv_bytes("نمره".encode("cp1256"))
        assert "UTF-8" in str(e.value)

    def test_thesis_paragraph_uses_only_computed_numbers(self):
        fw, hu = _datasets()
        rep = validate_uploaded(fw, hu)
        text = thesis_paragraph(rep)
        r = rep["results"]["overall"]
        from scoring.validation import _fa
        assert f"ضریب اسپیرمن {_fa(format(r['rho'], '.2f'))}" in text and "یک داور" in text
        assert f"روی {_fa(r['n'])} صفحه" in text and "ρ" not in text


class TestRoutes:
    def setup_method(self):
        self.c = app.test_client()

    def test_page_loads_and_is_linked_from_masthead(self):
        html = self.c.get("/validation").get_data(as_text=True)
        assert "اعتبارسنجی با داور انسانی" in html
        assert "/validation" in self.c.get("/").get_data(as_text=True)

    def test_blank_sheet_download(self):
        fw, _ = _datasets(4)
        r = self.c.post("/validation/sheet", data={"framework_csv": (io.BytesIO(fw.encode()), "r.csv"), "fmt": "csv"},
                        content_type="multipart/form-data")
        assert r.status_code == 200 and r.mimetype == "text/csv"
        assert r.data.startswith("﻿".encode("utf-8"))

    def test_blank_sheet_download_default_is_excel(self):
        fw, _ = _datasets(4)
        r = self.c.post("/validation/sheet", data={"framework_csv": (io.BytesIO(fw.encode()), "r.csv")},
                        content_type="multipart/form-data")
        assert r.status_code == 200 and r.mimetype.endswith("spreadsheetml.sheet")
        assert r.data[:2] == b"PK"

    def test_analyze_shows_table_scatter_warnings_and_paragraph(self):
        fw, hu = _datasets()
        r = self.c.post("/validation/analyze", data={
            "framework_csv": (io.BytesIO(fw.encode()), "r.csv"),
            "human_csv": (io.BytesIO(hu.encode()), "h.csv")}, content_type="multipart/form-data")
        html = r.get_data(as_text=True)
        assert r.status_code == 200
        assert html.count('class="scatter"') == 5
        assert "هشدارهای روش‌شناختی" in html and "پیش‌نویس متن فصل نتایج" in html
        assert "همبستگی اسپیرمن" in html

    def test_missing_file_and_bad_columns_show_error_not_crash(self):
        r = self.c.post("/validation/analyze", data={}, content_type="multipart/form-data")
        assert r.status_code == 400 and "انتخاب نشده" in r.get_data(as_text=True)
        r = self.c.post("/validation/analyze", data={
            "framework_csv": (io.BytesIO(b"a,b\n1,2\n"), "r.csv"),
            "human_csv": (io.BytesIO(HHEAD.encode()), "h.csv")}, content_type="multipart/form-data")
        assert r.status_code == 400 and "ستون" in r.get_data(as_text=True)
