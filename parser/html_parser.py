"""
ماژول Parser — تبدیل HTML خام به ساختار DOM قابل پردازش.

ورودی: HTML خام (str)
خروجی: شیء BeautifulSoup + چند فیلد کمکی از پیش استخراج‌شده که
       تقریباً همه Extractor ها به آن نیاز دارند (برای جلوگیری از
       پردازش تکراری).
"""

import json
from dataclasses import dataclass
from bs4 import BeautifulSoup


# تگ‌هایی که معمولاً بخشی از محتوای اصلی نیستند و از محاسبه تراکم متن
# و از ناحیه اصلی محتوا کنار گذاشته می‌شوند
NON_CONTENT_TAGS = ["header", "footer", "nav", "aside", "script", "style", "form"]


@dataclass
class ParsedPage:
    """نتیجه پارس یک صفحه — ورودی مشترک همه Extractor ها."""
    soup: BeautifulSoup
    url: str
    main_content_text: str      # متن اصلی محتوا (بدون هدر/فوتر/منو)
    main_content_soup: BeautifulSoup  # ناحیه DOM محتوای اصلی (برای E4 و مشابه)
    all_links: list             # همه تگ‌های <a> با href
    all_images: list            # همه تگ‌های <img>
    headings: list              # لیست (سطح, متن) برای H1 تا H6
    json_ld_blocks: list        # داده‌های JSON-LD استخراج‌شده (خام، parse‌شده)


def _local_link_context_text(a_tag) -> str:
    """
    متن «محلی» اطراف یک لینک — برای حالتی که برچسب قابل‌مشاهده (مثلاً
    کنار یک آیکون، یا کلمه‌ی زمینه‌ساز مثل «طبق» قبل از لینک) بیرون
    از خود تگ <a> نوشته شده باشد.

    رفع باگ: نسخه‌ی قبل مستقیماً a.parent.get_text() را برمی‌گرداند —
    یعنی *کل* متن والد، شامل متن هر <a> خواهر دیگری که تصادفاً زیر
    همان والد باشد. این روی هر ساختار خیلی رایج «چند لینک کنار هم زیر
    یک والد مشترک» (فوتر با «درباره ما | تماس با ما | حریم خصوصی»،
    یا یک پاراگراف با چند لینک) باعث می‌شد همه‌ی آن لینک‌های خواهر یک
    parent_text کاملاً یکسان و آلوده به متن هم بگیرند — یعنی جست‌وجوی
    مثلاً «حریم خصوصی» می‌توانست روی لینک کاملاً نامرتبط «درباره ما»
    هم مچ شود، چون هر دو زیر یک والد بودند.

    حالا فقط متن خواهر/برادرهای مستقیمِ *غیر-<a>* همین لینک، در همان
    والد، جمع می‌شود — یعنی متن لینک‌های <a> دیگر (منبع اصلی آلودگی)
    کنار گذاشته می‌شود، ولی برچسب/کلمه‌ی زمینه‌ساز مجاور که خارج از
    خود <a> نوشته شده همچنان دیده می‌شود.
    """
    parent = a_tag.parent
    if parent is None:
        return ""
    parts = []
    for child in parent.children:
        if child is a_tag or getattr(child, "name", None) == "a":
            continue
        text = child.get_text(separator=" ", strip=True) if hasattr(child, "get_text") else str(child).strip()
        if text:
            parts.append(text)
    return " ".join(parts)


def parse_html(html: str, url: str) -> ParsedPage:
    """نقطه ورود اصلی ماژول Parser."""
    soup = BeautifulSoup(html, "lxml")

    main_content_soup = extract_main_content(soup)
    main_content_text = main_content_soup.get_text(separator=" ", strip=True)

    all_links = [
        {
            "href": a.get("href", ""),
            "text": a.get_text(strip=True),
            # متن محلی اطراف لینک — رجوع به _local_link_context_text بالا
            "parent_text": _local_link_context_text(a),
            # متن alt تصاویر داخل خود لینک (لینک‌های فقط-آیکون)
            "img_alt_text": " ".join(img.get("alt", "") for img in a.find_all("img")),
        }
        for a in soup.find_all("a", href=True)

    ]

    all_images = [
        {"src": img.get("src", ""), "alt": img.get("alt", "")}
        for img in soup.find_all("img")
    ]

    headings = [
        (int(h.name[1]), h.get_text(strip=True))
        for h in soup.find_all(["h1", "h2", "h3", "h4", "h5", "h6"])
    ]

    json_ld_blocks = _extract_json_ld(soup)

    return ParsedPage(
        soup=soup,
        url=url,
        main_content_text=main_content_text,
        main_content_soup=main_content_soup,
        all_links=all_links,
        all_images=all_images,
        headings=headings,
        json_ld_blocks=json_ld_blocks,
    )


