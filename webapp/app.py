# -*- coding: utf-8 -*-
"""
رابط وب پروژه E-E-A-T Framework.

اجرا (از پوشه اصلی پروژه eeat_framework/):
    python webapp/app.py
سپس در مرورگر برو به: http://127.0.0.1:5000
"""

import os
import sys
import tempfile
import uuid
from collections import OrderedDict
from urllib.parse import urlparse

# اضافه‌کردن پوشه اصلی پروژه (یک سطح بالاتر از webapp/) به sys.path
# تا import هایی مثل "from pipeline import ..." و "from scoring.scorer
# import ..." درست کار کنند، فارغ از این‌که این فایل از کجا اجرا شود.
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from flask import Flask, render_template, request, send_file, abort

from pipeline import process_single_url, FetchFailedError
from scoring.scorer import load_weights
from webapp.recommendations import (
    COMPONENT_LABELS, COMPONENT_INDICATOR_CODES, INDICATOR_LABELS,
    IMPROVEMENT_TIPS, IMPROVEMENT_THRESHOLD, get_status_level,
)
from reporting.pdf_report import generate_pdf_report, generate_comparison_pdf
from webapp.comparison import build_comparison_context, normalize_url_for_compare
from webapp.validation_web import validation_bp
from utils.page_type import PAGE_TYPES


app = Flask(__name__)
app.register_blueprint(validation_bp)

WEIGHTS_PATH = os.path.join(PROJECT_ROOT, "config", "weights_equal.yaml")
_weights_cache = None

# ---------------------------------------------------------------------------
# کش فایل‌های PDF تولیدشده برای دانلود
# ---------------------------------------------------------------------------
# چرا این‌طور: Flask این‌جا stateless است — نتیجه‌ی /analyze فقط به صفحه‌ی
# نتیجه رندر می‌شود و هیچ‌جا ذخیره نمی‌ماند. برای این‌که دکمه‌ی «دانلود PDF»
# بدون اجرای دوباره‌ی کل تحلیل (که با Playwright می‌تواند کند باشد) کار
# کند، PDF همان لحظه‌ی /analyze یک‌بار ساخته و روی دیسک (پوشه‌ی موقت سیستم)
# ذخیره می‌شود؛ یک توکن تصادفی کوتاه (نه URL خام، برای جلوگیری از حدس‌زدن
# مسیر فایل توسط کاربر دیگر) به آن اشاره می‌کند.
# محدودیت صادقانه: این کش فقط در حافظه‌ی همین پردازش است — با ری‌استارت
# سرور خالی می‌شود، و فقط برای یک کاربر محلی (نه استقرار چندکاربره‌ی
# واقعی) طراحی شده، که دقیقاً همان سناریوی استفاده‌ی این پروژه است.
# برای جلوگیری از پر شدن بی‌حدوحصر دیسک در یک نشست طولانی، فقط
# PDF_CACHE_MAX_SIZE مورد آخر نگه داشته می‌شود؛ قدیمی‌ترین‌ها هم از
# دیکشنری و هم از دیسک پاک می‌شوند.
PDF_CACHE_MAX_SIZE = 30
_pdf_cache: "OrderedDict[str, tuple[str, str]]" = OrderedDict()


def _cache_pdf(file_path: str, download_name: str) -> str:
    token = uuid.uuid4().hex
    _pdf_cache[token] = (file_path, download_name)
    _pdf_cache.move_to_end(token)
    while len(_pdf_cache) > PDF_CACHE_MAX_SIZE:
        _, (old_path, _old_name) = _pdf_cache.popitem(last=False)
        try:
            os.remove(old_path)
        except OSError:
            pass
    return token


def get_weights():
    global _weights_cache
    if _weights_cache is None:
        _weights_cache = load_weights(WEIGHTS_PATH)
    return _weights_cache


@app.context_processor
def inject_ui_constants():
    """
    ثابت‌های نمایشی مشترک همه‌ی قالب‌ها — فقط خواندنی و از همان منبع‌های
    موجود (recommendations.py)، تا صفحه‌ی اصلی فهرست واقعی شاخص‌ها را
    نشان بدهد و آستانه‌های رسم‌شده روی نمودارها با get_status_level
    هم‌خوان بمانند (آستانه‌ی «ضعیف» همان 0.4 داخل get_status_level است).
    """
    return {
        "component_overview": [
            {
                "key": key,
                "label": COMPONENT_LABELS[key],
                "indicators": [
                    {"code": code, "label": INDICATOR_LABELS[code]} for code in codes
                ],
            }
            for key, codes in COMPONENT_INDICATOR_CODES.items()
        ],
        "thresholds": {"fail": 40, "pass": round(IMPROVEMENT_THRESHOLD * 100)},
    }


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



