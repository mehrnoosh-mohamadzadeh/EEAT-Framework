"""
نقطه ورود اصلی پروژه — اجرای کامل پایپ‌لاین روی یک یا چند URL.

استفاده (بعد از پیاده‌سازی کامل ماژول‌ها):

    python main.py --input data/sample_urls.csv --weights config/weights_equal.yaml --output results.csv

جریان اجرا (طبق معماری مستندشده در README.md):

    URL --> Fetcher --> Parser --> Extractors (x4) --> Normalizer --> Scorer --> Reporter
"""

import argparse
import csv
import sys

from pipeline import process_single_url_safe
from scoring.scorer import load_weights
from reporting.reporter import export_to_csv, export_to_json


def read_urls_from_csv(input_path: str) -> list[dict]:
    """خواندن ستون‌های url و (اختیاری) category از فایل CSV ورودی."""
    rows = []
    with open(input_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get("url", "").strip().startswith("#"):
                continue
            rows.append(row)
    return rows


def main():
    arg_parser = argparse.ArgumentParser(
        description="اجرای چارچوب کمی‌سازی E-E-A-T روی نمونه‌ای از URL ها"
    )
    arg_parser.add_argument("--input", required=True, help="مسیر فایل CSV شامل ستون url")
    arg_parser.add_argument("--weights", default="config/weights_equal.yaml")
    arg_parser.add_argument("--output", default="results.csv")
    arg_parser.add_argument("--render-js", action="store_true",
                             help="اجبار به استفاده از Playwright برای همه صفحات")
    args = arg_parser.parse_args()

    weights = load_weights(args.weights)
    rows = read_urls_from_csv(args.input)

    categories = {row["url"]: row.get("category", "") for row in rows}
    scores = []

    for row in rows:
        url = row["url"]
        print(f"در حال پردازش: {url}")
        result = process_single_url_safe(url, weights, render_js=args.render_js)
        if result is not None:
            result.weights_used = args.weights
            scores.append(result)

    if not scores:
        print("هیچ صفحه‌ای با موفقیت پردازش نشد.", file=sys.stderr)
        sys.exit(1)

    export_to_csv(scores, args.output, categories=categories)
    json_output = args.output.rsplit(".", 1)[0] + ".json"
    export_to_json(scores, json_output)

    print(f"\nنتایج ذخیره شد: {args.output} و {json_output}")
    print(f"تعداد صفحات پردازش‌شده: {len(scores)} از {len(rows)}")


if __name__ == "__main__":
    main()