def extract_main_content(soup: BeautifulSoup) -> BeautifulSoup:
    """
    تشخیص و استخراج ناحیه اصلی محتوا (نه هدر/سایدبار/فوتر/تبلیغات).

    استراتژی:
      ۱. اگر یک یا چند تگ <article> وجود داشته باشد، تگی که بیشترین
         متن را دارد انتخاب می‌شود — نه لزوماً اولی. رفع باگ: صفحات
         آرشیو/دسته‌بندی/برچسب معمولاً چند <article> دارند (یکی برای
         هر خلاصه‌ی کوتاه‌مقاله در لیست)؛ گرفتن فقط اولی می‌توانست
         یک تیزر چندکلمه‌ای باشد، نه محتوای کامل مقاله‌ی واقعی.
      ۲. در غیر این صورت، از میان تگ‌های <div>، بلوکی با بیشترین
         تراکم متن (نسبت طول متن به تعداد تگ‌های فرزند) انتخاب می‌شود
         — این یک heuristic شناخته‌شده و ساده برای تشخیص محتوای
         اصلی صفحه است (مشابه رویکرد کتابخانه‌هایی مثل Readability.js)،
         نه یک الگوریتم قطعی.

    رفع باگ کارایی: قبلاً برای هر div کاندید، get_text() و find_all(True)
    جداگانه صدا زده می‌شد — که یعنی زیرشاخه‌ی هر div تودرتو، چندین‌بار
    (یک‌بار برای خودش، یک‌بار برای هر div والدش) پیمایش می‌شد؛ روی
    صفحات واقعی با صدها div (تبلیغات، اسکریپت آنالیتیکس) این می‌توانست
    واقعاً کند شود. حالا (طول متن, تعداد تگ) هر گره با یک پیمایش
    تک‌مرحله‌ای (_compute_text_and_tag_counts) محاسبه می‌شود.
    """
    article_tags = soup.find_all("article")
    if article_tags:
        return max(article_tags, key=lambda tag: len(tag.get_text(strip=True)))

    candidates = soup.find_all("div")
    if not candidates:
        return soup

    metrics = _compute_text_and_tag_counts(soup)

    best_candidate = None
    best_density = -1.0

    for div in candidates:
        # از بلوک‌هایی که تودرتوی بلوک‌های غیرمحتوایی هستند صرف‌نظر کن
        if div.find_parent(NON_CONTENT_TAGS) is not None:
            continue

        text_length, tag_count = metrics.get(id(div), (0, 0))
        density = text_length / (tag_count + 1)  # +1 برای جلوگیری از تقسیم بر صفر

        if text_length > 100 and density > best_density:
            best_density = density
            best_candidate = div

    return best_candidate if best_candidate is not None else soup


def _compute_text_and_tag_counts(root) -> dict:
    """
    محاسبه‌ی (طول متن، تعداد تگ توی خودش+فرزندانش) برای هر عنصر HTML
    زیر ``root``، با یک پیمایش post-order — هر گره فقط یک‌بار بازدید
    می‌شود و نتیجه‌ی هر زیرشاخه مستقیماً از جمع نتایج فرزندانش به دست
    می‌آید، نه با پیمایش دوباره‌ی همان زیرشاخه برای هر گره‌ی والد.

    خروجی معادل دقیق همان چیزی است که قبلاً با
    ``len(tag.get_text(strip=True))`` و ``len(tag.find_all(True))``
    برای هر تگ جداگانه محاسبه می‌شد — فقط با پیچیدگی O(n) به‌جای
    O(n × عمق تودرتویی) روی کل درخت.

    خروجی: دیکشنری ``{id(tag): (text_length, tag_count)}``.
    """
    from bs4 import NavigableString

    metrics = {}

    def visit(node):
        if isinstance(node, NavigableString):
            return len(str(node).strip()), 0
        if not hasattr(node, "children"):
            return 0, 0

        text_length = 0
        tag_count = 0
        for child in node.children:
            child_text, child_tags = visit(child)
            text_length += child_text
            tag_count += child_tags

        if getattr(node, "name", None) is not None:
            tag_count += 1
            metrics[id(node)] = (text_length, tag_count)

        return text_length, tag_count

    visit(root)
    return metrics


def _extract_json_ld(soup: BeautifulSoup) -> list:
    """استخراج و پارس تمام بلوک‌های JSON-LD موجود در صفحه."""
    blocks = []
    for script_tag in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script_tag.string or "{}")
            blocks.append(data)
        except (json.JSONDecodeError, TypeError):
            # بلوک‌های JSON-LD نامعتبر/ناقص نادیده گرفته می‌شوند
            continue
    return blocks
