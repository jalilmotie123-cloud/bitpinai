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


## 2026-09-30 deep pagination run
Observed pagination output:
- Valid pages completed: 754
- Records received: 75,400
- Unique IDs: 75,394
- Duplicate IDs: 6
- First ID: 238,130
- Last ID: 162,736
- Page 755 request returned HTTP 401

Important: HTTP 401 at page 755 is an authentication failure, NOT evidence that the history ended. Therefore the current extraction is a partial authenticated snapshot and should not be labeled as the complete history.

Next safe continuation:
1. Refresh/re-authenticate the OCT24 Bearer token.
2. Resume pagination from page 755 (or recheck pages 754-755 to verify continuity).
3. Preserve the 75,400-record result; do not overwrite it.
4. Store subsequent pages as a new dated artifact and append the verification log.
