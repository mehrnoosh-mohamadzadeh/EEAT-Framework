"""
تست‌های واحد scoring/validation.py با داده‌ی فرضی (نه نمره‌های واقعی
داور، که هنوز جمع‌آوری نشده‌اند).
"""

import csv

import pytest

from scoring.validation import compute_spearman_per_component, load_framework_scores, load_human_ratings


def _write_csv(path, fieldnames, rows):
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


class TestLoadFunctions:

    def test_load_framework_scores(self, tmp_path):
        csv_path = tmp_path / "framework.csv"
        _write_csv(csv_path,
                    ["url", "category", "experience_score", "expertise_score",
                     "authority_score", "trust_score", "final_score"],
                    [{"url": "https://a.ir", "category": "high", "experience_score": "0.8",
                      "expertise_score": "0.7", "authority_score": "0.9", "trust_score": "0.6",
                      "final_score": "0.75"}])
        scores = load_framework_scores(str(csv_path))
        assert scores["https://a.ir"]["experience"] == 0.8
        assert scores["https://a.ir"]["final"] == 0.75

    def test_load_human_ratings(self, tmp_path):
        csv_path = tmp_path / "human.csv"
        _write_csv(csv_path,
                    ["url", "human_experience", "human_expertise", "human_authority", "human_trust"],
                    [{"url": "https://a.ir", "human_experience": "4", "human_expertise": "3",
                      "human_authority": "5", "human_trust": "4"}])
        ratings = load_human_ratings(str(csv_path))
        assert ratings["https://a.ir"]["experience"] == 4.0
        assert ratings["https://a.ir"]["authority"] == 5.0


class TestSpearmanComputation:

    def test_perfect_positive_correlation(self, tmp_path):
        """
        وقتی رتبه‌ی ابزار و انسان دقیقاً یکی است، rho باید ۱.۰ باشد —
        تست درستی خودِ فرمول همبستگی، نه ادعایی درباره‌ی کیفیت واقعی چارچوب.
        """
        framework_csv = tmp_path / "framework.csv"
        human_csv = tmp_path / "human.csv"

        urls = [f"https://site{i}.ir" for i in range(5)]
        framework_rows = [
            {"url": u, "category": "", "experience_score": str(0.1 * (i + 1)),
             "expertise_score": str(0.1 * (i + 1)), "authority_score": str(0.1 * (i + 1)),
             "trust_score": str(0.1 * (i + 1)), "final_score": str(0.1 * (i + 1))}
            for i, u in enumerate(urls)
        ]
        human_rows = [
            {"url": u, "human_experience": str(i + 1), "human_expertise": str(i + 1),
             "human_authority": str(i + 1), "human_trust": str(i + 1)}
            for i, u in enumerate(urls)
        ]
        _write_csv(framework_csv, ["url", "category", "experience_score", "expertise_score",
                                    "authority_score", "trust_score", "final_score"], framework_rows)
        _write_csv(human_csv, ["url", "human_experience", "human_expertise",
                                "human_authority", "human_trust"], human_rows)

        results = compute_spearman_per_component(str(framework_csv), str(human_csv))
        assert results["experience"]["rho"] == pytest.approx(1.0)
        assert results["overall"]["rho"] == pytest.approx(1.0)

    def test_returns_none_when_too_few_common_pages(self, tmp_path):
        """با کمتر از ۳ صفحه‌ی مشترک، نباید همبستگی محاسبه شود (بی‌معنی است)."""
        framework_csv = tmp_path / "framework.csv"
        human_csv = tmp_path / "human.csv"

        _write_csv(framework_csv, ["url", "category", "experience_score", "expertise_score",
                                    "authority_score", "trust_score", "final_score"],
                   [{"url": "https://a.ir", "category": "", "experience_score": "0.5",
                     "expertise_score": "0.5", "authority_score": "0.5", "trust_score": "0.5",
                     "final_score": "0.5"}])
        _write_csv(human_csv, ["url", "human_experience", "human_expertise",
                                "human_authority", "human_trust"],
                   [{"url": "https://a.ir", "human_experience": "3", "human_expertise": "3",
                     "human_authority": "3", "human_trust": "3"}])

        results = compute_spearman_per_component(str(framework_csv), str(human_csv))
        assert results["experience"] is None

    def test_ignores_urls_only_in_one_source(self, tmp_path):
        """صفحاتی که فقط در یکی از دو فایل هستند (نه هردو) نباید وارد محاسبه شوند."""
        framework_csv = tmp_path / "framework.csv"
        human_csv = tmp_path / "human.csv"

        framework_rows = [
            {"url": f"https://site{i}.ir", "category": "", "experience_score": str(0.1 * (i + 1)),
             "expertise_score": "0.5", "authority_score": "0.5", "trust_score": "0.5",
             "final_score": "0.5"}
            for i in range(4)
        ]
        # فقط ۳ تای اول در نمره‌های انسانی هستند
        human_rows = [
            {"url": f"https://site{i}.ir", "human_experience": str(i + 1), "human_expertise": "3",
             "human_authority": "3", "human_trust": "3"}
            for i in range(3)
        ]
        _write_csv(framework_csv, ["url", "category", "experience_score", "expertise_score",
                                    "authority_score", "trust_score", "final_score"], framework_rows)
        _write_csv(human_csv, ["url", "human_experience", "human_expertise",
                                "human_authority", "human_trust"], human_rows)

        results = compute_spearman_per_component(str(framework_csv), str(human_csv))
        assert results["experience"]["n"] == 3
