# G6 Data Status — 2026-09-30

## Repository
- Repository: `jalilmotie123-cloud/bitpinai`
- Target branch: `main`
- Date: 2026-09-30

## Data currently verified on the local collector
The latest local G6 collector state reported:
- Total unique stored records: 238,236
- New records in the latest run: 75,473
- Files: 46 JSONL files (`g6_signals_000001.jsonl` … `g6_signals_000046.jsonl`)
- First ID seen in storage: 238,238
- Last ID seen in storage: 162,646
- Pages requested: 756
- Token stored: false
- Latest collector update: 2026-09-30T13:27:06Z

## Independent full-scan audit
- Rows: 238,236
- Unique IDs: 238,236
- Duplicate rows: 0
- Duplicate ID values: 0
- Minimum ID: 1
- Maximum ID: 238,238
- Missing ID values: 132848, 175711
- SignalType: Gold 119,551; Silver 118,685
- ResultType: TP 132,593; SL 105,643
- Earliest openedAt: 2026-04-16T18:28:14.542Z
- Latest openedAt: 2026-09-30T13:18:06.935Z

## Preset audit
- Low Risk: 234,266 total; TP 130,476; SL 103,790; TP rate 55.696%
- High Risk: 3,038 total; TP 1,514; SL 1,524; TP rate 49.835%
- Less Risk: 798 total; TP 511; SL 287; TP rate 64.035%
- Default: 133 total; TP 92; SL 41; TP rate 69.173%
- Maximum: 1 total; SL 1

## Win-rate calibration audit
Observed monotonic relationship between reported winRate bands and realized TP rate in the collected history:
- <50: n=418, actual TP=44.258%
- 50–52: n=11,253, actual TP=50.502%
- 52–54: n=10,140, actual TP=51.874%
- 54–56: n=32,750, actual TP=53.863%
- 56–58: n=58,372, actual TP=55.151%
- 58–60: n=63,082, actual TP=56.593%
- 60–65: n=61,785, actual TP=57.687%
- 65–70: n=420, actual TP=66.19%
- 70+: n=16, actual TP=75%

## Threshold audit
- >=55: n=211,995; TP=56.191%
- >=58: n=125,303; TP=57.167%
- >=60: n=62,221; TP=57.749%
- >=62: n=35,834; TP=58.352%
- >=65: n=436; TP=66.514% (very small sample)

Recent 30-day >=62:
- n=12,169
- TP=57.778%

## Walk-forward audit
8 folds, train 56 days / test 14 days, threshold selected at 62:
- OOS filtered n=35,131 (excluding empty folds)
- OOS TP=58.188%
- Baseline=56.087%
- Delta=+2.10 percentage points
- 7 positive non-empty folds
- Final fold is incomplete through 2026-09-30

## Economic fields
Collected averages:
- AVG TP percent: 65.8903
- Median TP percent: 65.39
- AVG LC percent: 12.4817
- Median LC percent: 12.47

These fields are treated as signal target/projection fields, not direct realized ROI, until their semantics are independently proven.

## Frontend/API investigation
Verified:
- `/v1/g6/signals/history` returns id, signalType, presetName, winRate, tpPercent, lcPercent, openedAt, resultType.
- `/v1/popups/active?page=G6` returned HTTP 200 with `{"success":true,"data":[]}`.
- Current inspected frontend chunks did not reveal a verified Gold/Silver -> Long/Short mapping.
- Mock data also contains the same `signalId` with both Gold and Silver examples, so that mock data cannot establish direction semantics.

## GitHub transfer status
This commit adds the raw G6 snapshot already present on branch `g6-snapshot-20260929`, its collection log, and this status record to `main`.

Important limitation:
The latest local split JSONL set containing all 238,236 records was not available as file bytes in this runtime, so those 46 JSONL files themselves are NOT claimed to have been transferred by this commit.
