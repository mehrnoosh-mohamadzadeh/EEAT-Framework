# -*- coding: utf-8 -*-
"""
منطق «مقایسه‌ی دو صفحه» — بدون هیچ وابستگی به Flask، شبکه یا PDF.

چرا در یک ماژول جدا: تعیین برنده باید یک تابع خالص باشد (ورودی ->
خروجی، بدون اثر جانبی) تا مستقیم و سریع تست واحد شود. ورودی این
ماژول همان دیکشنری‌هایی است که webapp.app.build_report_context برای هر
صفحه می‌سازد؛ یعنی هیچ منطق استخراج یا امتیازدهی این‌جا کپی نشده.

قاعده‌ی برنده (تصمیم طراحی، نه ادعای علمی):
- مقایسه روی «درصد گردشده‌ی نمایش‌داده‌شده» انجام می‌شود، نه روی عدد خام؛
  تا کاربر هیچ‌وقت «۷۲٪ در برابر ۷۲٪ با برنده» نبیند.
- اگر درصدها برابر باشند: «مساوی» (برنده ندارد).
- اگر یکی از دو طرف «داده کافی نیست» (missing) یا «غیرقابل‌اعمال»
  (not_applicable) باشد، یا مقدارش None باشد: مقایسه‌ی عادلانه ممکن
  نیست، پس «بدون قضاوت» (none) و هیچ برنده‌ای اعلام نمی‌شود.
- هیچ آستانه‌ی «اختلاف معنی‌دار» ساخته نشده؛ چون منبع علمی برای آن
  نداریم. به‌جایش در رابط و گزارش صریحاً نوشته می‌شود که اختلاف
  امتیاز معنی آماری ندارد (STATISTICAL_DISCLAIMER).
"""

# نتیجه‌ی مقایسه‌ی یک ردیف
WINNER_A = "a"
WINNER_B = "b"
TIE = "tie"
NONE = "none"  # مقایسه ممکن نیست (یک طرف missing/not_applicable/None)

_NOT_COMPARABLE_STATUSES = ("missing", "not_applicable")

STATISTICAL_DISCLAIMER = (
    "توجه: اختلاف امتیاز بین دو صفحه معنی آماری ندارد؛ فقط تفاوت "
    "شاخص‌هایی را نشان می‌دهد که همین ابزار اندازه می‌گیرد، نه تفاوت "
    "اثبات‌شده‌ی کیفیت یا رتبه‌ی واقعی دو صفحه."
)


def decide_winner(percent_a, percent_b, status_a="pass", status_b="pass") -> dict:
    """
    تعیین برنده‌ی یک ردیف (یک شاخص، یک مؤلفه یا امتیاز نهایی).

    ورودی: درصد (عدد صحیح یا None) و وضعیت هر طرف.
    خروجی: {"result": "a"|"b"|"tie"|"none", "diff": int|None}
    diff = درصد طرف اول منهای درصد طرف دوم (علامت‌دار)؛ فقط وقتی
    مقایسه ممکن است، وگرنه None.
    """
    if (status_a in _NOT_COMPARABLE_STATUSES or status_b in _NOT_COMPARABLE_STATUSES
            or percent_a is None or percent_b is None):
        return {"result": NONE, "diff": None}

    diff = percent_a - percent_b
    if diff > 0:
        return {"result": WINNER_A, "diff": diff}
    if diff < 0:
        return {"result": WINNER_B, "diff": diff}
    return {"result": TIE, "diff": 0}


def normalize_url_for_compare(url: str) -> str:
    """
    شکل استاندارد یک URL فقط برای تشخیص «دو آدرس یکسان»:
    حروف کوچک، بدون اسلش انتهایی و بدون fragment. (آدرس واقعی برای
    تحلیل دست‌نخورده می‌ماند.)
    """
    from urllib.parse import urlparse

    parsed = urlparse((url or "").strip())
    host = (parsed.netloc or "").lower()
    path = parsed.path.rstrip("/")
    query = f"?{parsed.query}" if parsed.query else ""
    return f"{parsed.scheme.lower()}://{host}{path}{query}"


def _side(item: dict, percent_key: str) -> dict:
    return {"percent": item.get(percent_key), "status": item.get("status")}


