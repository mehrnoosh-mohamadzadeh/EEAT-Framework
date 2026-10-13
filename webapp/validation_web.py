# -*- coding: utf-8 -*-
"""
صفحه‌ی «اعتبارسنجی با داور انسانی» در وب‌اپ.

سه کار، همه روی فایل جدولی (CSV):
  ۱. ساخت برگه‌ی نمره‌دهی کور از فایل نتایج ابزار (بدون نمره‌ی ابزار)؛
  ۲. بارگذاری نتایج ابزار + برگه‌ی پرشده و نمایش اسپیرمن، فاصله‌ی اطمینان، نمودار؛
  ۳. متن پیش‌نویس فصل نتایج.
منطق آماری در scoring/validation.py است؛ این‌جا فقط مسیرها و نمایش.
"""

from flask import Blueprint, Response, render_template, request

from scoring.validation import (
    ValidationInputError, build_blank_rating_sheet, build_blank_rating_xlsx,
    decode_csv_bytes,
    thesis_paragraph, validate_uploaded,
)

validation_bp = Blueprint("validation", __name__)

MAX_UPLOAD_BYTES = 1_000_000  # ۱ مگابایت برای هر فایل

COMPONENT_ROWS = [
    ("experience", "تجربه"), ("expertise", "تخصص"),
    ("authority", "اقتدار"), ("trust", "اعتماد"), ("overall", "امتیاز نهایی"),
]


def _read_upload(field: str, label: str) -> str:
    f = request.files.get(field)
    if f is None or not f.filename:
        raise ValidationInputError(f"فایل {label} انتخاب نشده است.")
    raw = f.read(MAX_UPLOAD_BYTES + 1)
    if len(raw) > MAX_UPLOAD_BYTES:
        raise ValidationInputError(f"فایل {label} بزرگ‌تر از ۱ مگابایت است.")
    return decode_csv_bytes(raw)


@validation_bp.route("/validation", methods=["GET"])
def validation_page():
    return render_template("validation.html", rows=COMPONENT_ROWS)


@validation_bp.route("/validation/sheet", methods=["POST"])
def blank_sheet():
    fmt = request.form.get("fmt", "xlsx")
    try:
        text = _read_upload("framework_csv", "نتایج ابزار")
        if fmt == "csv":
            sheet = build_blank_rating_sheet(text)
        else:
            xlsx = build_blank_rating_xlsx(text)
    except ValidationInputError as e:
        return render_template("validation.html", rows=COMPONENT_ROWS, error=str(e)), 400
    if fmt == "csv":
        # BOM تا اکسل فارسی را درست باز کند
        return Response("\ufeff" + sheet, mimetype="text/csv; charset=utf-8",
                        headers={"Content-Disposition": "attachment; filename=human_ratings_blank.csv"})
    return Response(
        xlsx,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=human_ratings_blank.xlsx"})


@validation_bp.route("/validation/analyze", methods=["POST"])
def analyze_validation():
    try:
        fw = _read_upload("framework_csv", "نتایج ابزار")
        hu = _read_upload("human_csv", "نمره‌ی داور")
        report = validate_uploaded(fw, hu)
    except ValidationInputError as e:
        return render_template("validation.html", rows=COMPONENT_ROWS, error=str(e)), 400
    return render_template("validation.html", rows=COMPONENT_ROWS, report=report,
                           paragraph=thesis_paragraph(report))
