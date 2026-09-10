"""
ماژول Reporter — تولید خروجی نهایی از نتایج امتیازدهی.

خروجی‌های پشتیبانی‌شده:
  - JSON: جزئیات کامل هر شاخص برای یک یا چند صفحه (برای دیباگ/بررسی دقیق)
  - CSV:  جدول خلاصه امتیازها برای همه صفحات نمونه (برای فاز ۵ - ارزیابی،
          شامل ستون‌های امتیاز هر مؤلفه + امتیاز نهایی + دسته‌بندی صفحه)
"""

import json
import csv
from scoring.scorer import PageScore


def export_to_json(scores: list, output_path: str) -> None:
    """ذخیره نتایج کامل (شامل جزئیات شاخص‌ها) به‌صورت JSON."""
    data = []
    for s in scores:
        data.append({
            "url": s.url,
            "component_scores": s.component_scores,
            "final_score": s.final_score,
            "weights_used": s.weights_used,
            "excluded_indicators": s.excluded_indicators,
            "missing_indicators": s.missing_indicators,
        })
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def export_to_csv(scores: list, output_path: str, categories: dict | None = None) -> None:
    """
    ذخیره جدول خلاصه (یک ردیف به ازای هر صفحه) به‌صورت CSV.

    categories: دیکشنری اختیاری {url: "high_quality"/"medium_quality"/...}
                برای افزودن ستون دسته‌بندی دستی (برای فاز ۵ - ارزیابی،
                محاسبه میانگین هر دسته و همبستگی اسپیرمن).
    """
    categories = categories or {}

    fieldnames = ["url", "category", "experience_score", "expertise_score",
                  "authority_score", "trust_score", "final_score"]

    with open(output_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for s in scores:
            writer.writerow({
                "url": s.url,
                "category": categories.get(s.url, ""),
                "experience_score": s.component_scores.get("Experience"),
                "expertise_score": s.component_scores.get("Expertise"),
                "authority_score": s.component_scores.get("Authoritativeness"),
                "trust_score": s.component_scores.get("Trustworthiness"),
                "final_score": s.final_score,
            })
