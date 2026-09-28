# Feasibility Audit V1

This is a deterministic, read-only SOL market-economics audit. It does not modify input datasets, collectors, existing models, strategy code, or trading code.

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

1. Unix epoch seconds: interpreted as Unix UTC.
2. Unix epoch milliseconds: interpreted as Unix UTC.
3. Datetimes with an explicit timezone/offset: interpreted using that embedded offset.
4. Naive datetimes such as \`YYYY-MM-DD HH:MM:SS.fff\`: interpreted with the host OS local-time rules via \`time.mktime()\`.

The report records:

- host local timezone name;
- timestamp interpretation kinds found in each dataset;
- timezone status.

This local-datetime rule assumes the files were created by the same local collector environment. If the collector timezone cannot be established, the report marks the case \`TIMEZONE_UNCERTAIN\`; signal alignment must then be treated as a limitation rather than silently guessing UTC.

Tradeflow Unix epochs are therefore converted to UTC first, while market naive timestamps are converted from the collector host's local clock to the same absolute Unix timeline.

## Canonical market source

Both \`market_data_v2.csv\` and \`market_data_v3.csv\` are audited independently.

Canonical selection does not use row count as the primary criterion.

Selection hierarchy:

1. executable SOL time/bid/ask schema must exist;
2. newer temporal end coverage;
3. longer temporal coverage;
4. lower P95 sampling interval;
5. lower invalid bid/ask rate;
6. valid SOL executable row count only as the final tie-breaker.

The report includes both datasets' start/end, duration, valid SOL rows, executable validity, continuity and schema information, plus the exact selection reason.

## Horizons

Only these horizons are tested:

\`300, 900, 1800, 3600, 7200, 14400, 21600, 43200, 86400\` seconds.

No other opportunity horizon is added.

## Canonical signal timeline

When \`tradeflow_features_v3.csv\` exists:

- \`signal_time\` = tradeflow timestamp.
- \`market_snapshot_time\` = canonical market snapshot selected for the signal.
- \`entry_time\` is kept conceptually separate from \`signal_time\`.
- \`entry_snapshot_time\` is the first market snapshot with \`market_time >= signal_time\`.
- \`exit_time\` is the last market snapshot at or before \`signal_time + horizon\` for the fixed-horizon baseline.

The alignment delay is exactly:

\`entry_snapshot_time - signal_time\`

The report provides mean, median, P90, P95, P99 and max, plus a fixed stale/delayed count for delays above 30 seconds. The 30-second flag is an audit diagnostic, not an optimized parameter.

## Long execution

For executable Long economics:

- ENTRY = ASK
- EXIT = future BID

Baseline gross mid-to-mid:

\`gross_mid = future_mid / entry_mid - 1\`

Gross after fee, before spread:

\`gross_after_fee = future_mid * (1-fee) / (entry_mid * (1+fee)) - 1\`

Executable gross after spread:

\`gross_after_spread = future_bid / entry_ask - 1\`

Net after fee plus spread:

\`net_fee_spread = future_bid * (1-fee) / (entry_ask * (1+fee)) - 1\`

Additional slippage is then applied as a fixed round-trip deduction for exactly 0, 5, 10, 20 and 30 bps.

## Fee decomposition

Default:

\`fee_side = 0.0035\`

This is a configurable assumption, not a verified current-market truth.

The exact two-sided fee-only factor for a flat-price round trip is:

\`(1-fee)/(1+fee)\`

Therefore the exact flat-price fee drag is:

\`1 - (1-fee)/(1+fee)\`

For \`fee_side=0.0035\`, this is about 0.69756%, not 0.70% exactly.

The CSV field \`fee_cost_flat_pct\` represents this exact flat-price fee drag. It is not the per-observation PnL fee loss.

Spread is not reported as a simple subtraction of two returns. The executable ASK-to-BID return is the primary spread-aware quantity. The report also gives entry spread, exit spread, and an exact multiplicative factor drag:

\`1 - (1 + gross_after_spread) / (1 + gross_mid)\`

This is a factor-equivalent execution drag, not an additive return subtraction.

## Short execution

No short result is manufactured.

With ordinary bid/ask snapshots alone, short opening/closing mechanics, borrow/margin availability and executable fills are not established. Therefore:

\`SHORT = INCONCLUSIVE\`

unless the supplied data itself proves executable short mechanics.

## Baseline sampling and dependence

Every valid canonical market snapshot is evaluated for each requested horizon.

This is an opportunity-density analysis, not a portfolio backtest.

Raw \`N\` is reported but is explicitly **not** treated as an independent-sample count. With overlapping horizons, especially 4h, 6h, 12h and 24h, adjacent observations can be strongly dependent.

The report therefore uses four consecutive chronological time blocks for stability checks and does not make statistical-proof claims from raw \`N\`.

## Time blocks

The full canonical market coverage is divided into four consecutive chronological blocks.

For every horizon and the five requested slippage sensitivities, each block reports:

- N
- gross measures
- net mean
- net median
- win rate
- quantiles

No random shuffle is used.

## Volatility regimes

When sufficient market data exists, a simple non-ML regime proxy is calculated from 300-second trailing realized log-return volatility.

The distribution is split into LOW, MEDIUM and HIGH empirical thirds.

This is descriptive regime analysis only. It is not a strategy, signal, threshold optimization, or parameter sweep.

## Oracle MFE / MAE

For each horizon and valid entry:

- MFE = maximum future BID relative to executable entry ASK within the horizon.
- MAE = minimum future BID relative to executable entry ASK within the horizon.

Only snapshots at or before the horizon end are included. This is an opportunity-existence diagnostic, not a TP/SL test and not a strategy.

## Decision framework

Base sensitivity is 20 bps of additional slippage.

A horizon is:

### GO-FOR-FURTHER-RESEARCH

Only when all of these hold:

- raw N >= 100;
- net mean > 0 at 20 bps;
- all four time blocks have positive net mean at 20 bps;
- net mean is positive at 0, 5, 10 and 20 bps.

This is a research-gate label, not a statistical-significance claim.

### NO-GO

Only when:

- raw N >= 100; and
- all four time blocks have non-positive net mean at 20 bps.

### INCONCLUSIVE

All other cases, including:

- insufficient raw observations;
- positive mean concentrated in only one block;
- positive without slippage but negative at 10–20 bps;
- incomplete block coverage;
- unresolved timezone alignment.

## Limitations

Historical slippage is not inferred from thin air; it is represented only through the five requested sensitivity cases.

Quote snapshots do not prove executable fill size or market impact.

Large sampling gaps can reduce the number of valid horizon observations and can affect representativeness; the audit reports median/P90/P95/P99/max intervals so this can be assessed before interpretation.

Overlapping observations are intentionally retained for opportunity-density measurement. They must not be interpreted as independent trades.

No ML, signal model, threshold optimization, TP/SL optimization, live trading, order execution, or collector modification is performed.

## Outputs

When run locally from the repository root, the script creates only:

- \`research/feasibility_results.csv\`
- \`research/feasibility_report.txt\`

The input datasets are read-only.

Run:

\`\`\`
python research/feasibility_audit_v1.py
\`\`\`
