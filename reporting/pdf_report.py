# -*- coding: utf-8 -*-
"""
تولید گزارش PDF از نتیجه‌ی تحلیل E-E-A-T (یک صفحه، یا مقایسه‌ی دو صفحه).

چرا به این شکل نوشته شده (برای نگهداری آینده):
- ورودی گزارش تک‌صفحه همان دیکشنری خروجی webapp.app.build_report_context و
  ورودی گزارش مقایسه خروجی webapp.comparison.build_comparison_context است —
  یعنی PDF از همان داده‌ای ساخته می‌شود که صفحه‌ی نتیجه‌ی وب از آن ساخته
  می‌شود (همان برچسب‌ها، همان متن «چرا این نمره» و همان توصیه‌ی بهبود از
  webapp/recommendations.py). این ماژول هیچ امتیاز، وزن یا وضعیتی نمی‌سازد
  و محاسبه نمی‌کند؛ فقط نمایش می‌دهد.
- ترتیب گزارش همان ترتیب صفحه‌ی نتیجه‌ی وب است: عنوان و مشخصات صفحه ←
  امتیاز نهایی ← چهار مؤلفه ← جزئیات شاخص‌ها ← معنی وضعیت‌ها.
- ظاهر (پالت، کدگذاری وضعیت با شکل و واژه، آستانه‌های ۴۰ و ۶۰ روی نوارها)
  همان رابط وب است (webapp/static/style.css).
- فارسی در PDF با reportlab مستقیم درست نمایش داده نمی‌شود: حروف باید
  به فرم اتصالی تبدیل شوند (arabic_reshaper) و ترتیب راست‌به‌چپ بگیرند
  (python-bidi). چون Paragraph داخلی reportlab این دو مرحله را در حین
  شکستن خط به‌درستی انجام نمی‌دهد، متن را خودمان بر پایه‌ی عرض واقعی
  (قبل از reshape) به خط می‌شکنیم و هر خط را جداگانه reshape/bidi می‌کنیم —
  تکنیک استاندارد RTL با reportlab.
- فونت Vazirmatn از webapp/static/fonts/ (مجوز SIL OFL، فایل
  VAZIRMATN-OFL-LICENSE.txt کنار آن).
"""

import os
import re
from datetime import datetime

import arabic_reshaper
from bidi.algorithm import get_display
from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

from webapp.recommendations import IMPROVEMENT_THRESHOLD, IMPROVEMENT_TIPS

# ---------------------------------------------------------------------------
# فونت
# ---------------------------------------------------------------------------

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_FONT_DIR = os.path.join(_PROJECT_ROOT, "webapp", "static", "fonts")
FONT_REGULAR = "Vazirmatn"
FONT_BOLD = "Vazirmatn-Bold"
_fonts_registered = False


def _ensure_fonts_registered():
    """
    ثبت فونت فارسی در reportlab — فقط یک‌بار در کل عمر فرآیند لازم است.
    اگر فایل فونت پیدا نشود، یک خطای روشن می‌دهد به‌جای این‌که فارسی را با
    فونت پیش‌فرض (که فارسی ندارد) بی‌صدا خراب رندر کند.
    """
    global _fonts_registered
    if _fonts_registered:
        return
    regular_path = os.path.join(_FONT_DIR, "Vazirmatn-Regular.ttf")
    bold_path = os.path.join(_FONT_DIR, "Vazirmatn-Bold.ttf")
    if not os.path.isfile(regular_path) or not os.path.isfile(bold_path):
        raise FileNotFoundError(
            "فونت Vazirmatn پیدا نشد. فایل‌های Vazirmatn-Regular.ttf و "
            "Vazirmatn-Bold.ttf باید در webapp/static/fonts/ باشند — "
            "بدون این‌ها متن فارسی در PDF به‌درستی نمایش داده نمی‌شود."
        )
    pdfmetrics.registerFont(TTFont(FONT_REGULAR, regular_path))
    pdfmetrics.registerFont(TTFont(FONT_BOLD, bold_path))
    _fonts_registered = True


def rtl(text) -> str:
    """
    آماده‌سازی یک رشته‌ی فارسی برای رسم صحیح: اتصال حروف + ترتیب راست‌به‌چپ.
    جهت پایه عمداً راست‌به‌چپ است تا خطی که با یک واژه‌ی انگلیسی یا عدد شروع
    می‌شود هم مثل بقیه‌ی خط‌ها راست‌چین بماند.
    """
    if text is None:
        return ""
    text = str(text)
    if not text:
        return ""
    # عبارت لاتین داخل پرانتز (مثل «(TTR)») باید پرانتزهایش را در همان خط
    # چپ‌به‌راست نگه دارد؛ نشانه‌ی نامرئی LRM فقط برای ترتیب‌دهی است و بعد حذف می‌شود.
    text = re.sub(r"\(([A-Za-z0-9_. \-]+)\)", "\u200e(\\1)\u200e", text)
    shaped = get_display(arabic_reshaper.reshape(text), base_dir="R")
    return shaped.replace("\u200e", "")


def _wrap_to_width(text: str, font: str, size: float, max_width: float) -> list:
    """
    شکستن متن به خط‌هایی که هرکدام در max_width جا می‌شوند.
    روی متن خام (قبل از reshape) اندازه‌گیری می‌شود — عرض فرم‌های
    اتصالی قابل‌مقایسه با فرم‌های جدا است، پس این تقریب برای تصمیم
    «کجا خط را بشکنیم» کافی و قابل‌اتکاست.
    """
    words = str(text).split()
    if not words:
        return [""]
    lines, current = [], []
    for word in words:
        trial = " ".join(current + [word])
        if not current or pdfmetrics.stringWidth(trial, font, size) <= max_width:
            current.append(word)
        else:
            lines.append(" ".join(current))
            current = [word]
    if current:
        lines.append(" ".join(current))
    return lines


def _wrap_chars(text: str, font: str, size: float, max_width: float) -> list:
    """شکستن رشته‌ی چپ‌به‌راست بلند بدون فاصله (مثل آدرس اینترنتی) بر پایه‌ی نویسه."""
    lines, current = [], ""
    for ch in str(text):
        if current and pdfmetrics.stringWidth(current + ch, font, size) > max_width:
            lines.append(current)
            current = ch
        else:
            current += ch
    if current:
        lines.append(current)
    return lines or [""]


# ---------------------------------------------------------------------------
# رنگ‌ها — دقیقاً پالت رابط وب (webapp/static/style.css)
# ---------------------------------------------------------------------------

