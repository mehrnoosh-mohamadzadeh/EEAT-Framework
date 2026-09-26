"""
تست‌های واحد webapp/app.py — تمرکز روی جلوگیری از تکرار باگ «برچسب‌های
عقب‌افتاده» (وقتی extractorها raw_details جدید اضافه می‌کنند ولی
RAW_DETAILS_LABELS به‌روزرسانی نمی‌شود).
"""

from parser.html_parser import parse_html
from extractors.experience_extractor import ExperienceExtractor
from extractors.expertise_extractor import ExpertiseExtractor
from extractors.authority_extractor import AuthorityExtractor
from extractors.trust_extractor import TrustExtractor
from webapp.app import RAW_DETAILS_LABELS, RAW_DETAILS_KEYS_HANDLED_SEPARATELY, _format_evidence


# یک صفحه‌ی نسبتاً غنی که بیشتر مسیرهای extractorها را فعال می‌کند
# (بدون نیاز به شبکه‌ی واقعی) تا حداکثر تعداد کلید raw_details واقعی
# تولید شود
RICH_SAMPLE_HTML = """
<html><head>
<script type="application/ld+json">
{"@graph": [
    {"@type": "Organization", "name": "شرکت نمونه", "sameAs": ["https://twitter.com/example"]},
    {"@type": "Article", "dateModified": "2024-01-01T00:00:00Z"}
]}
</script>
</head>
<body>
<article>
<h1>یک مقاله واقعی و بلند برای تست</h1>
<div class="author-box">نویسنده: دکتر سارا محمدی، متخصص تغذیه</div>
<p>من خودم پنج سال است که در این حوزه کار کرده‌ام و تجربه عملی زیادی دارم.
""" + (" ".join(["محتوای تکمیلی برای رسیدن به طول کافی."] * 60)) + """
</p>
<div><iframe src="https://www.youtube.com/embed/xyz"></iframe></div>
<a href="https://harvard.edu/research">طبق این پژوهش معتبر</a>
<a href="/privacy">حریم خصوصی</a>
<a href="/about-us">درباره ما</a>
</article>
</body></html>
"""


def _collect_all_raw_details_keys() -> set:
    """اجرای همه extractorها روی یک صفحه غنی و جمع‌آوری همه کلیدهای raw_details تولیدشده."""
    parsed = parse_html(RICH_SAMPLE_HTML, "https://example.ac.ir/article")
    all_keys = set()
    for Extractor in [ExperienceExtractor, ExpertiseExtractor, AuthorityExtractor, TrustExtractor]:
        for result in Extractor().extract(parsed):
            if result.raw_details:
                all_keys.update(result.raw_details.keys())
    return all_keys


class TestRawDetailsLabelsConsistency:

    def test_every_produced_key_has_a_label_or_is_handled_separately(self):
        """
        رگرسیون مورد ۹: هر کلید raw_details که extractorها واقعاً
        تولید می‌کنند، باید یا در RAW_DETAILS_LABELS برچسب فارسی
        داشته باشد، یا صریحاً در RAW_DETAILS_KEYS_HANDLED_SEPARATELY
        باشد (مثل reason/note). این تست جلوی برگشتن بی‌صدای همین باگ
        در آینده را می‌گیرد.
        """
        produced_keys = _collect_all_raw_details_keys()
        known_keys = set(RAW_DETAILS_LABELS.keys()) | RAW_DETAILS_KEYS_HANDLED_SEPARATELY

        unlabeled = produced_keys - known_keys
        assert not unlabeled, f"این کلیدها برچسب فارسی ندارند: {unlabeled}"

    def test_format_evidence_never_shows_raw_english_key_for_known_keys(self):
        """یک بررسی مستقیم: خروجی _format_evidence نباید حاوی کلید خام (مثل 'ad_iframe_count') باشد."""
        raw_details = {"ad_iframe_count": 2, "ad_elements": 3, "total_blocks": 10}
        formatted = _format_evidence(raw_details)
        assert "ad_iframe_count" not in formatted
        assert "تعداد iframe تبلیغاتی" in formatted
