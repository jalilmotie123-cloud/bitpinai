# Canonical SOL Collection V1

هدف این branch فقط ساخت یک pipeline مستقل برای جمع‌آوری داده canonical و قابل‌اتکا برای feasibility پژوهش 12h/24h است.

## Scope

این branch:

- فقط SOL_USDT را جمع‌آوری می‌کند.
- هیچ order یا transaction ارسال نمی‌کند.
- wallet لازم ندارد.
- ML، strategy، signal، TP/SL، backtest و threshold optimization ندارد.
- به \`scanner_v2.py\`، \`matches_collector_clean.py\` یا collector/model/strategy قدیمی دست نمی‌زند.
- هیچ داده واقعی را در Git commit نمی‌کند.

## Collector files

### 1. \`research/canonical_sol_market_collector_v1.py\`

Endpoint پیش‌فرض orderbook:

\`https://api.bitpin.org/api/v1/mth/orderbook/{symbol}/\`

این endpoint همان endpoint مورد استفاده collector قبلی repository است. URL از طریق \`--url-template\` قابل تنظیم و در خروجی startup چاپ می‌شود.

خروجی پیش‌فرض:

\`canonical_sol_market_v1.csv\`

نمونه‌برداری هدف:

2 ثانیه بین آغاز requestها. این target یک فرض عملیاتی برای جمع‌آوری داده است و برای سودسازی optimize نشده است.

فیلدهای اصلی:

\`request_sent_at_epoch_ms\`, \`received_at_epoch_ms\`, \`request_sent_at_iso\`, \`received_at_iso\`, \`response_latency_ms\`, \`symbol\`, bid/ask/mid/spread، depthهای 1/3/5/10، OBI و OFI.

اگر پاسخ API timestamp/server timestamp واقعی نداشته باشد:

\`server_timestamp_available=false\`

و timestamp محلی دریافت در \`received_at_*\` ثبت می‌شود.

هیچ timestamp ساختگی تولید نمی‌شود.

### Clock semantics

\`request_sent_at\` لحظه ارسال request است.

\`received_at\` لحظه دریافت response است.

\`response_latency_ms = received_at - request_sent_at\`.

\`received_at\` زمان محلی همان machine است و با timezone همان محیط ثبت می‌شود.

**\`received_at != exchange event time\`**

همچنین:

**orderbook snapshot != true event-time order book**

این collector فقط snapshot مشاهده‌شده از API را ثبت می‌کند. Snapshot به‌تنهایی نشان نمی‌دهد دقیقاً چه اتفاقی بین دو snapshot در order book رخ داده است.

### OFI

OFI فقط از دو snapshot متوالی SOL محاسبه می‌شود.

اگر:

- اولین snapshot باشد؛
- gap بیش از \`MAX_STATE_GAP_SEC=10\` ثانیه باشد؛
- یا درخواست/ارتباط شکست خورده و state قبلی قابل‌اعتماد نباشد؛

state قبلی reset می‌شود:

\`state_reset=1\`

و OFI آن snapshot به‌عنوان continuation از state قبلی محاسبه نمی‌شود؛ مقدار OFI در همان row صفر است و row با \`state_reset=1\` مشخص می‌شود.

Gapهای:

- \`normal\`: <= 10s
- \`warning\`: >10s و <=60s
- \`outage\`: >60s

برای data quality هستند و برای سودسازی/strategy optimization انتخاب نشده‌اند.

### OBI

برای depthهای 1/3/5/10:

\`OBI = (bid_volume - ask_volume) / (bid_volume + ask_volume)\`

حجم depthها از مجموع مقدار levelهای سمت bid و ask گرفته می‌شود.

## 2. \`research/canonical_sol_matches_collector_v1.py\`

Verified repository transport برای matches فعلاً REST polling است:

\`https://api.bitpin.org/api/v1/mth/matches/SOL_USDT/\`

خروجی پیش‌فرض:

\`canonical_sol_matches_v1.csv\`

این endpoint snapshot آخرین trades را برمی‌گرداند و collector با trade ID dedup می‌کند. ID دیده‌شده دوباره append نمی‌شود.

فیلدهای اصلی:

- trade ID
- \`event_time_epoch_ms\`
- \`event_time_iso\`
- \`received_at_epoch_ms\`
- \`received_at_iso\`
- request sent time
- latency
- price/base/quote/side
- session_id
- reconnect_count

\`event_time\` و \`received_at\` همیشه دو مفهوم جدا هستند.

### Transport / reconnect

این collector WebSocket نیست، بنابراین \`ping/pong\` برای آن قابل‌اعمال نیست و به‌صورت ساختگی پیاده‌سازی نشده است.

به‌جای آن:

- HTTP failures → backoff
- پس از recovery → reconnect count افزایش می‌یابد
- graceful shutdown با Ctrl+C
- dedup پایدار بر اساس trade ID

اگر در آینده یک WebSocket عمومی و verified برای همین endpoint پیدا شود، می‌توان collector جداگانه ساخت؛ این branch هیچ endpoint تأییدنشده‌ای را حدس نمی‌زند.

## 3. \`research/canonical_sol_tradeflow_v1.py\`

این builder فایل canonical matches را می‌خواند و:

\`tradeflow_features_canonical.csv\`

را به‌صورت deterministic می‌سازد.

پنجره‌ها دقیقاً:

30s, 60s, 120s, 300s, 600s

Featureها فقط:

- trade count
- base volume
- quote volume
- buy/sell base volume
- buy/sell quote volume
- CVD
- delta
- delta ratio
- intensity
- large trade ratio
- price return

### تعریف CVD

در این نسخه CVD برای هر window برابر با:

\`buy_quote_volume - sell_quote_volume\`

است؛ بنابراین rolling CVD و delta در این builder یک مفهوم واحد از quote-volume signed flow دارند.

### Large trade ratio

برای جلوگیری از هرگونه threshold tuning خارجی، threshold به‌صورت deterministic از همان window جاری گرفته می‌شود:

\`large trade = quote volume >= P90 همان window\`

این feature از future data بعد از timestamp جاری استفاده نمی‌کند؛ فقط trades موجود تا همان timestamp را در window می‌بیند.

## 4. \`research/data_manifest.py\`

Manifest builder به‌صورت read-only داده‌های collector-owned را audit می‌کند و:

\`research/data_manifest.json\`

را تولید می‌کند.

برای هر dataset گزارش می‌شود:

- file
- first timestamp
- last timestamp
- rows
- valid rows
- parser errors
- duplicates removed/detected
- median/P90/P95/P99/max gap
- warning/outage gaps
- reconnects
- state resets
- data quality flags

Manifest نیز پس از تولید به‌صورت atomic نوشته می‌شود.

## Unified schema

Schema versions:

\`\`\`
market_canonical_v1
matches_canonical_v1
tradeflow_canonical_v1
\`\`\`

نسخه schema در manifest ثبت می‌شود.

هیچ‌یک از این schemaها به معنی اثبات event-time دقیق بازار نیستند.

## Atomic writing / power-loss recovery

Collector-owned CSVها:

- header را فقط هنگام نبودن فایل ایجاد می‌کنند؛
- هر record را به‌صورت یک CSV line کامل write می‌کنند؛
- flush و fsync انجام می‌دهند؛
- در startup یک trailing incomplete line احتمالی را فقط در فایل متعلق به همان canonical collector repair می‌کنند.

فایل‌های legacy مانند:

\`market_data_v2.csv\`

\`market_data_v3.csv\`

\`matches_clean.csv\`

هرگز توسط این branch repair یا rewrite نمی‌شوند.

Tradeflow output با temp file + fsync + atomic \`os.replace\` ساخته می‌شود.

## Continuous operation

Market collector:

\`--interval-sec 2\`

به‌صورت continuous اجرا می‌شود و بعد از خطا دوباره request را با backoff ادامه می‌دهد.

Matches collector:

\`--poll-sec 5\`

به‌صورت continuous polling اجرا می‌شود و پس از خطای شبکه backoff دارد.

Auto-start سیستم‌عامل در این branch تغییر داده نشده است.

## Gap / continuity interpretation

Gap detection صرفاً data-quality است.

Thresholdها:

- normal <= 10s
- warning > 10s and <= 60s
- outage > 60s

برای market، \`MAX_STATE_GAP_SEC=10\` جداگانه باعث reset state OFI می‌شود.

این thresholdها برای انتخاب سودده‌ترین حالت یا strategy tuning انتخاب نشده‌اند.

## Tests

\`research/test_canonical_sol_collection_v1.py\`

حداقل این موارد را test می‌کند:

- OBI
- OFI
- timestamp parsing
- gap detection
- reconnect/state reset
- atomic append
- trade-ID dedup

این testها synthetic هستند و به هیچ dataset واقعی وابسته نیستند.

## Run examples

Market collector:

\`\`\`
python research/canonical_sol_market_collector_v1.py
\`\`\`

Matches collector:

\`\`\`
python research/canonical_sol_matches_collector_v1.py
\`\`\`

Tradeflow builder:

\`\`\`
python research/canonical_sol_tradeflow_v1.py
\`\`\`

Manifest:

\`\`\`
python research/data_manifest.py
\`\`\`

Tests:

\`\`\`
python research/test_canonical_sol_collection_v1.py
\`\`\`

## 30–60 day objective

این pipeline برای تولید یک dataset پیوسته و audit-able در بازه حداقل 30 روز و ترجیحاً 45–60 روز طراحی شده است.

هدف نهایی branch فقط این است که بعداً بتوانیم با timeline canonical:

\`signal_time -> market_snapshot_time -> entry_time -> exit_time\`

پرسش 12h/24h را آزمایش کنیم:

آیا در SOL قبل از وقوع حرکت، opportunity قابل‌اندازه‌گیری وجود دارد که بعد از هزینه واقعی بتواند Net-EV مثبت داشته باشد؟

این branch هیچ نتیجه‌ای درباره وجود یا عدم وجود چنین edgeای اعلام نمی‌کند؛ فقط زیرساخت اندازه‌گیری را می‌سازد.