COLOR_PAPER = HexColor("#F5F2EB")      # پس‌زمینه‌ی صفحه
COLOR_SURFACE = HexColor("#FFFFFF")    # بخش محتوایی
COLOR_INK = HexColor("#29352F")        # متن اصلی
COLOR_PRIMARY = HexColor("#34443D")    # تیترها و تأکید اصلی
COLOR_SECONDARY = HexColor("#718477")  # نوارها و عناصر ثانویه
COLOR_ACCENT = HexColor("#B77953")     # تأکید محدود
COLOR_RULE = HexColor("#DCDDD5")       # خطوط جداکننده
# سه رنگ مشتق‌شده (همان‌هایی که وب برای خوانایی متن کوچک دارد)
COLOR_INK_SOFT = HexColor("#4B5951")
COLOR_ACCENT_INK = HexColor("#8A5232")
COLOR_FAIL = HexColor("#8F3B2E")

# واژه‌های وضعیت — همان واژه‌های رابط وب (_ui.html)
STATUS_LABELS_FA = {
    "pass": "وضعیت خوب",
    "warn": "نیاز به بهبود",
    "fail": "ضعیف",
    "missing": "داده ناموجود",
    "not_applicable": "غیرقابل اعمال",
}
STATUS_WORD_COLORS = {
    "pass": COLOR_INK_SOFT,
    "warn": COLOR_ACCENT_INK,
    "fail": COLOR_FAIL,
    "missing": COLOR_INK_SOFT,
    "not_applicable": COLOR_INK_SOFT,
}
STATUS_WORD_BOLD = {"warn", "fail"}

# آستانه‌هایی که روی نوارها کشیده می‌شوند (همان منبع وب: get_status_level)
THRESHOLD_FAIL = 40
THRESHOLD_PASS = round(IMPROVEMENT_THRESHOLD * 100)

PAGE_W, PAGE_H = A4
MARGIN = 50
CONTENT_W = PAGE_W - 2 * MARGIN
RIGHT = PAGE_W - MARGIN   # لبه‌ی راست محتوا (راست‌چین‌ایم)
LEFT = MARGIN
TOP = 54
BOTTOM = 62               # پایین‌ترین جای مجاز برای محتوا (بالای پانویس)

LEGEND = [
    ("fail", "امتیاز صفر", "شاخص سنجیده شد و هیچ نشانه‌ای پیدا نشد."),
    ("missing", "داده ناموجود", "داده‌ی کافی برای سنجش نبود؛ در میانگین نمی‌آید."),
    ("not_applicable", "غیرقابل اعمال",
     "این شاخص برای این نوع صفحه معنا ندارد؛ آن هم در میانگین نمی‌آید."),
]


def status_word(status: str, percent) -> str:
    """واژه‌ی وضعیت؛ «ضعیفِ صفر» به‌جای «ضعیف» می‌شود «امتیاز صفر» (مثل وب)."""
    if status == "fail" and percent == 0:
        return "امتیاز صفر"
    return STATUS_LABELS_FA.get(status, "")


def _pct_text(percent) -> str:
    return f"{percent}٪" if percent is not None else "—"


# ---------------------------------------------------------------------------
# بوم و ابزارهای رسم
# ---------------------------------------------------------------------------

class _Doc:
    """
    بوم reportlab به‌همراه موقعیت عمودی جاری (y) و شکست خودکار صفحه.
    هر صفحه کاغذیِ #F5F2EB است و پانویس (نام ابزار، تاریخ، شماره‌ی صفحه) دارد.
    """

    def __init__(self, path, title, generated_at):
        _ensure_fonts_registered()
        self.c = canvas.Canvas(path, pagesize=A4)
        self.c.setTitle(title)
        self.c.setAuthor("EEAT-Framework")
        self.title = title
        self.generated_at = generated_at
        self.page_num = 1
        self._start_page()

    def _start_page(self):
        c = self.c
        c.setFillColor(COLOR_PAPER)
        c.rect(0, 0, PAGE_W, PAGE_H, stroke=0, fill=1)
        if self.page_num > 1:
            # نوار باریک بالای صفحه‌های بعدی (صفحه‌ی اول جلد بزرگ دارد)
            c.setFillColor(COLOR_PRIMARY)
            c.rect(0, PAGE_H - 26, PAGE_W, 26, stroke=0, fill=1)
            c.setFillColor(COLOR_ACCENT)
            c.rect(0, PAGE_H - 28, PAGE_W, 2, stroke=0, fill=1)
            c.setFont(FONT_BOLD, 9)
            c.setFillColor(COLOR_PAPER)
            c.drawRightString(RIGHT, PAGE_H - 17, rtl(self.title))
            c.setFont(FONT_REGULAR, 8.5)
            c.setFillColor(COLOR_RULE)
            c.drawString(LEFT, PAGE_H - 17, rtl(self.generated_at))
        c.setStrokeColor(COLOR_RULE)
        c.setLineWidth(0.6)
        c.line(MARGIN, 44, RIGHT, 44)
        c.setFont(FONT_REGULAR, 8.5)
        c.setFillColor(COLOR_INK_SOFT)
        c.drawRightString(RIGHT, 30, rtl("ابزار ارزیابی E-E-A-T"))
        c.drawString(LEFT, 30, rtl(f"صفحه {self.page_num}"))
        self.y = PAGE_H - (TOP if self.page_num == 1 else 62)

    def new_page(self):
        self.c.showPage()
        self.page_num += 1
        self._start_page()

    def remaining(self):
        return self.y - BOTTOM

    def ensure(self, height):
        """اگر ارتفاع باقی‌مانده کافی نیست، صفحه‌ی جدید باز می‌کند."""
        if self.y - height < BOTTOM:
            self.new_page()

    def space(self, h):
        self.y -= h

    # --- ابزارهای متن -------------------------------------------------
    def text(self, s, xr, y, font=FONT_REGULAR, size=10, color=COLOR_INK):
        """متن فارسی با لبه‌ی راست در xr."""
        self.c.setFont(font, size)
        self.c.setFillColor(color)
        self.c.drawRightString(xr, y, rtl(s))

    def text_left(self, s, xl, y, font=FONT_REGULAR, size=10, color=COLOR_INK):
        """متن فارسی با لبه‌ی چپ در xl."""
        self.c.setFont(font, size)
        self.c.setFillColor(color)
        self.c.drawString(xl, y, rtl(s))

    def text_center(self, s, xc, y, font=FONT_REGULAR, size=10, color=COLOR_INK):
        self.c.setFont(font, size)
        self.c.setFillColor(color)
        self.c.drawCentredString(xc, y, rtl(s))

    def raw_right(self, s, xr, y, font=FONT_REGULAR, size=10, color=COLOR_INK):
        """متن چپ‌به‌راست (آدرس، کد، عدد) بدون bidi، با لبه‌ی راست در xr."""
        self.c.setFont(font, size)
        self.c.setFillColor(color)
        self.c.drawRightString(xr, y, str(s))

    def raw_left(self, s, xl, y, font=FONT_REGULAR, size=10, color=COLOR_INK):
        self.c.setFont(font, size)
        self.c.setFillColor(color)
        self.c.drawString(xl, y, str(s))

    def paragraph(self, s, xr, width, y, font=FONT_REGULAR, size=9.5,
                  color=COLOR_INK, leading=None):
        """پاراگراف راست‌چین از y به پایین (y خط مبنای اولین خط)؛ تعداد خط را برمی‌گرداند."""
        leading = leading or size * 1.6
        lines = _wrap_to_width(s, font, size, width)
        self.c.setFont(font, size)
        self.c.setFillColor(color)
        for i, line in enumerate(lines):
            self.c.drawRightString(xr, y - i * leading, rtl(line))
        return len(lines)

    # --- خط‌ها و قاب‌ها -----------------------------------------------
    def hline(self, y, x1=LEFT, x2=RIGHT, color=COLOR_RULE, width=0.6):
        self.c.setStrokeColor(color)
        self.c.setLineWidth(width)
        self.c.line(x1, y, x2, y)

    def panel(self, top, height):
        """تنها قاب سفید گزارش: زمینه‌ی سفید با حاشیه‌ی نازک، بدون سایه."""
        self.c.setFillColor(COLOR_SURFACE)
        self.c.setStrokeColor(COLOR_RULE)
        self.c.setLineWidth(0.6)
        self.c.roundRect(LEFT, top - height, CONTENT_W, height, 3, stroke=1, fill=1)


