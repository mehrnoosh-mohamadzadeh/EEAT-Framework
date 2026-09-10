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


def parse_html(html: str, url: str) -> ParsedPage:
    """نقطه ورود اصلی ماژول Parser."""
    soup = BeautifulSoup(html, "lxml")

    main_content_soup = extract_main_content(soup)
    main_content_text = main_content_soup.get_text(separator=" ", strip=True)

    all_links = [
        {
            "href": a.get("href", ""),
            "text": a.get_text(strip=True),
            # متن کل عنصر والد — برای حالتی که برچسب قابل‌مشاهده (مثلاً
            # کنار یک آیکون) بیرون از خود تگ <a> نوشته شده باشد
            "parent_text": a.parent.get_text(strip=True) if a.parent else "",
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
      ۱. اگر تگ <article> وجود داشته باشد، همان به‌عنوان محتوای اصلی
         در نظر گرفته می‌شود (رایج‌ترین حالت در سایت‌های خبری/وبلاگ).
      ۲. در غیر این صورت، از میان تگ‌های <div>، بلوکی با بیشترین
         تراکم متن (نسبت طول متن به تعداد تگ‌های فرزند) انتخاب می‌شود
         — این یک heuristic شناخته‌شده و ساده برای تشخیص محتوای
         اصلی صفحه است (مشابه رویکرد کتابخانه‌هایی مثل Readability.js)،
         نه یک الگوریتم قطعی.
    """
    article_tag = soup.find("article")
    if article_tag is not None:
        return article_tag

    candidates = soup.find_all("div")
    if not candidates:
        return soup

    best_candidate = None
    best_density = -1.0

    for div in candidates:
        # از بلوک‌هایی که تودرتوی بلوک‌های غیرمحتوایی هستند صرف‌نظر کن
        if div.find_parent(NON_CONTENT_TAGS) is not None:
            continue

        text_length = len(div.get_text(strip=True))
        tag_count = len(div.find_all(True)) + 1  # +1 برای جلوگیری از تقسیم بر صفر
        density = text_length / tag_count

        if text_length > 100 and density > best_density:
            best_density = density
            best_candidate = div

    return best_candidate if best_candidate is not None else soup


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
