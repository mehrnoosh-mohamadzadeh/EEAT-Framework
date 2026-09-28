# -*- coding: utf-8 -*-
"""
ابزار عیب‌یابی: نشان می‌دهد پروژه برای یک URL دقیقاً «چه HTML‌ای» دریافت می‌کند
و شاخص E3 (نظرات کاربران) روی همان HTML چه تصمیمی می‌گیرد.

چرا لازم است؟ چیزی که در «View Source» مرورگر می‌بینید، همیشه همان چیزی نیست
که برنامه دریافت می‌کند (بعضی سایت‌ها به ربات‌ها صفحه‌ی دیگری می‌دهند، یا
نظرها را بعداً با جاوااسکریپت می‌آورند). این ابزار همین تفاوت را نشان می‌دهد.

اجرا:
    python diagnose_url.py https://example.com/blog/post/
    python diagnose_url.py https://example.com/blog/post/ --render-js
"""

import argparse
import json
import re
import sys

from fetcher.page_downloader import fetch
from parser.html_parser import parse_html
from extractors import experience_extractor
from extractors.experience_extractor import ExperienceExtractor


def main():
    arg_parser = argparse.ArgumentParser(description="عیب‌یابی دریافت صفحه و شاخص E3")
    arg_parser.add_argument("url")
    arg_parser.add_argument("--render-js", action="store_true",
                            help="اجبار به رندر کامل با مرورگر (Playwright)")
    arg_parser.add_argument("--save", default="fetched_page.html",
                            help="مسیر ذخیره‌ی HTML دریافت‌شده (پیش‌فرض: fetched_page.html)")
    args = arg_parser.parse_args()

    print("=" * 60)
    has_new_code = hasattr(experience_extractor, "_count_repeated_comment_items")
    print("نسخه‌ی کد E3 (شمارش عمومی نظرها) فعال است؟", "بله" if has_new_code else "خیر — فایل experience_extractor.py هنوز قدیمی است")

    result = fetch(args.url, render_js=args.render_js)
    print("روش دریافت:", result.fetch_method)
    print("موفق:", result.success, "| کد وضعیت:", result.status_code, "| خطا:", result.error)
    if not result.success:
        print("\nصفحه دریافت نشد؛ تحلیل ممکن نیست.")
        sys.exit(1)

    html = result.html
    with open(args.save, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"طول HTML دریافت‌شده: {len(html):,} نویسه  (ذخیره شد در: {args.save})")

    print("-" * 60)
    print("نشانه‌های موجود در HTML دریافت‌شده:")
    checks = {
        "داده ساختاریافته JSON-LD": 'application/ld+json' in html,
        "نوع Comment در JSON-LD": '"@type":"Comment"' in html or '"@type": "Comment"' in html,
        "کلاس comment-list": "comment-list" in html,
        "کلاس comment-body": "comment-body" in html,
        "فرم نظر وردپرس": "wp-comments-post" in html,
    }
    for label, present in checks.items():
        print(f"  {'✓' if present else '✗'} {label}")
    print("  تعداد نوع Comment در JSON-LD:", len(re.findall(r'"@type"\s*:\s*"Comment"', html)))

    # فقط نشانه‌های دقیق صفحه‌ی چالش، و فقط وقتی صفحه کوچک است (صفحه‌ی واقعی
    # و بزرگ ممکن است به‌طور عادی کلمه‌ی captcha را در فرم نظر داشته باشد)
    bot_markers = ["Just a moment", "cf-browser-verification", "Attention Required"]
    found_bot = [m for m in bot_markers if m.lower() in html.lower()]
    if found_bot and len(html) < 50000:
        print("\n⚠️ هشدار: این HTML شبیه صفحه‌ی مسدودسازی/چالش ربات است:", found_bot)
        print("   یعنی سایت به برنامه صفحه‌ی واقعی را نداده؛ نتیجه‌ی تحلیل قابل‌اعتماد نیست.")

    parsed = parse_html(html, args.url)
    print("-" * 60)
    print("تعداد بلوک JSON-LD که با موفقیت خوانده شد:", len(parsed.json_ld_blocks))
    e3 = ExperienceExtractor()._e3_user_reviews(parsed)
    print("E3 امتیاز:", round(e3.value, 3) if e3.value is not None else None)
    print("E3 جزئیات:", json.dumps(e3.raw_details, ensure_ascii=False, indent=2))
    print("=" * 60)


if __name__ == "__main__":
    main()