def _draw_mark(doc: _Doc, status: str, cx: float, cy: float, r: float = 4.6):
    """نشانه‌ی وضعیت با شکل (نه فقط رنگ): پر، نیم‌پر، حلقه، حلقه‌ی خط‌چین، خط کوتاه."""
    c = doc.c
    c.saveState()
    if status == "pass":
        c.setFillColor(COLOR_PRIMARY)
        c.circle(cx, cy, r + 0.6, stroke=0, fill=1)
    elif status == "warn":
        c.setStrokeColor(COLOR_ACCENT)
        c.setLineWidth(1.1)
        c.circle(cx, cy, r, stroke=1, fill=0)
        c.setFillColor(COLOR_ACCENT)
        c.wedge(cx - r, cy - r, cx + r, cy + r, 90, 180, stroke=0, fill=1)
    elif status == "fail":
        c.setStrokeColor(COLOR_FAIL)
        c.setLineWidth(1.6)
        c.circle(cx, cy, r, stroke=1, fill=0)
    elif status == "missing":
        c.setStrokeColor(COLOR_SECONDARY)
        c.setLineWidth(1.1)
        c.setDash(1.5, 1.4)
        c.circle(cx, cy, r, stroke=1, fill=0)
    else:  # not_applicable
        c.setStrokeColor(COLOR_SECONDARY)
        c.setLineWidth(1.5)
        c.setLineCap(1)
        c.line(cx - r + 0.8, cy, cx + r - 0.8, cy)
    c.restoreState()


def _draw_track(doc: _Doc, xl: float, xr: float, yc: float, percent, status: str,
                h: float = 7.5, strong: bool = False):
    """
    نوار ۰ تا ۱۰۰ مثل وب: پر شدن از راست، نشانه‌ی آستانه‌های ۴۰ و ۶۰.
    «امتیاز صفر» نوار خالیِ دارای آستانه است؛ «ناموجود» خط‌چین و
    «غیرقابل اعمال» خط نازک است و آستانه ندارند.
    """
    c = doc.c
    w = xr - xl
    c.saveState()
    if status == "missing" or percent is None and status != "not_applicable":
        c.setStrokeColor(COLOR_SECONDARY)
        c.setLineWidth(1)
        c.setDash(2.2, 2)
        c.line(xl, yc, xr, yc)
    elif status == "not_applicable":
        c.setStrokeColor(COLOR_RULE)
        c.setLineWidth(1)
        c.line(xl, yc, xr, yc)
    else:
        c.setFillColor(COLOR_RULE)
        c.rect(xl, yc - h / 2, w, h, stroke=0, fill=1)
        fill_w = w * max(0, min(100, percent)) / 100.0
        if fill_w > 0:
            c.setFillColor(COLOR_PRIMARY if strong else COLOR_SECONDARY)
            c.rect(xr - fill_w, yc - h / 2, fill_w, h, stroke=0, fill=1)
        c.setStrokeColor(COLOR_INK)
        c.setLineWidth(0.8)
        for t in (THRESHOLD_FAIL, THRESHOLD_PASS):
            x = xr - w * t / 100.0
            c.line(x, yc - h / 2 - 1.5, x, yc + h / 2 + 1.5)
    c.restoreState()


def _draw_gauge(doc: _Doc, cx: float, base_y: float, percent: int, radius: float = 62):
    """نیم‌دایره‌ی امتیاز نهایی: ۰ سمت راست، ۱۰۰ سمت چپ، با نشانه‌ی آستانه‌ها."""
    import math
    c = doc.c
    c.saveState()
    c.setLineCap(0)
    c.setLineWidth(10)
    box = (cx - radius, base_y - radius, cx + radius, base_y + radius)
    c.setStrokeColor(COLOR_RULE)
    c.arc(*box, startAng=0, extent=180)
    if percent and percent > 0:
        c.setStrokeColor(COLOR_PRIMARY)
        c.arc(*box, startAng=0, extent=180 * min(percent, 100) / 100.0)
    c.setStrokeColor(COLOR_INK)
    c.setLineWidth(1)
    for t in (THRESHOLD_FAIL, THRESHOLD_PASS):
        ang = math.radians(t * 1.8)
        c.line(cx + (radius - 9) * math.cos(ang), base_y + (radius - 9) * math.sin(ang),
               cx + (radius + 6) * math.cos(ang), base_y + (radius + 6) * math.sin(ang))
    c.restoreState()
    for t in (THRESHOLD_FAIL, THRESHOLD_PASS):
        ang = math.radians(t * 1.8)
        lx = cx + (radius + 15) * math.cos(ang)
        ly = base_y + (radius + 15) * math.sin(ang)
        doc.c.setFont(FONT_REGULAR, 8)
        doc.c.setFillColor(COLOR_INK_SOFT)
        doc.c.drawCentredString(lx, ly - 2.5, str(t))
    doc.c.setFont(FONT_BOLD, 38)
    doc.c.setFillColor(COLOR_INK)
    doc.c.drawCentredString(cx, base_y + 4, str(percent))
    doc.text_center("از 100", cx, base_y - 17, size=8.5, color=COLOR_INK_SOFT)
    doc.c.setFont(FONT_REGULAR, 8)
    doc.c.setFillColor(COLOR_INK_SOFT)
    doc.c.drawCentredString(cx + radius, base_y - 17, "0")
    doc.c.drawCentredString(cx - radius, base_y - 17, "100")


# ---------------------------------------------------------------------------
# بخش‌های مشترک
# ---------------------------------------------------------------------------

