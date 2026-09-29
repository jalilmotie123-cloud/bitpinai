# Selective 24h Feasibility Test V1

Research-only test for SOL_USDT. This branch does not place orders, call trading APIs, use ML, perform threshold sweeps, or alter existing collectors.

## Data and source policy

Primary market source:

\`market_data_v3.csv\`

If v3 is missing or fails the required executable schema, the script may fall back to \`market_data_v2.csv\` and reports that fallback explicitly.

Tradeflow source:

\`tradeflow_features_v3.csv\`

No Internet/API data is fetched by this test.

The test requires:

- market \`time, symbol, bid, ask, mid, obi10, ofi_norm\`
- tradeflow \`time\` and one fixed CVD-60s column from this predeclared compatibility order:
  1. \`cvd_rate_log_60s\`
  2. \`cvd_rate_60s\`
  3. \`cvd_60s\`

This fallback is schema compatibility only; it is not feature hunting.

## Timeline and leakage control

\`signal_time\` comes from \`tradeflow_features_v3.csv\`.

For feature values:

\`feature_snapshot_time = latest market snapshot at or before signal_time\`

so market features cannot use a future snapshot.

For execution:

\`entry_snapshot_time = first market snapshot at or after signal_time\`

and the alignment delay is:

\`entry_snapshot_time - signal_time\`

Only delays <= 30 seconds are considered usable. Larger delays are reported as alignment rejects; the 30-second value is a fixed data-quality rule, not an optimized parameter.

The 24h exit is:

\`last market snapshot at or before entry_time + 86400s\`

No future feature values are used.

## Fixed feature score

Exactly three features are used:

- OBI10
- OFI_norm
- CVD signed 60-second rate

Economic sign convention is fixed:

- positive pressure / imbalance / CVD -> Long
- negative pressure / imbalance / CVD -> Short

Each feature is standardized with mean and population standard deviation computed **only on the training period**.

\`score = (z_obi10 + z_ofi_norm + z_cvd60) / 3\`

The selection threshold is fixed before validation/holdout:

\`Long if score >= 1.50\`

\`Short if score <= -1.50\`

No threshold, feature sign, scaling, weighting or feature set is changed after seeing validation or holdout results.

## Temporal split

Aligned signal records are sorted chronologically and split:

- first 50% = train
- next 20% = validation
- final 30% = final holdout

Validation is sanity-only. It does not modify the fixed rule.

## Non-overlap

For the primary selected result, accepted entries must be at least 24 hours apart regardless of direction.

This reduces overlapping-horizon dependence. It does not prove statistical independence.

All-entry baselines are intentionally kept as descriptive overlapping baselines and must not be interpreted as independent observations.

## Execution economics

Long:

- entry = ASK
- exit = BID

Net after fee + spread uses exactly the convention of the prior feasibility audit:

\`exit_bid*(1-fee)/(entry_ask*(1+fee)) - 1\`

with:

\`fee_side = 0.0035\`

The 0.35% per-side fee is an assumption unless an authoritative project value overrides it.

For each trade:

\`trading_cost = gross_return - net_return\`

This is the exact return difference for that observation; spread is not added again.

Short is **not** considered executable from ordinary bid/ask quotes alone. Unless actual short/margin mechanics are proven in the supplied data, the short economic section is:

\`INCONCLUSIVE\`

and is excluded from the primary Net-EV aggregate.

The test also reports fixed additional slippage sensitivity at:

0, 5, 10, 20, 30 bps

These are assumptions, not observed historical slippage.

## Trade-level outputs

For selected executable trades the CSV records:

- entry_time
- exit_time
- side
- score
- gross_return
- trading_cost
- net_return
- MFE
- MAE

For Long:

\`MFE = max(future_bid / entry_ask - 1)\`

\`MAE = min(future_bid / entry_ask - 1)\`

For Short, the analogous executable formulas are present in code but are not used unless short mechanics are explicitly proven.

## Baselines

The report contains:

A. all eligible Long entries

B. selected Long entries

C. all eligible Short entries as a separate baseline only if the short mechanics issue is explicitly resolved; otherwise Short is INCONCLUSIVE

D. selected Long + selected Short when executable short mechanics are proven

With current default \`SHORT_EXECUTION_PROVEN=False\`, only executable Long selection contributes to the primary economic aggregate.

## Statistics

Reported where a valid sample exists:

- N
- mean net
- median net
- P25/P75
- P90
- win rate
- profit factor
- cumulative arithmetic P&L
- compounded return
- max drawdown for the non-overlapping selected sequence
- train / validation / holdout
- four chronological blocks
- fixed slippage sensitivity

Raw all-entry N is descriptive and not an independent-sample count.

## Deterministic gate

The gate is mechanical.

Minimum full signal coverage for a definitive result:

\`30 days\`

Minimum selected final-holdout observations:

\`5\`

Because the current dataset may be shorter, an otherwise positive result can remain \`INCONCLUSIVE\`.

### GO-FOR-FURTHER-RESEARCH

Requires all:

- at least 30 days full coverage;
- at least 5 selected executable holdout observations;
- positive holdout mean net;
- positive holdout cumulative arithmetic P&L;
- positive holdout median;
- positive mean through 0/5/10 bps sensitivity;
- positive selected result in at least 2 of 4 chronological blocks;
- selected result exceeds a direction-matched all-entry baseline by at least 0.25 percentage points.

### NO-GO

Requires a sufficiently sized/covered test and:

- non-positive holdout mean or cumulative arithmetic P&L, or
- non-positive holdout median.

### INCONCLUSIVE

Everything else, including:

- too few non-overlapping selected **Long-primary** holdout observations;
- instability across blocks;
- positive at 0 bps but not robust to fixed additional cost sensitivity;
- insufficient or ambiguous input data.

Short execution mechanics are evaluated separately. When `SHORT_EXECUTION_PROVEN=False`, Short is `NOT_EVALUATED` and does not affect the Long-primary gate.

A GO label means only that the fixed hypothesis is worth further confirmation. It does not mean profitability is proven and does not authorize live trading.

## Important limitation

The final holdout is evaluated exactly once by the fixed rule. The script contains no mechanism for changing the rule based on holdout results.

The test also does not establish statistical significance or independence for the underlying market-snapshot series. Its main dependence control is the 24-hour spacing of selected entries plus chronological block analysis.

## Files and outputs

Test script:

\`research/selective_24h_feasibility_v1.py\`

Tests:

\`research/test_selective_24h_feasibility_v1.py\`

Expected local outputs:

\`research/selective_24h_results.csv\`

\`research/selective_24h_report.txt\`

No existing input CSV is rewritten. The result files are task-owned outputs only.
