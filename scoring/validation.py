# -*- coding: utf-8 -*-
"""
ماژول Validation — فاز ۶ (اعتبارسنجی تجربی چارچوب، مورد ۱۲).

کار این ماژول: ترکیب خروجی CSV چارچوب (از reporting/reporter.py) با
نمره‌های انسانی (از data/human_ratings_template.csv پرشده) بر اساس
url، و محاسبه‌ی همبستگی اسپیرمن بین امتیاز ابزار و قضاوت انسانی —
برای هر مؤلفه جداگانه و برای امتیاز نهایی.

⚠️ محدودیت مهم و صادقانه: این تحلیل با فرض «یک داور انسانی» نوشته
شده (نه ۲-۳ داور مستقل که در طرح اولیه پیشنهاد شده بود). به همین
دلیل این ماژول **توافق بین‌داوری (inter-rater agreement / Cohen's
kappa)** را محاسبه نمی‌کند — چون با یک داور، اصلاً همچین مفهومی
تعریف‌شده نیست. اگر در آینده داور دوم/سوم اضافه شد، محاسبه‌ی
Cohen's kappa یا Krippendorff's alpha باید جداگانه اضافه شود؛ فعلاً
عمداً این‌جا نیست تا ادعای اشتباهی درباره‌ی «اعتبارسنجی چند‌داوره»
القا نشود.

مرجع آماری: scipy.stats.spearmanr (🟢 پیاده‌سازی استاندارد و
مستندشده‌ی همبستگی رتبه‌ای اسپیرمن؛ قبلاً هم در requirements.txt این
پروژه بود).
"""

import csv

from scipy.stats import spearmanr


def load_framework_scores(csv_path: str) -> dict:
    """
    خواندن خروجی reporting.export_to_csv و برگرداندن دیکشنری
    {url: {"experience": float|None, "expertise": ..., "authority": ...,
           "trust": ..., "final": ...}}.
    """
    scores = {}
    with open(csv_path, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            url = row["url"]
            scores[url] = {
                "experience": _to_float_or_none(row.get("experience_score")),
                "expertise": _to_float_or_none(row.get("expertise_score")),
                "authority": _to_float_or_none(row.get("authority_score")),
                "trust": _to_float_or_none(row.get("trust_score")),
                "final": _to_float_or_none(row.get("final_score")),
            }
    return scores


def load_human_ratings(csv_path: str) -> dict:
    """
    خواندن data/human_ratings_template.csv پرشده و برگرداندن دیکشنری
    {url: {"experience": int, "expertise": int, "authority": int, "trust": int}}.
    """
    ratings = {}
    with open(csv_path, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            url = row["url"]
            ratings[url] = {
                "experience": _to_float_or_none(row.get("human_experience")),
                "expertise": _to_float_or_none(row.get("human_expertise")),
                "authority": _to_float_or_none(row.get("human_authority")),
                "trust": _to_float_or_none(row.get("human_trust")),
            }
    return ratings


def _to_float_or_none(value):
    if value is None or value == "":
        return None
    try:
        return float(value)
    except ValueError:
        return None


def compute_spearman_per_component(framework_csv_path: str, human_ratings_csv_path: str) -> dict:
    """
    محاسبه‌ی همبستگی اسپیرمن بین امتیاز چارچوب و نمره‌ی انسانی، برای
    هر ۴ مؤلفه به‌طور جداگانه، بعلاوه یک ترکیب کلی (میانگین ۴ مؤلفه
    انسانی در برابر امتیاز نهایی چارچوب).

    فقط صفحاتی که هم در خروجی چارچوب هم در نمره‌های انسانی، مقدار
    معتبر (نه None) دارند وارد محاسبه می‌شوند. اگر داده‌ی کافی
    (حداقل ۳ جفت) نبود، برای آن مؤلفه None برمی‌گرداند (نه خطا) —
    چون همبستگی روی نمونه‌ی خیلی کوچک بی‌معنی/گمراه‌کننده است.

    خروجی: {"experience": {"rho": float, "p_value": float, "n": int} یا None, ...}
    """
    framework_scores = load_framework_scores(framework_csv_path)
    human_ratings = load_human_ratings(human_ratings_csv_path)

    common_urls = set(framework_scores.keys()) & set(human_ratings.keys())

    results = {}
    for component in ["experience", "expertise", "authority", "trust"]:
        framework_values = []
        human_values = []
        for url in common_urls:
            f_val = framework_scores[url].get(component)
            h_val = human_ratings[url].get(component)
            if f_val is not None and h_val is not None:
                framework_values.append(f_val)
                human_values.append(h_val)

        results[component] = _spearman_or_none(framework_values, human_values)

    # ترکیب کلی: میانگین ۴ نمره‌ی انسانی در برابر امتیاز نهایی چارچوب
    final_framework_values = []
    overall_human_values = []
    for url in common_urls:
        f_final = framework_scores[url].get("final")
        h_components = [human_ratings[url].get(c) for c in
                         ["experience", "expertise", "authority", "trust"]]
        if f_final is not None and all(v is not None for v in h_components):
            final_framework_values.append(f_final)
            overall_human_values.append(sum(h_components) / len(h_components))

    results["overall"] = _spearman_or_none(final_framework_values, overall_human_values)
    return results


def _spearman_or_none(x_values: list, y_values: list, min_pairs: int = 3):
    if len(x_values) < min_pairs or len(y_values) < min_pairs:
        return None
    rho, p_value = spearmanr(x_values, y_values)
    return {"rho": rho, "p_value": p_value, "n": len(x_values)}


def print_validation_report(results: dict) -> None:
    """چاپ خوانا از خروجی compute_spearman_per_component."""
    component_labels = {
        "experience": "Experience",
        "expertise": "Expertise",
        "authority": "Authoritativeness",
        "trust": "Trustworthiness",
        "overall": "امتیاز نهایی (میانگین انسانی در برابر final_score)",
    }
    print("=== گزارش اعتبارسنجی: همبستگی اسپیرمن (ابزار در برابر داور انسانی) ===")
    print("⚠️ این نتایج فقط بر پایه‌ی یک داور انسانی است — نه چند داور مستقل.")
    print()
    for component, label in component_labels.items():
        result = results.get(component)
        if result is None:
            print(f"{label}: داده‌ی کافی نبود (حداقل ۳ صفحه‌ی مشترک با نمره‌ی معتبر لازم است)")
        else:
            print(f"{label}: rho={result['rho']:.3f}, p={result['p_value']:.4f}, n={result['n']}")