def _draw_title_block(doc: _Doc, title: str, rows: list):
    """
    ۱. جلد گزارش: نوار تیره‌ی تمام‌عرض با عنوان و مشخصات صفحه‌ی بررسی‌شده.
    rows: [(برچسب فارسی, مقدار چپ‌به‌راست)] — آدرس بلند بر پایه‌ی نویسه شکسته می‌شود.
    """
    label_w = 96
    value_xr = RIGHT - label_w
    wrapped = [(lab, _wrap_chars(val, FONT_REGULAR, 9.5, value_xr - LEFT)) for lab, val in rows]
    n_lines = sum(len(w) for _, w in wrapped)
    band_h = 98 + n_lines * 15 + len(wrapped) * 4 + 22
    c = doc.c
    c.setFillColor(COLOR_PRIMARY)
    c.rect(0, PAGE_H - band_h, PAGE_W, band_h, stroke=0, fill=1)
    c.setFillColor(COLOR_ACCENT)
    c.rect(0, PAGE_H - band_h - 3, PAGE_W, 3, stroke=0, fill=1)
    doc.text("گزارش تحلیلی · ابزار ارزیابی E-E-A-T", RIGHT, PAGE_H - 34, size=9, color=COLOR_RULE)
    doc.text(title, RIGHT, PAGE_H - 68, font=FONT_BOLD, size=25, color=COLOR_PAPER)
    y = PAGE_H - 98
    for label, lines in wrapped:
        doc.text(label, RIGHT, y, size=8.8, color=COLOR_RULE)
        for line in lines:
            doc.raw_right(line, value_xr, y, size=9.5, color=COLOR_SURFACE)
            y -= 15
        y -= 4
    doc.y = PAGE_H - band_h - 3 - 30


def _draw_section_title(doc: _Doc, text: str, keep_with: float = 80):
    """عنوان بخش اصلی (هم‌اندازه برای همه‌ی بخش‌ها)؛ همراه محتوای بعدی‌اش می‌ماند."""
    doc.ensure(keep_with)
    doc.c.setFillColor(COLOR_ACCENT)
    doc.c.rect(RIGHT + 8, doc.y - 18, 3, 19, stroke=0, fill=1)
    doc.text(text, RIGHT, doc.y - 14, font=FONT_BOLD, size=15, color=COLOR_PRIMARY)
    doc.space(32)


def _draw_legend(doc: _Doc):
    """۵. توضیح تکمیلی: آستانه‌ها و معنی وضعیت‌های خاص (همان «معنی وضعیت‌ها» در وب)."""
    doc.ensure(150)
    _draw_section_title(doc, "معنی وضعیت‌ها", keep_with=150)
    note = (f"نوارها و مقیاس‌ها از ۰ تا ۱۰۰ هستند: کمتر از {THRESHOLD_FAIL} ضعیف، "
            f"تا {THRESHOLD_PASS} نیاز به بهبود و {THRESHOLD_PASS} به بالا خوب. "
            f"خط‌های عمودی روی نوارها همین دو آستانه‌اند.")
    n = doc.paragraph(note, RIGHT, CONTENT_W, doc.y - 8, size=9.5, color=COLOR_INK, leading=15)
    doc.space(n * 15 + 8)
    for status, term, desc in LEGEND:
        doc.ensure(24)
        _draw_mark(doc, status, RIGHT - 5, doc.y - 8)
        doc.text(term, RIGHT - 18, doc.y - 11, font=FONT_BOLD, size=9.5)
        doc.paragraph(desc, RIGHT - 110, RIGHT - 110 - LEFT, doc.y - 11, size=9.5,
                      color=COLOR_INK_SOFT, leading=15)
        doc.space(21)


def _split_facts(evidence: str) -> list:
    """شواهد «چرا این نمره» را به واقعیت‌های جدا می‌شکند (همان جداکننده‌ی وب)."""
    return [p.strip() for p in (evidence or "").split(" | ") if p.strip()]


def _facts_paragraph_text(evidence: str) -> str:
    return "؛ ".join(_split_facts(evidence))


# ---------------------------------------------------------------------------
# گزارش تک‌صفحه
# ---------------------------------------------------------------------------

def _build_indicator_tip_text(ind: dict) -> str:
    """
    متن نهایی «چه کار باید بکند» برای یک شاخص، با لحن مناسبِ وضعیت فعلی‌اش.

    ind["tip"] که از build_report_context در webapp/app.py می‌آید فقط برای
    status در (fail, warn) پر می‌شود — چون صفحه‌ی وب عمداً فقط به شاخص‌های
    ضعیف توصیه نشان می‌دهد. اما PDF صریحاً برای «هر شاخص» (از جمله آن‌هایی
    که وضعیت خوبی دارند) می‌گوید چه باید کرد؛ پس مستقیم از IMPROVEMENT_TIPS[code]
    خوانده می‌شود — همان منبع واحد حقیقت، بدون فیلتر صفحه‌ی وب.
    """
    base_tip = IMPROVEMENT_TIPS.get(ind["code"])
    status = ind["status"]
    if status == "not_applicable":
        return "این شاخص برای این نوع صفحه از ابتدا قابل‌اعمال نیست، پس نیازی به اقدام نیست."
    if status == "missing":
        return "محتوای صفحه برای سنجش قابل‌اتکای این شاخص کافی نبود؛ نمی‌توان با اطمینان توصیه‌ای داد."
    if not base_tip:
        return ""
    if status == "pass":
        return f"این شاخص وضعیت خوبی دارد. برای حفظ و تقویت بیشترش: {base_tip}"
    return base_tip


def _tip_heading(status: str) -> str:
    if status == "pass":
        return "برای حفظ این نتیجه"
    if status in ("missing", "not_applicable"):
        return "توضیح"
    return "برای بهبود"


_BAND_X = LEFT - 10
_BAND_W = CONTENT_W + 20


def _draw_row_bg(doc: _Doc, y0: float, height: float):
    """زمینه‌ی سفید یک بلوک شاخص (تا خط جداکننده‌ی پایینش)."""
    doc.c.setFillColor(COLOR_SURFACE)
    doc.c.rect(_BAND_X, y0 - height + 4, _BAND_W, height - 4, stroke=0, fill=1)


def _draw_comp_band(doc: _Doc, label: str, left_pct=None, left_word=None):
    """سرتیتر مؤلفه: نوار تیره با نام مؤلفه (راست) و امتیازش (چپ)."""
    top = doc.y
    doc.c.setFillColor(COLOR_PRIMARY)
    doc.c.roundRect(_BAND_X, top - 28, _BAND_W, 28, 3, stroke=0, fill=1)
    doc.text(label, RIGHT, top - 18, font=FONT_BOLD, size=13, color=COLOR_PAPER)
    if left_pct is not None:
        doc.raw_left(left_pct, LEFT, top - 18.5, font=FONT_BOLD, size=12.5, color=COLOR_PAPER)
        if left_word:
            w = pdfmetrics.stringWidth(left_pct, FONT_BOLD, 12.5)
            doc.text_left(left_word, LEFT + w + 10, top - 18, size=9.5, color=COLOR_RULE)
    elif left_word:
        doc.text_left(left_word, LEFT, top - 18, size=9.5, color=COLOR_RULE)
    doc.space(28)