def build_comparison_context(ctx_a: dict, ctx_b: dict) -> dict:
    """
    ساخت ساختار قابل‌نمایش مقایسه از دو context هم‌شکل با
    build_report_context.

    خروجی:
    {
      "a": ctx_a, "b": ctx_b,
      "final": {"a": درصد, "b": درصد, "result": ..., "diff": ...},
      "components": [{key, label, a:{percent,status}, b:{...}, result, diff,
                      indicators: [{code, label, a:{percent,status,evidence},
                                    b:{...}, result, diff}]}],
      "tally": {"a": n, "b": n, "tie": n, "none": n},   # فقط روی ۱۹ شاخص
      "disclaimer": STATISTICAL_DISCLAIMER,
    }
    ترتیب و برچسب مؤلفه‌ها/شاخص‌ها از ctx_a گرفته می‌شود؛ شاخص طرف دوم
    با کد (code) پیدا می‌شود، نه با موقعیت — تا اگر ترتیب فرق کرد
    مقایسه جابه‌جا نشود.
    """
    # دو صفحه با «نوع» متفاوت (یکی ویدیومحور، یکی معمولی) مجموعه‌ی شاخص‌های
    # قضاوت‌شده‌ی متفاوتی دارند؛ مقایسه‌ی امتیاز نهایی و مؤلفه‌ها بین‌شان
    # عادلانه نیست، پس برنده‌ای اعلام نمی‌شود (شاخص‌ها جداگانه مقایسه می‌شوند).
    mixed_types = ctx_a.get("page_type", "standard") != ctx_b.get("page_type", "standard")
    comps_b = {c["key"]: c for c in ctx_b["components"]}
    tally = {WINNER_A: 0, WINNER_B: 0, TIE: 0, NONE: 0}

    components = []
    for comp_a in ctx_a["components"]:
        comp_b = comps_b.get(comp_a["key"])
        if comp_b is None:
            comp_b = {"score_percent": None, "status": "missing", "indicators": []}
        inds_b = {i["code"]: i for i in comp_b["indicators"]}

        indicators = []
        for ind_a in comp_a["indicators"]:
            ind_b = inds_b.get(ind_a["code"]) or {
                "value_percent": None, "status": "missing", "evidence": "",
            }
            verdict = decide_winner(
                ind_a.get("value_percent"), ind_b.get("value_percent"),
                ind_a.get("status"), ind_b.get("status"),
            )
            tally[verdict["result"]] += 1
            indicators.append({
                "code": ind_a["code"],
                "label": ind_a["label"],
                "a": {**_side(ind_a, "value_percent"), "evidence": ind_a.get("evidence", "")},
                "b": {**_side(ind_b, "value_percent"), "evidence": ind_b.get("evidence", "")},
                **verdict,
            })

        comp_verdict = decide_winner(
            None if mixed_types else comp_a.get("score_percent"),
            None if mixed_types else comp_b.get("score_percent"),
            comp_a.get("status"), comp_b.get("status"),
        )
        components.append({
            "key": comp_a["key"],
            "label": comp_a["label"],
            "a": _side(comp_a, "score_percent"),
            "b": _side(comp_b, "score_percent"),
            **comp_verdict,
            "indicators": indicators,
        })

    # امتیاز نهایی همیشه عدد دارد (final_score در PageScore اجباری است)
    final_verdict = decide_winner(
        None if mixed_types else ctx_a.get("final_score_percent"),
        None if mixed_types else ctx_b.get("final_score_percent"),
    )

    type_notes = []
    for label, ctx in (("صفحه‌ی اول", ctx_a), ("صفحه‌ی دوم", ctx_b)):
        if ctx.get("type_note"):
            type_notes.append(f"{label}: {ctx['type_note']}")
    if mixed_types:
        type_notes.append(
            "نوع دو صفحه فرق دارد (مثلاً یکی ویدیومحور یا محصول است)، پس مجموعه‌ی شاخص‌های قضاوت‌شده‌شان "
            "یکی نیست و برای امتیاز نهایی و مؤلفه‌ها برنده‌ای اعلام نمی‌شود؛ فقط شاخص‌هایی "
            "که برای هر دو صفحه قضاوت شده‌اند مقایسه می‌شوند."
        )

    return {
        "a": ctx_a,
        "b": ctx_b,
        "final": {
            "a": ctx_a.get("final_score_percent"),
            "b": ctx_b.get("final_score_percent"),
            **final_verdict,
        },
        "components": components,
        "tally": tally,
        "disclaimer": STATISTICAL_DISCLAIMER,
        "type_notes": type_notes,
        "mixed_types": mixed_types,
    }
