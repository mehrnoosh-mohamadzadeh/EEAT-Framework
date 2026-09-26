"""
نقطه ورود فاز ۶ (اعتبارسنجی، مورد ۱۲) — مقایسه‌ی خروجی چارچوب با
نمره‌های انسانی و چاپ گزارش همبستگی اسپیرمن.

استفاده (بعد از این‌که هم results.csv از main.py گرفتید، هم
data/human_ratings_template.csv را برای همان صفحات پر کردید):

    python main.py --input data/sample_urls.csv --output results.csv
    # ... نمره‌دهی انسانی طبق data/rating_rubric.md در یک کپی از
    # data/human_ratings_template.csv ...
    python validate.py --framework-scores results.csv --human-ratings data/my_ratings_filled.csv

⚠️ این اسکریپت فقط همبستگی اسپیرمن را حساب می‌کند (ابزار در برابر
یک داور انسانی). توافق بین‌داوری این‌جا نیست چون این پروژه با یک
داور انجام می‌شود — رجوع به data/rating_rubric.md برای توضیح کامل
این محدودیت.
"""

import argparse
import sys

from scoring.validation import compute_spearman_per_component, print_validation_report


def main():
    arg_parser = argparse.ArgumentParser(
        description="اعتبارسنجی چارچوب E-E-A-T با مقایسه‌ی خروجی آن با نمره‌های انسانی"
    )
    arg_parser.add_argument("--framework-scores", required=True,
                             help="مسیر CSV خروجی main.py (شامل ستون‌های *_score)")
    arg_parser.add_argument("--human-ratings", required=True,
                             help="مسیر CSV نمره‌های انسانی پرشده (طبق فرمت data/human_ratings_template.csv)")
    args = arg_parser.parse_args()

    try:
        results = compute_spearman_per_component(args.framework_scores, args.human_ratings)
    except FileNotFoundError as e:
        print(f"خطا: فایل پیدا نشد — {e}", file=sys.stderr)
        sys.exit(1)

    print_validation_report(results)


if __name__ == "__main__":
    main()
