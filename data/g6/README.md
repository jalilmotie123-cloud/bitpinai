# OCT24 G6 Raw Data

این پوشه برای نگهداری **داده خام G6 OCT24** و snapshotهای قابل بازتولید است.

## Canonical format

- Raw export: JSON یا ترجیحاً JSONL
- نام‌گذاری پیشنهادی:
  - `g6_history_YYYYMMDD_HHMMSS_raw.json`
  - `g6_history_YYYYMMDD_HHMMSS_raw.jsonl`
- هر رکورد باید بدون تغییر محتوایی از API ذخیره شود.
- Bearer token / API key نباید داخل فایل داده، commit یا log ذخیره شود.

## Known schema

```
id
signalType
presetName
winRate
tpPercent
lcPercent
openedAt
resultType
```

## Current audit baseline

Snapshotهای فعلی ممیزی نشان داده‌اند که حدود 60,000 رکورد از History استخراج شده است. این repository باید از این به بعد محل نگهداری snapshotهای خام باشد تا تحلیل‌ها قابل بازگشت و قابل ردیابی بمانند.

## Integrity rule

برای هر snapshot، همراه داده یک manifest ثبت شود که شامل این موارد باشد:

- extraction timestamp
- page range
- row count
- unique ID count
- duplicate count
- min/max ID
- min/max openedAt
- API endpoint
- SHA-256 فایل

داده خام را قبل از integrity check یا analysis تغییر ندهید.
