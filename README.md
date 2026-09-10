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
[Scorer]       -> ترکیب وزنی شاخص‌ها -> امتیاز نهایی
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

این نسخه فقط **اسکلت پروژه** است. توابع اصلی هنوز پیاده‌سازی نشده‌اند
(علامت `# TODO` در هر فایل مشخص شده). پیاده‌سازی به‌صورت ماژول به ماژول
در مراحل بعدی انجام می‌شود.
