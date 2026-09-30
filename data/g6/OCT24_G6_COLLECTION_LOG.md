# OCT24 G6 Data Collection Log

## 2026-09-30 full historical backfill completed

The collector resumed at page 1177 with `--full` and reached the end of the API history.

Final observed results:
- Start page: 1177
- End page: 2383
- Pages requested in this run: 1207
- New records stored in this run: 120,468
- Total unique records stored after this run: 162,763
- Final page: 2383
- Final page count: 6
- Final page IDs: 6 through 1
- Git push: OK

Interpretation:
- The historical API scan reached ID 1 and the last page contained only 6 records.
- Therefore, at the time of this extraction, the API exposed no older pages beyond page 2383.
- Because new signals can be inserted at the front over time, this is a complete historical snapshot for this run, not a permanent fixed total for future runs.
- No OCT24 token or Authorization header was stored in the repository.

Next phase:
- Preserve this historical snapshot.
- Stop deep historical backfill.
- Join G6 records to Bitpin SOL market/trade data by time.
- Evaluate forward returns, spread, fees, slippage, and signal stability at multiple horizons.