# ستون‌های ردیف شاخص (از چپ): واژه‌ی وضعیت، عدد، نوار؛ برچسب از راست
_IND_WORD_XR = LEFT + 68
_IND_NUM_XR = LEFT + 104
_IND_TRACK_XL = LEFT + 114
_IND_TRACK_XR = LEFT + 200
_BODY_XR = RIGHT - 18
_BODY_W = 400


def _indicator_layout(ind: dict) -> dict:
    """اندازه‌گیری مقدم یک بلوک شاخص تا بلوک هرگز وسط صفحه نشکند."""
    facts_text = _facts_paragraph_text(ind.get("evidence"))
    facts_lines = _wrap_to_width(facts_text, FONT_REGULAR, 9, _BODY_W) if facts_text else []
    tip_text = ind.get("tip_text") or ""
    tip_lines = _wrap_to_width(tip_text, FONT_REGULAR, 9, _BODY_W - 10) if tip_text else []
    height = 22
    if facts_lines:
        height += 6 + 13 + len(facts_lines) * 13
    if tip_lines:
        height += 8 + 13 + len(tip_lines) * 13
    height += 12
    return {"facts": facts_lines, "tip": tip_lines, "height": height}


def _draw_indicator(doc: _Doc, ind: dict, layout: dict = None):
    layout = layout or _indicator_layout(ind)
    doc.ensure(layout["height"])
    status = ind["status"]
    y0 = doc.y
    row_y = y0 - 12
    _draw_row_bg(doc, y0, layout["height"])

    # ردیف اصلی: نشانه، نام و کد (راست) ← نوار، عدد، واژه‌ی وضعیت (چپ)
    _draw_mark(doc, status, RIGHT - 5, row_y + 3.5)
    label = ind["label"]
    doc.text(label, RIGHT - 18, row_y, font=FONT_BOLD, size=10.5)
    label_w = pdfmetrics.stringWidth(label, FONT_BOLD, 10.5)
    doc.raw_right(ind["code"], RIGHT - 18 - label_w - 7, row_y, size=8.5, color=COLOR_INK_SOFT)

    percent = ind.get("value_percent")
    _draw_track(doc, _IND_TRACK_XL, _IND_TRACK_XR, row_y + 3, percent, status)
    num = "—" if status in ("missing", "not_applicable") or percent is None else _pct_text(percent)
    doc.raw_right(num, _IND_NUM_XR, row_y, font=FONT_BOLD, size=10.5)
    word = status_word(status, percent)
    doc.text_left(word, LEFT, row_y,
                  font=FONT_BOLD if status in STATUS_WORD_BOLD else FONT_REGULAR,
                  size=8.8, color=STATUS_WORD_COLORS.get(status, COLOR_INK_SOFT))
    y = y0 - 22

    # چرا این نمره
    if layout["facts"]:
        y -= 6
        doc.text("چرا این نمره", _BODY_XR, y - 9, font=FONT_BOLD, size=8.8, color=COLOR_INK_SOFT)
        y -= 13
        doc.paragraph(_facts_paragraph_text(ind.get("evidence")), _BODY_XR, _BODY_W, y - 9,
                      size=9, color=COLOR_INK, leading=13)
        y -= len(layout["facts"]) * 13

    # توصیه (برای بهبود / حفظ / توضیح)
    if layout["tip"]:
        y -= 8
        bar_color = COLOR_ACCENT if status in ("fail", "warn") else COLOR_SECONDARY
        block_h = 13 + len(layout["tip"]) * 13
        doc.c.setFillColor(bar_color)
        doc.c.rect(_BODY_XR + 1, y - block_h + 2, 2, block_h, stroke=0, fill=1)
        doc.text(_tip_heading(status), _BODY_XR - 9, y - 9, font=FONT_BOLD, size=8.8,
                 color=COLOR_ACCENT_INK if status in ("fail", "warn") else COLOR_INK_SOFT)
        doc.paragraph(ind["tip_text"], _BODY_XR - 9, _BODY_W - 10, y - 22,
                      size=9, color=COLOR_INK, leading=13)
        y -= block_h

    y -= 8
    doc.hline(y)
    doc.y = y - 4


def _status_counts(components: list) -> dict:
    counts = {"pass": 0, "warn": 0, "fail": 0, "missing": 0, "not_applicable": 0, "total": 0}
    for comp in components:
        for ind in comp["indicators"]:
            counts[ind["status"]] = counts.get(ind["status"], 0) + 1
            counts["total"] += 1
    return counts


