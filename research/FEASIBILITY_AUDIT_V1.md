# Feasibility Audit V1

Read-only SOL market-economics audit. Existing datasets, collectors, models and trading code are not modified.

## Inputs

The tool reads these local files when present:

- market_data_v2.csv
- market_data_v3.csv
- matches_clean.csv
- tradeflow_features_v3.csv

Missing files are reported explicitly. No missing data is imputed.

For the canonical market timeline, the available v2/v3 market dataset with the larger number of valid SOL bid/ask snapshots is selected. Both market files are still included in the data audit.

## Method

Only SOL rows are analyzed. Timestamps are interpreted as epoch seconds/milliseconds or UTC-naive ISO-like datetimes; the report records the UTC interpretation.

Only these horizons are evaluated:

300, 900, 1800, 3600, 7200, 14400, 21600, 43200, 86400 seconds.

Every valid canonical market snapshot with a future snapshot at the requested horizon is evaluated.

Long:
- ENTRY = ASK
- EXIT = future BID

Short is INCONCLUSIVE unless the supplied data proves executable short/margin mechanics. A bid/ask quote is not treated as proof that a short can actually be opened and closed.

## Cost decomposition

A. Gross only: future mid / entry mid - 1

B. Gross - Fee: two-sided fee applied to the mid-to-mid trade

C. Gross - Fee - Spread: executable ASK-to-future-BID return with the configured fee

D. Gross - Fee - Spread - Slippage: C minus the requested fixed slippage sensitivity.

Default fee is fee_side=0.0035 per side. It is an assumption, not a hard-coded claim about current market fees.

Slippage is not fabricated. Exactly five sensitivity cases are used: 0, 5, 10, 20 and 30 bps.

## Canonical timeline

When tradeflow_features_v3.csv exists, its timestamp is signal_time. The entry snapshot is the first canonical market snapshot at or after signal_time. Signal-to-entry delay is measured and reported.

Baseline opportunity analysis does not manufacture a signal; it evaluates every valid market snapshot directly.

## Stability

The market period is divided into four consecutive chronological blocks. No random shuffle is used.

A simple non-ML regime proxy is entry spread, split into LOW/MEDIUM/HIGH empirical thirds. This is descriptive only.

## Oracle analysis

For each horizon the tool reports MFE and MAE distributions. This is an opportunity-existence test, not a strategy, TP/SL test, or optimization.

## Validation / limitations

The report checks duplicate timestamps and IDs, missing values, invalid prices/bid/ask, ordering, sampling gaps, canonical alignment, future lookup ordering, horizon availability, and time-block density.

Historical slippage is unknown unless explicitly supplied, so slippage remains a sensitivity assumption. Overlapping baseline observations are retained because the question is whether market opportunity exists at all; chronological block results are supplied to expose instability.

No ML, signal model, threshold optimization, TP/SL optimization, live trading, order execution, or collector changes are performed.

## Outputs

When the local datasets are available:

- research/feasibility_results.csv
- research/feasibility_report.txt

Run from the repository root:

python research/feasibility_audit_v1.py

The script is deterministic and does not write to any input dataset.
