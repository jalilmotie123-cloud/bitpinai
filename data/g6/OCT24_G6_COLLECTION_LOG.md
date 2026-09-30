# OCT24 G6 Data Collection Log

## Repository
- Repository: `jalilmotie123-cloud/bitpinai`
- Snapshot branch: `g6-snapshot-20260929`
- Purpose: preserve raw OCT24 G6 signal-history evidence and subsequent extraction/validation results.
- Secrets policy: Bearer/API tokens are NEVER stored in this repository.

## Existing 2026-09-29 snapshot
- Raw storage file: `data/g6/oct24_g6_raw_storage_20260929.json`
- Records captured: 60,000
- Unique IDs: 59,981
- Duplicate records: 19
- SHA-256: `2d54e16c37ebcf4e0de23bc52c59ae2c52a86571ecf6e60eca2356b36de2eb23`

## 2026-09-30 API verification
Endpoint:
`GET https://api.oct24.ai/v1/g6/signals/history?page=1&limit=100`

Observed result:
- HTTP_STATUS = 200
- SUCCESS = true
- ITEMS_COUNT = 100
- FIRST_ID = 238128
- LAST_ID = 238029

This confirms that the user's current authenticated Bearer token successfully accesses the G6 history endpoint and that page 1 returns 100 records.

## Next extraction step
The next run is intended to paginate through the history endpoint and record:
- total pages
- total records extracted
- unique IDs
- duplicate count
- first ID
- last ID

## Continuity rule
Subsequent OCT24 G6 extraction results should be appended as dated logs and/or data artifacts under `data/g6/`. Existing raw snapshots must not be overwritten. Tokens, cookies, Authorization headers, and other credentials must never be committed.