def _draw_single_result_panel(doc: _Doc, context: dict):
    """۲ و ۳. امتیاز نهایی و چهار مؤلفه، داخل یک قاب."""
    components = context["components"]
    final_pct = context["final_score_percent"]
    final_status = context.get("final_status") or (
        "fail" if final_pct < THRESHOLD_FAIL else "warn" if final_pct < THRESHOLD_PASS else "pass")
    counts = _status_counts(components)

    ranked = sorted((c for c in components if c.get("score_percent") is not None),
                    key=lambda c: c["score_percent"])
    summary = "میانگین وزنی چهار مؤلفه."
    if len(ranked) >= 2 and ranked[0]["score_percent"] != ranked[-1]["score_percent"]:
        summary += (f" بالاترین مؤلفه {ranked[-1]['label']} ({ranked[-1]['score_percent']}٪) و "
                    f"پایین‌ترین {ranked[0]['label']} ({ranked[0]['score_percent']}٪) است.")

    if context.get("type_note"):
        summary += " " + context["type_note"]

    pad = 24
    text_xr = RIGHT - pad
    text_w = 250
    sum_lines = _wrap_to_width(summary, FONT_REGULAR, 9.5, text_w)
    top_h = 14 + 12 + 16 + 10 + len(sum_lines) * 15 + 12 + 14 + 5 * 16 + 4
    top_h = max(top_h, 190)
    rows_h = len(components) * 26
    panel_h = pad + top_h + pad - 14

    doc.ensure(panel_h)
    top = doc.y
    doc.panel(top, panel_h)

    # --- امتیاز نهایی: نیم‌دایره (چپ) و خلاصه (راست) ---
    y = top - pad
    _draw_gauge(doc, LEFT + pad + 90, y - 128, final_pct)

    doc.text("امتیاز نهایی", text_xr, y - 12, font=FONT_BOLD, size=13, color=COLOR_PRIMARY)
    _draw_mark(doc, final_status, text_xr - 5, y - 36 + 4, r=5.2)
    doc.text(status_word(final_status, final_pct), text_xr - 18, y - 36, font=FONT_BOLD, size=12.5)
    sy = y - 60
    doc.paragraph(summary, text_xr, text_w, sy, size=9.5, color=COLOR_INK_SOFT, leading=15)
    sy -= len(sum_lines) * 15 + 6
    doc.text(f"از {counts['total']} شاخص", text_xr, sy, size=8.8, color=COLOR_INK_SOFT)
    sy -= 17
    for status, label in (("pass", "وضعیت خوب"), ("warn", "نیاز به بهبود"),
                          ("fail", "ضعیف یا صفر"), ("missing", "داده ناموجود"),
                          ("not_applicable", "غیرقابل اعمال")):
        n = counts[status]
        muted = n == 0
        _draw_mark(doc, status, text_xr - 5, sy + 3.5)
        doc.raw_right(str(n), text_xr - 14, sy, font=FONT_REGULAR if muted else FONT_BOLD, size=9.5,
                      color=COLOR_INK_SOFT if muted else COLOR_INK)
        doc.text(label, text_xr - 40, sy, size=9.5, color=COLOR_INK_SOFT if muted else COLOR_INK)
        sy -= 16

    doc.y = top - panel_h - 30

    # --- چهار مؤلفه: کارت‌های ۲×۲ ---
    _draw_section_title(doc, "چهار مؤلفه", keep_with=40 + 2 * 96)
    gap = 14
    cw = (CONTENT_W - gap) / 2.0
    ch = 86
    for idx, comp in enumerate(components):
        if idx % 2 == 0:
            doc.ensure(ch + 12)
            row_top = doc.y
        xr = RIGHT - (idx % 2) * (cw + gap)
        xl = xr - cw
        doc.c.setFillColor(COLOR_SURFACE)
        doc.c.setStrokeColor(COLOR_RULE)
        doc.c.setLineWidth(0.6)
        doc.c.roundRect(xl, row_top - ch, cw, ch, 3, stroke=1, fill=1)
        doc.text(comp["label"], xr - 14, row_top - 24, font=FONT_BOLD, size=12, color=COLOR_PRIMARY)
        pct = comp.get("score_percent")
        if pct is not None:
            doc.raw_left(_pct_text(pct), xl + 14, row_top - 26, font=FONT_BOLD, size=22)
        else:
            doc.text_left("ناموجود", xl + 14, row_top - 24, size=10, color=COLOR_INK_SOFT)
        _draw_track(doc, xl + 14, xr - 14, row_top - 49, pct, comp["status"], h=8)
        _draw_mark(doc, comp["status"], xr - 19, row_top - 71 + 3.5)
        doc.text(status_word(comp["status"], pct), xr - 32, row_top - 71, size=9.5,
                 font=FONT_BOLD if comp["status"] in STATUS_WORD_BOLD else FONT_REGULAR,
                 color=STATUS_WORD_COLORS.get(comp["status"], COLOR_INK_SOFT))
        if idx % 2 == 1 or idx == len(components) - 1:
            doc.y = row_top - ch - 14
    doc.space(14)


def _draw_component_head(doc: _Doc, comp: dict):
    pct = comp.get("score_percent")
    if pct is None:
        _draw_comp_band(doc, comp["label"], left_word="امتیاز مؤلفه ناموجود")
    else:
        _draw_comp_band(doc, comp["label"], _pct_text(pct), status_word(comp["status"], pct))


def generate_pdf_report(context: dict, output_path: str) -> str:
    """
    ساخت فایل PDF گزارش از همان context ای که build_report_context در
    webapp/app.py برای صفحه‌ی نتیجه‌ی وب می‌سازد.

    ترتیب: عنوان و مشخصات ← امتیاز نهایی ← چهار مؤلفه ← جزئیات شاخص‌ها ←
    معنی وضعیت‌ها. خروجی: همان output_path.
    """
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M")
    doc = _Doc(output_path, "گزارش ارزیابی E-E-A-T", generated_at)

    _draw_title_block(doc, "گزارش ارزیابی E-E-A-T", [
        ("صفحه‌ی بررسی‌شده", context["url"]),
        ("تاریخ تولید گزارش", generated_at),
    ])
    _draw_single_result_panel(doc, context)

    _draw_section_title(doc, "جزئیات شاخص‌ها", keep_with=170)
    for comp in context["components"]:
        inds = []
        for ind in comp["indicators"]:
            ind = dict(ind)
            ind["tip_text"] = _build_indicator_tip_text(ind)
            inds.append((ind, _indicator_layout(ind)))
        first_h = inds[0][1]["height"] if inds else 0
        doc.ensure(40 + first_h)  # عنوان مؤلفه تنها ته صفحه نمی‌ماند
        _draw_component_head(doc, comp)
        for ind, layout in inds:
            _draw_indicator(doc, ind, layout)
        doc.space(16)

    _draw_legend(doc)
    doc.c.save()
    return output_path


# ===========================================================================
# گزارش PDF «مقایسه‌ی دو صفحه»
# ورودی: خروجی webapp.comparison.build_comparison_context.
# ===========================================================================

_SIDE_NAME = {"a": "صفحه‌ی اول", "b": "صفحه‌ی دوم"}


def _side_status_text(side: dict) -> str:
    status = side.get("status")
    if status == "not_applicable":
        return STATUS_LABELS_FA["not_applicable"]
    if status == "missing" or side.get("percent") is None:
        return STATUS_LABELS_FA["missing"]
    return f"{_pct_text(side['percent'])} ({status_word(status, side['percent'])})"


def _verdict_text(result: str, diff) -> str:
    """متن فارسی نتیجه‌ی یک ردیف؛ برای حالت «بدون قضاوت» برنده‌ای ادعا نمی‌شود."""
    if result == "a":
        return f"برنده: {_SIDE_NAME['a']} (اختلاف {abs(diff)} واحد درصد)"
    if result == "b":
        return f"برنده: {_SIDE_NAME['b']} (اختلاف {abs(diff)} واحد درصد)"
    if result == "tie":
        return "مساوی؛ برنده‌ای اعلام نمی‌شود"
    return "بدون قضاوت؛ یکی از دو طرف داده‌ی کافی ندارد یا شاخص غیرقابل‌اعمال است"


def _short_verdict(result: str, diff) -> str:
    if result == "tie":
        return "مساوی"
    if result == "none":
        return "بدون قضاوت"
    return f"اختلاف {abs(diff)}"