# نگاشت کلید فنی raw_details (که extractorها تولید می‌کنند) به برچسب
# فارسی قابل‌نمایش. عمداً در سطح ماژول است (نه محلی داخل تابع) تا
# tests/test_webapp.py بتواند آن را با کلیدهای واقعی extractorها
# مقایسه کند — رفع باگ: این دیکشنری قبلاً از فازهای بعدی پروژه عقب
# افتاده بود (حدود ۲۵ کلید جدید بدون برچسب فارسی اضافه شده بودند) و
# هیچ‌چیزی این عقب‌افتادگی را خودکار تشخیص نمی‌داد.
RAW_DETAILS_LABELS = {
    # عمومی/چندشاخصی
    "channels_found": "کانال‌های یافت‌شده",
    "details_found": "جزئیات یافت‌شده",
    "found_fields": "فیلدهای یافت‌شده",
    "found_types": "انواع یافت‌شده",
    "word_count": "تعداد کلمه",
    "min_required": "حداقل لازم",
    "matches": "تعداد تطابق",
    "tokenize_method": "روش توکنایز",
    # E1-E4 (Experience)
    "has_experience_phrase": "عبارت صریح تجربه دارد؟",
    "has_explicit_duration": "مدت‌زمان صریح تجربه ذکر شده؟",
    "review_count": "تعداد نظر (طبق داده ساختاریافته)",
    "qualified_images": "تعداد تصویر واجد شرایط",
    "total_images_in_content": "تعداد کل تصاویر محتوا",
    "text_signal": "نشانه متنی نظرات",
    "structural_signal": "نشانه ساختاری نظرات",
    "visible_signal_present": "نشانه بصری نظرات موجود است؟",
    "wp_comment_form_present": "فرم ثبت نظر وردپرسی دارد؟",
    # X1-X5 (Expertise)
    "has_bio": "بیوگرافی نویسنده دارد؟",
    "title_score": "امتیاز عنوان تخصصی",
    "author_area_text_length": "طول متن ناحیه نویسنده (کاراکتر)",
    "profile_links_found": "تعداد لینک پروفایل حرفه‌ای",
    "authoritative_count": "تعداد لینک به دامنه معتبر",
    "total_outbound_links": "تعداد کل لینک خروجی",
    "avg_sentence_length": "میانگین طول جمله (کلمه)",
    "structure_score": "امتیاز ساختار تیترها",
    "ttr_score": "امتیاز تنوع واژگانی (TTR)",
    "citation_context_count": "تعداد ارجاع معتبر با بافت متنی",
    # A1-A3 (Authoritativeness)
    "social_links_found": "تعداد لینک شبکه اجتماعی",
    "about_page_fetched": "صفحه درباره‌ما دانلود شد؟",
    # T1-T7 (Trustworthiness)
    "issuer": "صادرکننده گواهی SSL",
    "contact_page_fetched": "صفحه تماس دانلود شد؟",
    "whatsapp_link_detected": "لینک واتساپ پیدا شد؟",
    "tel_link_detected": "لینک تماس مستقیم (tel:) پیدا شد؟",
    "mailto_link_detected": "لینک ایمیل مستقیم (mailto:) پیدا شد؟",
    "linked_page_word_count": "تعداد کلمه صفحه لینک‌شده",
    "ad_elements": "تعداد عنصر تبلیغاتی",
    "ad_iframe_count": "تعداد iframe تبلیغاتی",
    "ad_network_scripts_detected": "اسکریپت‌های شبکه تبلیغاتی شناسایی‌شده",
    "total_blocks": "تعداد کل بلوک‌های صفحه",
    "source": "منبع تاریخ",
    "raw_date": "تاریخ خام یافت‌شده",
    "estimated_date": "تاریخ تخمینی (از Wayback Machine)",
    "days_since_update": "روز از آخرین به‌روزرسانی",
}

