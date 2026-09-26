# چارچوب کمی‌سازی E-E-A-T برای صفحات وب فارسی

پروژه Proof of Concept برای استخراج و کمی‌سازی شاخص‌های E-E-A-T
(Experience, Expertise, Authoritativeness, Trustworthiness) از صفحات وب فارسی.

## معماری

```
URL ورودی
  |
  v
[Fetcher]      -> دانلود HTML خام
  |
  v
[Parser]       -> تبدیل HTML به ساختار DOM قابل پردازش
  |
  v
[Extractors]   -> استخراج ۱۹ شاخص در ۴ دسته (Experience, Expertise, Authority, Trust)
  |
  v
[Normalizer]   -> نرمال‌سازی شاخص‌ها به بازه [۰,۱]
  |
  v
[Scorer]       -> میانگین ساده شاخص‌ها در هر مؤلفه -> ترکیب وزنی ۴ مؤلفه -> امتیاز نهایی
  |
  v
[Reporter]     -> خروجی JSON / CSV
```

مرجع کامل شاخص‌ها، فرمول‌ها و منابع: فایل `feature_dictionary_v3.md` (جدا از این پروژه).

## نصب

```bash
pip install -r requirements.txt
```

نصب پکیج پایتونی `playwright` به‌تنهایی کافی نیست؛ خودِ مرورگر
(Chromium headless) که Playwright برای رندر صفحات جاوااسکریپتی
(مثل Next.js/React) استفاده می‌کند، باید جداگانه نصب شود:

```bash
python -m playwright install chromium
```

بدون این مرحله، هر تلاش برای رندر یک صفحه‌ی JS-rendered (چه به‌صورت
خودکار — تشخیص heuristic در fetcher — و چه با `--render-js`) با خطای
«Executable doesn't exist» شکست می‌خورد؛ به‌لطف مدیریت خطای موجود در
`fetcher/page_downloader.py`، این شکست برنامه را کرش نمی‌دهد اما
یعنی صفحه فقط با HTML خام (بدون اجرای جاوااسکریپت) تحلیل می‌شود.

## ساختار پوشه‌ها

- `fetcher/`       دانلود HTML از URL
- `parser/`        پارس HTML به DOM
- `extractors/`    ۴ ماژول استخراج شاخص (یکی برای هر مؤلفه E-E-A-T)
- `normalization/` نرمال‌سازی شاخص‌های خام
- `scoring/`       ترکیب وزنی و محاسبه امتیاز نهایی
- `reporting/`     تولید خروجی نهایی
- `config/`        فایل‌های وزن‌دهی (weights_equal.yaml, weights_ahp.yaml)
- `utils/`         توابع کمکی مشترک (تاریخ شمسی، تحلیل دامنه، و غیره)
- `data/`          نمونه URL های ورودی برای فاز ارزیابی
- `tests/`         تست واحد برای هر ماژول
- `webapp/`        رابط وب (Flask) برای اجرای تعاملی چارچوب
## وضعیت فعلی

همه‌ی ماژول‌ها (fetcher, parser, extractors, normalization, scoring,
reporting, webapp) پیاده‌سازی شده‌اند — این دیگر یک اسکلت خالی نیست.
آستانه‌های عددی شاخص‌ها از `config/settings.yaml` خوانده می‌شوند (نه
ثابت داخل کد)، طبق مقادیر مستندشده در `feature_dictionary_v3.md`.

شاخص T6 (تازگی محتوا) سه منبع تاریخ را به‌ترتیب امتحان می‌کند: JSON-LD
schema، تاریخ شمسی در متن صفحه، و در نهایت (اختیاری) تخمین از Wayback
Machine. این fallback آخر نیازمند دسترسی اینترنت به `archive.org` است
(ممکن است نیاز به فیلترشکن داشته باشد) و با
`external_data_sources.wayback_fallback_for_t6` در `config/settings.yaml`
قابل خاموش‌کردن است؛ اگر شبکه در دسترس نباشد یا خاموش باشد، رفتار
دقیقاً مثل قبل (`is_missing`) است — هیچ‌چیز کرش نمی‌کند.

آنچه بعد از آن باقی می‌ماند، اعتبارسنجی تجربی است: مقایسه‌ی خروجی
چارچوب با داوری انسانی روی نمونه‌ای از صفحات فارسی واقعی. راهنمای
کامل این فاز: `data/rating_rubric.md`. جریان کار:

```bash
python main.py --input data/sample_urls.csv --output results.csv
# نمره‌دهی به همان صفحات طبق data/rating_rubric.md در یک کپی از
# data/human_ratings_template.csv
python validate.py --framework-scores results.csv --human-ratings <فایل نمره‌های شما>
```

⚠️ این اعتبارسنجی با یک داور انجام می‌شود، نه چند داور مستقل — رجوع
به `feature_dictionary_v3.md` بخش «اعتبارسنجی تجربی» برای توضیح کامل
این محدودیت.
