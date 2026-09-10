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

## وضعیت فعلی

همه‌ی ماژول‌ها (fetcher, parser, extractors, normalization, scoring,
reporting, webapp) پیاده‌سازی شده‌اند — این دیگر یک اسکلت خالی نیست.
آستانه‌های عددی شاخص‌ها از `config/settings.yaml` خوانده می‌شوند (نه
ثابت داخل کد)، طبق مقادیر مستندشده در `feature_dictionary_v3.md`.

استثنا: شاخص T6 (تازگی محتوا) یک مسیر ناتمام دارد — وقتی تاریخ از
JSON-LD schema پیدا می‌شود، فعلاً پردازش نمی‌شود و کد به جستجوی تاریخ
شمسی در متن صفحه می‌رود. این در فاز رفع باگ برطرف خواهد شد.

آنچه بعد از آن باقی می‌ماند، اعتبارسنجی تجربی است: مقایسه‌ی خروجی
چارچوب با داوری انسانی روی نمونه‌ای از صفحات فارسی واقعی (فعلاً
`data/sample_urls.csv` فقط آدرس‌های نمونه دارد، نه داده‌ی برچسب‌خورده).