def comparison_tip_sides(ind: dict) -> list:
    """
    کدام طرف‌ها در PDF «برای بهبود» می‌گیرند (تابع خالص، قابل‌تست):
    - اگر برنده‌ای هست: فقط طرف ضعیف‌تر.
    - اگر مساوی یا بدون‌قضاوت است: فقط طرف‌هایی که خودشان ضعیف/نیازمند
      بهبود (fail/warn) هستند؛ طرفی که missing/not_applicable یا خوب
      است توصیه نمی‌گیرد.
    """
    result = ind["result"]
    if result == "a":
        return ["b"]
    if result == "b":
        return ["a"]
    return [k for k in ("a", "b") if ind[k].get("status") in ("fail", "warn")]


# شبکه‌ی جدول مقایسه (از راست): برچسب | صفحه‌ی اول | اختلاف | صفحه‌ی دوم
_CMP_LABEL_W = 118
_CMP_CELL_W = 150
_CMP_DIFF_W = 77
_CMP_A_XR = RIGHT - _CMP_LABEL_W
_CMP_A_XL = _CMP_A_XR - _CMP_CELL_W
_CMP_DIFF_XC = _CMP_A_XL - _CMP_DIFF_W / 2.0
_CMP_B_XR = _CMP_A_XL - _CMP_DIFF_W
_CMP_B_XL = _CMP_B_XR - _CMP_CELL_W


def _draw_cmp_cell(doc: _Doc, xr: float, yc: float, side: dict, is_win: bool):
    """یک سلول طرف مقایسه: نوار، عدد (برنده با زمینه‌ی تیره) و واژه‌ی وضعیت."""
    status = side.get("status")
    percent = side.get("percent")
    trk_xl, trk_xr = xr - 60, xr
    _draw_track(doc, trk_xl, trk_xr, yc, percent, status, h=7, strong=is_win)
    unavailable = status in ("missing", "not_applicable") or percent is None
    num = "—" if unavailable else _pct_text(percent)
    nx = trk_xl - 6
    if is_win and not unavailable:
        wdt = pdfmetrics.stringWidth(num, FONT_BOLD, 9.5) + 8
        doc.c.setFillColor(COLOR_PRIMARY)
        doc.c.roundRect(nx - wdt, yc - 6.5, wdt, 13, 1.5, stroke=0, fill=1)
        doc.raw_right(num, nx - 4, yc - 3.2, font=FONT_BOLD, size=9.5, color=COLOR_SURFACE)
        num_left = nx - wdt
    else:
        doc.raw_right(num, nx, yc - 3.2, font=FONT_BOLD if not unavailable else FONT_REGULAR, size=9.5)
        num_left = nx - pdfmetrics.stringWidth(num, FONT_BOLD, 9.5)
    word = status_word(status, percent)
    doc.text(word, num_left - 6, yc - 3, size=8.3,
             font=FONT_BOLD if status in STATUS_WORD_BOLD else FONT_REGULAR,
             color=STATUS_WORD_COLORS.get(status, COLOR_INK_SOFT))


def _draw_cmp_colhead(doc: _Doc):
    doc.text(_SIDE_NAME["a"], _CMP_A_XR, doc.y - 10, font=FONT_BOLD, size=9, color=COLOR_INK_SOFT)
    doc.text(_SIDE_NAME["b"], _CMP_B_XR, doc.y - 10, font=FONT_BOLD, size=9, color=COLOR_INK_SOFT)
    doc.space(16)


def _draw_comparison_header(doc: _Doc, cmp_ctx: dict, generated_at: str):
    """۱ تا ۲. عنوان، مشخصات دو صفحه و امتیاز نهایی هر دو."""
    _draw_title_block(doc, "گزارش مقایسه‌ی E-E-A-T دو صفحه", [
        (_SIDE_NAME["a"], cmp_ctx["a"]["url"]),
        (_SIDE_NAME["b"], cmp_ctx["b"]["url"]),
        ("تاریخ تولید گزارش", generated_at),
    ])

    final, t = cmp_ctx["final"], cmp_ctx["tally"]
    verdict = {
        "tie": "امتیاز نهایی دو صفحه برابر است؛ برنده‌ای اعلام نمی‌شود.",
        "none": "مقایسه‌ی امتیاز نهایی ممکن نیست.",
    }.get(final["result"]) or (
        f"امتیاز نهایی {_SIDE_NAME[final['result']]} {abs(final['diff'])} واحد درصد بیشتر است.")
    summary = (f"{verdict} از ۱۹ شاخص: صفحه‌ی اول در {t['a']}، صفحه‌ی دوم در {t['b']}، "
               f"مساوی در {t['tie']}، و بدون قضاوت در {t['none']} شاخص بهتر بود.")

    pad = 24
    inner_w = CONTENT_W - 2 * pad
    sum_lines = _wrap_to_width(summary, FONT_REGULAR, 9.5, inner_w)
    dis_text = " ".join(list(cmp_ctx.get("type_notes") or []) + [cmp_ctx["disclaimer"]])
    dis_lines = _wrap_to_width(dis_text, FONT_REGULAR, 8.8, inner_w)
    panel_h = pad + 112 + 14 + len(sum_lines) * 15 + 12 + 1 + 14 + len(dis_lines) * 13 + pad - 6
    doc.ensure(panel_h)
    top = doc.y
    doc.panel(top, panel_h)

    half = (inner_w - 30) / 2.0
    for idx, key in enumerate(("a", "b")):
        xr = RIGHT - pad - idx * (half + 30)
        xl = xr - half
        win = final["result"] == key
        doc.c.setFillColor(COLOR_PRIMARY if win else COLOR_RULE)
        doc.c.rect(xl, top - pad - 3, half, 3, stroke=0, fill=1)
        doc.text(_SIDE_NAME[key], xr, top - pad - 24, font=FONT_BOLD, size=12, color=COLOR_PRIMARY)
        doc.raw_right(str(final[key]), xr - 20, top - pad - 72, font=FONT_BOLD, size=42)
        doc.text("٪", xr - 2, top - pad - 72, font=FONT_REGULAR, size=16, color=COLOR_INK_SOFT)
        if win:
            _draw_mark(doc, "pass", xr - 5, top - pad - 98 + 4, r=5)
            doc.text("برنده در امتیاز نهایی", xr - 18, top - pad - 98, font=FONT_BOLD, size=10)
        else:
            doc.text("مساوی" if final["result"] == "tie" else "امتیاز نهایی", xr,
                     top - pad - 98, size=9.5, color=COLOR_INK_SOFT)

    y = top - pad - 112 - 14
    doc.paragraph(summary, RIGHT - pad, inner_w, y, size=9.5, leading=15)
    y -= len(sum_lines) * 15 + 4
    doc.hline(y, LEFT + pad, RIGHT - pad)
    y -= 16
    doc.paragraph(dis_text, RIGHT - pad, inner_w, y, size=8.8,
                  color=COLOR_INK_SOFT, leading=13)
    doc.y = top - panel_h - 34