# کلیدهایی که عمداً برچسب نمی‌گیرند چون جدا/متفاوت نمایش داده می‌شوند
RAW_DETAILS_KEYS_HANDLED_SEPARATELY = {"reason", "note"}


def _format_evidence(raw_details: dict) -> str:
    """
    تبدیل دیکشنری raw_details هر شاخص به یک خط متن قابل‌فهم — برای
    نمایش شفاف «چرا این امتیاز داده شد» در گزارش، بدون نیاز به حدس زدن.
    """
    if not raw_details:
        return ""

    parts = []
    for key, value in raw_details.items():
        if key in RAW_DETAILS_KEYS_HANDLED_SEPARATELY:
            continue
        label = RAW_DETAILS_LABELS.get(key, key)
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


def _build_type_note(page_score) -> str | None:
    """
    توضیح کوتاه برای صفحه‌ی ویدیومحور یا محصول: کدام شاخص‌ها قضاوت نشدند (با نام
    فارسی، نه کد) و وزن مؤثر مؤلفه‌ها چقدر شد. برای صفحه‌ی معمولی None است.
    """
    ptype = getattr(page_score, "page_type", "standard")
    if ptype not in PAGE_TYPES:
        return None
    names = "، ".join(INDICATOR_LABELS.get(c, c) for c in page_score.type_info.get("excluded", {}))
    shares = "، ".join(
        f"{COMPONENT_LABELS.get(k, k)} {round(v * 100)}٪"
        for k, v in page_score.effective_weights.items()
    )
    info = PAGE_TYPES[ptype]
    return (f"صفحه‌ی {info['label']} تشخیص داده شد ({info['reason']}). "
            f"این شاخص‌ها قضاوت نشدند: {names}. وزن‌شان بین بقیه‌ی شاخص‌ها "
            f"به‌نسبت پخش شد؛ سهم مؤلفه‌ها در امتیاز نهایی: {shares}.")


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

    type_note = _build_type_note(page_score)
    return {
        "url": page_score.url,
        "display_url": make_display_url(page_score.url),
        "page_type": getattr(page_score, "page_type", "standard"),
        "type_note": type_note,
        "final_score_percent": round(page_score.final_score * 100),
        # سطح وضعیت امتیاز نهایی (با همان آستانه‌های شاخص‌ها) — فقط برای
        # نمایش؛ خودِ امتیازدهی دست‌نخورده است
        "final_status": get_status_level(page_score.final_score, missing=False, applicable=True),
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
    context["pdf_token"] = _generate_and_cache_pdf(context)
    return render_template("results.html", **context)


def _normalize_input_url(raw: str) -> str:
    """
    مثل /analyze: آدرس بدون http/https با https:// کامل می‌شود؛ با این
    تفاوت که اسکیم بدون حساسیت به حروف بزرگ/کوچک بررسی می‌شود (آدرس
    «HTTPS://...» نباید به «https://HTTPS://...» تبدیل شود).
    """
    url = (raw or "").strip()
    if url and not url.lower().startswith(("http://", "https://")):
        url = "https://" + url
    return url


def _compare_form_error(message: str, url_a: str = "", url_b: str = ""):
    """بازگشت به صفحه‌ی اصلی در حالت مقایسه، با حفظ هر دو آدرس واردشده."""
    return render_template(
        "index.html", error=message, mode="compare", url_a=url_a, url_b=url_b
    )


@app.route("/compare", methods=["POST"])
def compare():
    raw_a = request.form.get("url", "").strip()
    raw_b = request.form.get("url2", "").strip()
    url_a = _normalize_input_url(raw_a)
    url_b = _normalize_input_url(raw_b)

    if not url_a or not url_b:
        return _compare_form_error(
            "برای مقایسه باید هر دو آدرس را وارد کنید.", raw_a, raw_b
        )

    if normalize_url_for_compare(url_a) == normalize_url_for_compare(url_b):
        return _compare_form_error(
            "هشدار: هر دو آدرس یکسان‌اند و مقایسه‌ی یک صفحه با خودش معنایی ندارد. "
            "دو آدرس متفاوت وارد کنید.", raw_a, raw_b
        )

    # دو صفحه پشت‌سرهم (نه هم‌زمان): Playwright در صورت نیاز یک مرورگر
    # کامل باز می‌کند و اجرای هم‌زمان دو نمونه فشار و ریسک بیشتری دارد.
    scores = []
    for label, url in (("اول", url_a), ("دوم", url_b)):
        try:
            scores.append(process_single_url(url, get_weights(), weights_label="equal"))
        except FetchFailedError as e:
            return _compare_form_error(
                f"دانلود صفحه‌ی {label} ناموفق بود ({url}). جزئیات: {e.reason}",
                raw_a, raw_b,
            )
        except Exception as e:  # noqa: BLE001 — هر خطای پردازش باید پیام روشن بدهد
            return _compare_form_error(
                f"خطایی هنگام پردازش صفحه‌ی {label} رخ داد ({url}): {e}",
                raw_a, raw_b,
            )

    ctx_a = build_report_context(scores[0])
    ctx_b = build_report_context(scores[1])
    compare_ctx = build_comparison_context(ctx_a, ctx_b)
    compare_ctx["pdf_token"] = _generate_and_cache_comparison_pdf(compare_ctx)
    return render_template("compare.html", **compare_ctx)


def _render_and_cache_pdf(render, download_name: str) -> str | None:
    """
    هستهٔ مشترک ساخت و کش PDF (برای گزارش تک‌صفحه و گزارش مقایسه).
    render(path) باید فایل PDF را در path بنویسد. اگر هر چیزی شکست بخورد،
    خطا فقط لاگ می‌شود، فایل نیمه‌کاره پاک می‌شود و None برمی‌گردد.
    """
    tmp_path = None
    try:
        fd, tmp_path = tempfile.mkstemp(suffix=".pdf", prefix="eeat_report_")
        os.close(fd)
        render(tmp_path)
        return _cache_pdf(tmp_path, download_name)
    except Exception as e:  # noqa: BLE001 — عمداً گسترده: هیچ خطای ساخت PDF
        # نباید کل صفحه‌ی نتیجه را خراب کند
        print(f"[warn] ساخت PDF گزارش ناموفق بود: {e}")
        if tmp_path:
            try:
                os.remove(tmp_path)
            except OSError:
                pass
        return None


def _generate_and_cache_pdf(context: dict) -> str | None:
    """
    ساخت PDF گزارش برای همین context و برگرداندن توکن دانلودش.
    اگر ساخت PDF به هر دلیلی (مثلاً فونت پیدا نشود) شکست بخورد، گزارش
    وب همچنان باید نمایش داده شود — پس خطا فقط لاگ می‌شود و None
    برمی‌گردد (قالب results.html در این حالت دکمه‌ی دانلود را نشان
    نمی‌دهد، به‌جای این‌که کل صفحه با یک خطای ۵۰۰ از کار بیفتد).
    """
    domain = urlparse(context["url"]).netloc.replace(":", "_") or "report"
    return _render_and_cache_pdf(
        lambda path: generate_pdf_report(context, path),
        f"eeat-report-{domain}.pdf",
    )


def _generate_and_cache_comparison_pdf(compare_context: dict) -> str | None:
    """همان منطق _generate_and_cache_pdf برای PDF مقایسه (همان کش و همان سقف)."""
    def _domain(ctx):
        return urlparse(ctx["url"]).netloc.replace(":", "_") or "page"
    name = f"eeat-compare-{_domain(compare_context['a'])}-vs-{_domain(compare_context['b'])}.pdf"
    return _render_and_cache_pdf(
        lambda path: generate_comparison_pdf(compare_context, path), name
    )


def _send_cached_pdf(token: str):
    entry = _pdf_cache.get(token)
    if entry is None:
        abort(404, description="این لینک دانلود منقضی شده یا نامعتبر است. لطفاً صفحه را دوباره بررسی کنید.")
    file_path, download_name = entry
    if not os.path.isfile(file_path):
        abort(404, description="فایل گزارش دیگر در دسترس نیست. لطفاً صفحه را دوباره بررسی کنید.")
    return send_file(file_path, mimetype="application/pdf",
                     as_attachment=True, download_name=download_name)


@app.route("/download-pdf/<token>", methods=["GET"])
def download_pdf(token):
    return _send_cached_pdf(token)


@app.route("/download-compare-pdf/<token>", methods=["GET"])
def download_compare_pdf(token):
    return _send_cached_pdf(token)


if __name__ == "__main__":
    app.run(debug=False, use_reloader=False, host="0.0.0.0", port=5000)
