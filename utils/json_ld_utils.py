# -*- coding: utf-8 -*-
"""
کمک‌تابع مشترک برای باز کردن بلوک‌های JSON-LD که ممکن است در قالب
`@graph` بسته‌بندی شده باشند — الگوی رایج افزونه‌هایی مثل Yoast SEO
در وردپرس (که چند نوع schema — Organization، Article، Person،
WebSite — را همه در یک بلوک `{"@graph": [...]}` می‌گذارد).

یافته‌ی رفع باگ ۲ (کشف‌شده حین بازبینی نهایی): بعضی سایت‌ها به‌جای
`@graph`، مستقیم یک آرایه‌ی JSON خام در تگ script می‌گذارند، مثل
`<script type="application/ld+json">[{...}, {...}]</script>`. نسخه‌ی
اول این تابع فقط dict را می‌پذیرفت و هر بلوکی که خودش یک لیست بود را
کامل نادیده می‌گرفت (`if not isinstance(block, dict): continue`) —
یعنی داده‌ی واقعاً موجود در این حالت هم، درست مثل حالت @graph، از
دست می‌رفت. حالا هر دو حالت پوشش داده می‌شوند.
"""


def flatten_json_ld_blocks(json_ld_blocks: list) -> list:
    """
    ورودی: parsed_page.json_ld_blocks (لیست خام بلوک‌های JSON-LD،
    همان‌طور که parser/html_parser.py با json.loads پارس کرده است؛
    هر بلوک می‌تواند dict باشد، یا خودش یک لیست باشد اگر تگ script
    مستقیماً یک آرایه‌ی JSON داشته).

    خروجی: یک لیست تخت از dict های schema — سه حالت پوشش داده می‌شود:
      ۱. بلوک یک dict معمولی است -> عیناً اضافه می‌شود
      ۲. بلوک یک dict با `{"@graph": [...]}` است -> آیتم‌های داخلش باز می‌شوند
      ۳. بلوک خودش یک لیست خام است (بدون @graph) -> آیتم‌هایش مستقیم اضافه می‌شوند
    هر extractor باید همیشه از این تابع استفاده کند، نه مستقیم روی
    json_ld_blocks حلقه بزند — تا با هر دو الگوی رایج سازگار بماند.
    """
    flattened = []
    for block in json_ld_blocks:
        if isinstance(block, list):
            flattened.extend(item for item in block if isinstance(item, dict))
            continue
        if not isinstance(block, dict):
            continue
        graph = block.get("@graph")
        if isinstance(graph, list):
            flattened.extend(item for item in graph if isinstance(item, dict))
        else:
            flattened.append(block)
    return flattened