def _draw_comparison_component_table(doc: _Doc, components: list):
    """۳. مقایسه‌ی چهار مؤلفه: یک جدول با ستون‌های برچسب | صفحه‌ی اول | اختلاف | صفحه‌ی دوم."""
    _draw_section_title(doc, "مقایسه‌ی مؤلفه‌ها", keep_with=40 + 4 * 30)
    _draw_cmp_colhead(doc)
    doc.hline(doc.y, color=COLOR_PRIMARY, width=0.9)
    doc.ensure(30 * len(components) + 6)
    doc.c.setFillColor(COLOR_SURFACE)
    doc.c.rect(_BAND_X, doc.y - 30 * len(components), _BAND_W, 30 * len(components),
               stroke=0, fill=1)
    for comp in components:
        row_h = 30
        doc.ensure(row_h)
        yc = doc.y - row_h / 2.0
        doc.text(comp["label"], RIGHT, yc - 3.5, font=FONT_BOLD, size=10.5)
        _draw_cmp_cell(doc, _CMP_A_XR, yc, comp["a"], comp["result"] == "a")
        doc.text_center(_short_verdict(comp["result"], comp["diff"]), _CMP_DIFF_XC, yc - 3,
                        size=8.8, color=COLOR_INK_SOFT)
        _draw_cmp_cell(doc, _CMP_B_XR, yc, comp["b"], comp["result"] == "b")
        doc.space(row_h)
        doc.hline(doc.y)
    doc.space(34)


_CMP_EVID_W = 232


def _comparison_indicator_layout(ind: dict) -> dict:
    label_lines = _wrap_to_width(ind["label"], FONT_BOLD, 9.8, _CMP_LABEL_W - 8)
    row_h = max(len(label_lines) * 12 + 12, 30)
    evid = {}
    for key in ("a", "b"):
        text = _facts_paragraph_text(ind[key].get("evidence"))
        evid[key] = _wrap_to_width(text, FONT_REGULAR, 8.8, _CMP_EVID_W) if text else []
    evid_rows = max(len(evid["a"]), len(evid["b"]))
    height = row_h
    if evid_rows:
        height += 4 + 12 + evid_rows * 12.5
    base_tip = IMPROVEMENT_TIPS.get(ind["code"])
    tip_blocks = []
    if base_tip:
        sides = comparison_tip_sides(ind)
        groups = ["هر دو صفحه"] if len(sides) == 2 else [_SIDE_NAME[k] for k in sides]
        tip_lines = _wrap_to_width(base_tip, FONT_REGULAR, 9, CONTENT_W - 30)
        for who in groups:
            tip_blocks.append((who, tip_lines))
            height += 8 + 13 + len(tip_lines) * 13
    height += 12
    return {"label_lines": label_lines, "row_h": row_h, "evid": evid,
            "evid_rows": evid_rows, "tips": tip_blocks, "height": height}


def _draw_comparison_indicator(doc: _Doc, ind: dict, layout: dict = None):
    layout = layout or _comparison_indicator_layout(ind)
    doc.ensure(layout["height"])
    y0 = doc.y
    _draw_row_bg(doc, y0, layout["height"])
    row_h = layout["row_h"]
    yc = y0 - row_h / 2.0

    # برچسب (تا دو خط) و کد
    ly = yc + (len(layout["label_lines"]) - 1) * 6 - 3
    for i, line in enumerate(layout["label_lines"]):
        doc.text(line, RIGHT, ly - i * 12, font=FONT_BOLD, size=9.8)
    doc.raw_right(ind["code"], RIGHT, ly - len(layout["label_lines"]) * 12 + 1,
                  size=8, color=COLOR_INK_SOFT)
    _draw_cmp_cell(doc, _CMP_A_XR, yc, ind["a"], ind["result"] == "a")
    doc.text_center(_short_verdict(ind["result"], ind["diff"]), _CMP_DIFF_XC, yc - 3,
                    size=8.8, color=COLOR_INK_SOFT)
    _draw_cmp_cell(doc, _CMP_B_XR, yc, ind["b"], ind["result"] == "b")
    y = y0 - row_h

    # چرا این نمره، برای هر دو صفحه کنار هم
    if layout["evid_rows"]:
        y -= 4
        for key, xr in (("a", RIGHT), ("b", RIGHT - _CMP_EVID_W - 26)):
            if layout["evid"][key]:
                doc.text(f"{_SIDE_NAME[key]} — چرا این نمره", xr, y - 9, font=FONT_BOLD,
                         size=8.5, color=COLOR_INK_SOFT)
                doc.paragraph(_facts_paragraph_text(ind[key].get("evidence")), xr,
                              _CMP_EVID_W, y - 22, size=8.8, color=COLOR_INK, leading=12.5)
        y -= 12 + layout["evid_rows"] * 12.5

    # برای بهبود
    for who, lines in layout["tips"]:
        y -= 8
        block_h = 13 + len(lines) * 13
        doc.c.setFillColor(COLOR_ACCENT)
        doc.c.rect(RIGHT - 9, y - block_h + 2, 2, block_h, stroke=0, fill=1)
        doc.text(f"برای بهبود ({who})", RIGHT - 18, y - 9, font=FONT_BOLD, size=8.8,
                 color=COLOR_ACCENT_INK)
        doc.paragraph(IMPROVEMENT_TIPS[ind["code"]], RIGHT - 18, CONTENT_W - 30, y - 22,
                      size=9, color=COLOR_INK, leading=13)
        y -= block_h

    y -= 8
    doc.hline(y)
    doc.y = y - 4


def generate_comparison_pdf(cmp_ctx: dict, output_path: str) -> str:
    """
    ساخت PDF مقایسه‌ی دو صفحه از خروجی webapp.comparison.build_comparison_context.
    ترتیب: عنوان و مشخصات ← امتیاز نهایی دو صفحه ← مقایسه‌ی مؤلفه‌ها ←
    جزئیات هر شاخص ← معنی وضعیت‌ها. خروجی: همان output_path.
    """
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M")
    doc = _Doc(output_path, "مقایسه‌ی E-E-A-T", generated_at)

    _draw_comparison_header(doc, cmp_ctx, generated_at)
    _draw_comparison_component_table(doc, cmp_ctx["components"])

    _draw_section_title(doc, "جزئیات هر شاخص", keep_with=170)
    for comp in cmp_ctx["components"]:
        inds = [(ind, _comparison_indicator_layout(ind)) for ind in comp["indicators"]]
        first_h = inds[0][1]["height"] if inds else 0
        doc.ensure(80 + first_h)
        _draw_comp_band(doc, comp["label"])
        doc.space(8)
        _draw_cmp_colhead(doc)
        for ind, layout in inds:
            _draw_comparison_indicator(doc, ind, layout)
        doc.space(16)

    _draw_legend(doc)
    doc.c.save()
    return output_path
