# Feasibility Audit V1

Deterministic, read-only SOL market-economics audit. Existing datasets, collectors, models, strategy code and trading code are not modified.

## Inputs

The script reads these local files when present:

- \`market_data_v2.csv\`
- \`market_data_v3.csv\`
- \`matches_clean.csv\`
- \`tradeflow_features_v3.csv\`

Missing files are reported explicitly. Missing values are never fabricated or filled by inference.

For files without a symbol column, the report states that the file is treated as a SOL-specific project file. Market files are filtered explicitly to SOL symbols.

## Timestamp methodology

Timestamp parsing distinguishes:

1. Unix epoch seconds: Unix UTC.
2. Unix epoch milliseconds: Unix UTC.
3. Datetimes with an explicit offset/timezone: the embedded offset.
4. Naive datetimes such as \`YYYY-MM-DD HH:MM:SS.fff\`: the host OS local timezone using \`datetime.timestamp()\`.

The report records the host local timezone name/details and the timestamp interpretation kinds found in each dataset.

This assumes naive collector timestamps were produced in the same local timezone as the machine running the audit. If that cannot be established, timezone/alignment is a limitation and must be treated as \`TIMEZONE_UNCERTAIN\`; UTC is never silently assumed for naive timestamps.

The data audit checks the **original file order before sorting** and reports both \`original_timestamp_ordering\` and \`original_timestamp_inversions\`. Calculations then use sorted chronological timestamps.

## Canonical market source

Both market files are audited independently.

Canonical selection is deterministic and does **not** choose the file with the most rows by default. The hierarchy is:

1. executable SOL bid/ask validity share;
2. usable schema;
3. newest end-time coverage;
4. longer coverage and better continuity;
5. lower invalid bid/ask rate;
6. valid row count only as the final tie-breaker.

The report explicitly writes:

\`CANONICAL_SOURCE=<file>\`

and

\`SELECTION_REASON=<deterministic hierarchy>\`

It also reports each market file's valid SOL rows, executable share, start/end, duration, median interval and P95 interval.

## Horizons

Only these horizons are evaluated:

\`300, 900, 1800, 3600, 7200, 14400, 21600, 43200, 86400\` seconds.

No other opportunity horizon is added.

## Canonical signal timeline

When \`tradeflow_features_v3.csv\` exists:

- \`signal_time\` = tradeflow timestamp.
- \`market_snapshot_time\` = canonical market snapshot used for alignment.
- \`entry_snapshot_time\` = first canonical market snapshot with \`market_time >= signal_time\`.
- \`entry_time\` remains conceptually distinct from \`signal_time\`.
- \`exit_time\` = last canonical market snapshot at or before \`signal_time + horizon\` for the fixed-horizon baseline.

The alignment delay is exactly:

\`entry_snapshot_time - signal_time\`

The report provides mean, median, P90, P95, P99 and max, plus a fixed audit count for delays over 30 seconds. The 30-second flag is diagnostic, not optimized.

## Long execution and cost decomposition

Long execution:

- ENTRY = ASK
- EXIT = future BID

A. Gross mid:

\`gross_mid = exit_mid / entry_mid - 1\`

B. Gross after fee, before spread:

\`gross_after_fee = exit_mid * (1-fee) / (entry_mid * (1+fee)) - 1\`

C. Executable before fee:

\`gross_after_spread = exit_bid / entry_ask - 1\`

D. Net after fee + spread:

\`net_fee_spread = exit_bid * (1-fee) / (entry_ask * (1+fee)) - 1\`

E. Net after additional slippage:

\`D - slippage_bps/10000\`

The five and only five sensitivity cases are:

\`0, 5, 10, 20, 30 bps\`

Slippage is an assumption for sensitivity analysis, not observed historical slippage.

## Fee model

Default:

\`fee_side = 0.0035\`

This is a configurable assumption, not verified current-market truth.

Exact two-sided fee-only factor for flat price:

\`(1-fee)/(1+fee)\`

Exact flat-price fee drag:

\`1-(1-fee)/(1+fee)\`

For 0.0035 per side, the exact flat-price drag is about 0.69756%.

The CSV field \`fee_cost_flat_pct\` is this exact flat-price drag. It is not presented as a per-observation PnL loss.

Spread is not represented by subtracting one return from another as an “exact cost”. The primary executable quantity is the ASK-to-future-BID return. The report separately records entry spread, exit spread and the exact multiplicative factor drag:

\`1 - (1 + gross_after_spread) / (1 + gross_mid)\`

## Baseline dependence

Every valid canonical market snapshot is evaluated.

Raw \`N\` is reported but is **not an independent-sample count**. Overlapping observations can be strongly correlated, particularly at 4h, 6h, 12h and 24h.

The audit does not make statistical-significance or statistical-proof claims from raw N alone. Four chronological time blocks are reported to expose stability.

## Performance / MFE / MAE

MFE/MAE uses a monotonic-deque sliding-window implementation.

For each horizon, the algorithm is approximately O(N):

- one deque tracks the maximum future BID;
- one deque tracks the minimum future BID;
- the right edge only moves forward;
- expired indices are removed from the front.

Definitions are unchanged:

\`MFE = max(future_bid / entry_ask - 1)\`

\`MAE = min(future_bid / entry_ask - 1)\`

An internal deterministic self-check compares the deque implementation against a brute-force reference on a small synthetic market before any input dataset is processed. A mismatch stops execution.

The fixed-horizon lookup is also implemented with a monotonic right pointer, avoiding repeated full searches per entry.

## Volatility regimes

Regime is descriptive only and is based on **trailing 300-second realized log-return volatility**, not future price movement or executable return.

To avoid look-ahead from regime cutpoints, empirical thirds for each chronological block are calibrated only from the immediately preceding block:

- block 1: UNKNOWN (no prior block exists);
- block 2: thirds from block 1;
- block 3: thirds from block 2;
- block 4: thirds from block 3.

Only LOW, MEDIUM and HIGH are emitted as regime categories; block-1 observations are explicitly counted as unclassified rather than assigned a guessed regime.

## Short execution

No short result is fabricated.

Bid/ask quotes alone do not establish borrow, margin, short-entry availability, close mechanics or executable short fills.

Therefore:

\`SHORT = INCONCLUSIVE\`

unless supplied data itself proves executable short mechanics.

## Decision framework

Base decision sensitivity is 20 bps additional slippage.

Minimum raw N for a non-INCONCLUSIVE result is 100, but N is not an independent-sample count.

GO-FOR-FURTHER-RESEARCH requires all of:

- raw N >= 100;
- positive net mean at 20 bps;
- positive net mean in all four chronological blocks at 20 bps;
- positive net mean at 0, 5, 10 and 20 bps.

Therefore a result that is positive without slippage but turns negative at 10–20 bps is not GO.

A result with only one positive time block is not GO.

NO-GO requires:

- raw N >= 100; and
- non-positive net mean in all four blocks at the 20 bps sensitivity.

All other cases are INCONCLUSIVE.

These are research-gate labels, not statistical significance claims.

## Data-audit fields

For every dataset the report provides, where applicable:

- row count;
- SOL row count;
- start/end;
- duration;
- duplicate timestamps;
- duplicate IDs;
- missing values;
- invalid prices;
- invalid bid/ask;
- original timestamp ordering;
- original timestamp inversions;
- median interval;
- P90/P95/P99 interval;
- maximum gap;
- timestamp interpretation/timezone status.

## Limitations

Quote snapshots do not prove executable fill size or market impact.

Historical slippage is not known unless the supplied data directly contains it; this audit therefore uses only the five fixed sensitivity cases.

Large sampling gaps can reduce valid horizon observations and affect representativeness; the audited gap distribution must be considered before interpretation.

Overlapping baseline observations are opportunity-density observations, not independent trades.

No ML, signal model, threshold sweep, TP/SL optimization, live trading, order execution, or collector modification is performed.

## Progress output

The script prints progress for:

- dataset loading/auditing;
- canonical source;
- each horizon start;
- MFE/MAE completion;
- each horizon completion;
- CSV output;
- text-report output.

Example:

\`[1/9] HORIZON=300s START\`

\`[1/9] HORIZON=300s MFE/MAE DONE N=...\`

\`[1/9] HORIZON=300s DONE N=...\`

## Outputs

A local run creates only:

- \`research/feasibility_results.csv\`
- \`research/feasibility_report.txt\`

The four input datasets are read-only.

Run from the repository root:

\`\`\`
python research/feasibility_audit_v1.py
\`\`\`
