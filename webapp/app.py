# -*- coding: utf-8 -*-
"""
رابط وب پروژه E-E-A-T Framework.

اجرا (از پوشه اصلی پروژه eeat_framework/):
    python webapp/app.py
سپس در مرورگر برو به: http://127.0.0.1:5000
"""

import os
import sys
from urllib.parse import urlparse

# اضافه‌کردن پوشه اصلی پروژه (یک سطح بالاتر از webapp/) به sys.path
# تا import هایی مثل "from pipeline import ..." و "from scoring.scorer
# import ..." درست کار کنند، فارغ از این‌که این فایل از کجا اجرا شود.
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from flask import Flask, render_template, request

from pipeline import process_single_url, FetchFailedError
from scoring.scorer import load_weights
from webapp.recommendations import (
    COMPONENT_LABELS, COMPONENT_INDICATOR_CODES, INDICATOR_LABELS,
    IMPROVEMENT_TIPS, IMPROVEMENT_THRESHOLD, get_status_level,
)


app = Flask(__name__)

WEIGHTS_PATH = os.path.join(PROJECT_ROOT, "config", "weights_equal.yaml")
_weights_cache = None


def get_weights():
    global _weights_cache
    if _weights_cache is None:
        _weights_cache = load_weights(WEIGHTS_PATH)
    return _weights_cache


def make_display_url(url: str, max_len: int = 70) -> str:
    """
    نسخه کوتاه و قابل‌نمایش یک URL — بدون query string و fragment
    طولانی (که می‌تواند خیلی بلند و رمزنگاری‌شده باشد، مثلاً در لینک‌های
    نتایج جستجوی گوگل). آدرس واقعی همچنان کامل برای تحلیل استفاده
    می‌شود؛ این فقط برای نمایش تمیزتر در گزارش است.
    """
    parsed = urlparse(url)
    clean = parsed.netloc + parsed.path
    if len(clean) > max_len:
        clean = clean[:max_len].rstrip() + "…"
    return clean or url


def _format_evidence(raw_details: dict) -> str:
    """
    تبدیل دیکشنری raw_details هر شاخص به یک خط متن قابل‌فهم — برای
    نمایش شفاف «چرا این امتیاز داده شد» در گزارش، بدون نیاز به حدس زدن.
    """
    if not raw_details:
        return ""

    labels = {
        "channels_found": "کانال‌های یافت‌شده",
        "details_found": "جزئیات یافت‌شده",
        "found_fields": "فیلدهای یافت‌شده",
        "found_types": "انواع یافت‌شده",
        "review_count": "تعداد نظر (طبق داده ساختاریافته)",
        "social_links_found": "تعداد لینک شبکه اجتماعی",
        "qualified_images": "تعداد تصویر واجد شرایط",
        "days_since_update": "روز از آخرین به‌روزرسانی",
        "about_page_fetched": "صفحه درباره‌ما دانلود شد؟",
        "contact_page_fetched": "صفحه تماس دانلود شد؟",
        "whatsapp_link_detected": "لینک واتساپ پیدا شد؟",
        "tel_link_detected": "لینک تماس مستقیم (tel:) پیدا شد؟",
        "mailto_link_detected": "لینک ایمیل مستقیم (mailto:) پیدا شد؟",
        "text_signal": "نشانه متنی نظرات",
        "structural_signal": "نشانه ساختاری نظرات",
        "visible_signal_present": "نشانه بصری نظرات موجود است؟",
    }

    parts = []
    for key, value in raw_details.items():
        if key in ("reason", "note"):
            continue
        label = labels.get(key, key)
        if isinstance(value, list):
            value_str = "، ".join(str(v) for v in value) if value else "هیچ‌کدام"
        elif isinstance(value, bool):
            value_str = "بله" if value else "خیر"
        else:
            value_str = str(value)
        parts.append(f"{label}: {value_str}")

    note = raw_details.get("note")
    result = " | ".join(parts)
    if note:
        result = (result + " — " if result else "") + note
    return result


def build_report_context(page_score) -> dict:
    """
    تبدیل PageScore خام به ساختاری آماده برای قالب results.html:
    هر مؤلفه به همراه لیست شاخص‌هایش (با برچسب فارسی، سطح وضعیت،
    و توصیه بهبود در صورت نیاز).
    """
    components = []
    for component_name, indicator_codes in COMPONENT_INDICATOR_CODES.items():
        indicators = []
        for code in indicator_codes:
            detail = page_score.indicator_details.get(code, {})
            value = detail.get("value")
            missing = detail.get("missing", False)
            applicable = detail.get("applicable", True)
            status = get_status_level(value, missing, applicable)

            show_tip = status in ("fail", "warn")
            indicators.append({
                "code": code,
                "label": INDICATOR_LABELS.get(code, code),
                "value": value,
                "value_percent": round(value * 100) if value is not None else None,
                "status": status,
                "tip": IMPROVEMENT_TIPS.get(code) if show_tip else None,
                "evidence": _format_evidence(detail.get("raw_details") or {}),
            })

        component_score = page_score.component_scores.get(component_name)
        component_status = get_status_level(
            component_score, missing=(component_score is None), applicable=True
        )
        components.append({
            "key": component_name,
            "label": COMPONENT_LABELS.get(component_name, component_name),
            "score": component_score,
            "score_percent": round(component_score * 100) if component_score is not None else None,
            "status": component_status,
            "indicators": indicators,
        })

    return {
        "url": page_score.url,
        "display_url": make_display_url(page_score.url),
        "final_score_percent": round(page_score.final_score * 100),
        "components": components,
    }


@app.route("/", methods=["GET"])
def index():
    return render_template("index.html")


@app.route("/analyze", methods=["POST"])
def analyze():
    url = request.form.get("url", "").strip()

    if not url:
        return render_template("index.html", error="لطفاً یک آدرس وارد کنید.")

    if not (url.startswith("http://") or url.startswith("https://")):
        url = "https://" + url

    try:
        page_score = process_single_url(url, get_weights(), weights_label="equal")
    except FetchFailedError as e:
        return render_template(
            "index.html",
            error=f"دانلود صفحه ناموفق بود. جزئیات: {e.reason}",
            failed_url=url,
        )
    except Exception as e:
        return render_template(
            "index.html",
            error=f"خطایی هنگام پردازش صفحه رخ داد: {e}",
            failed_url=url,
        )

    context = build_report_context(page_score)
    return render_template("results.html", **context)


if __name__ == "__main__":
    app.run(debug=False, use_reloader=False, host="0.0.0.0", port=5000)
