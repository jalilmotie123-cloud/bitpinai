import csv
import math
from datetime import datetime, timedelta

DATA_FILE = "market_data_v2.csv"
FEE_PER_SIDE = 0.0035
ROUND_TRIP_FEE = FEE_PER_SIDE * 2
SIGNAL_LOOKBACK_SEC = 60
HORIZONS_SEC = [300, 600, 1200]
CONFIGS = [
    (0.008, 0.004),
    (0.010, 0.005),
    (0.012, 0.006),
    (0.015, 0.0075),
]
SYMBOLS = [
    "BTC_USDT", "ETH_USDT", "XRP_USDT", "SOL_USDT",
    "BNB_USDT", "DOGE_USDT", "ADA_USDT", "XAUT_USDT",
]
FOLDS = 5


def parse_time(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def load_data():
    by_symbol = {s: [] for s in SYMBOLS}
    with open(DATA_FILE, encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            symbol = r["symbol"]
            if symbol not in by_symbol:
                continue
            by_symbol[symbol].append({
                "time": parse_time(r["time"]),
                "bid": float(r["bid"]),
                "ask": float(r["ask"]),
                "mid": float(r["mid"]),
                "obi": float(r["obi10"]),
                "ofi": float(r["ofi_norm"]),
            })
    for symbol in by_symbol:
        by_symbol[symbol].sort(key=lambda x: x["time"])
    return by_symbol


def percentile(values, p):
    if not values:
        return None
    values = sorted(values)
    pos = (len(values) - 1) * p
    lo = int(math.floor(pos))
    hi = int(math.ceil(pos))
    if lo == hi:
        return values[lo]
    return values[lo] + (values[hi] - values[lo]) * (pos - lo)


def previous_index_at_or_before(data, start, target_time):
    lo, hi = 0, start + 1
    while lo < hi:
        mid = (lo + hi) // 2
        if data[mid]["time"] <= target_time:
            lo = mid + 1
        else:
            hi = mid
    return lo - 1


def thresholds(train):
    obi_changes = []
    ofi_changes = []
    for i in range(1, len(train)):
        prev_i = previous_index_at_or_before(train, i - 1, train[i]["time"] - timedelta(seconds=SIGNAL_LOOKBACK_SEC))
        if prev_i < 0:
            continue
        dt = (train[i]["time"] - train[prev_i]["time"]).total_seconds()
        if dt <= 0:
            continue
        obi_changes.append(train[i]["obi"] - train[prev_i]["obi"])
        ofi_changes.append(train[i]["ofi"] - train[prev_i]["ofi"])

    if len(obi_changes) < 20 or len(ofi_changes) < 20:
        return None

    return {
        "obi_low": percentile(obi_changes, 0.10),
        "obi_high": percentile(obi_changes, 0.90),
        "ofi_low": percentile(ofi_changes, 0.10),
        "ofi_high": percentile(ofi_changes, 0.90),
    }


def signal(data, i, th):
    if i < 1:
        return 0
    prev_i = previous_index_at_or_before(data, i - 1, data[i]["time"] - timedelta(seconds=SIGNAL_LOOKBACK_SEC))
    if prev_i < 0:
        return 0
    obi_ch = data[i]["obi"] - data[prev_i]["obi"]
    ofi_ch = data[i]["ofi"] - data[prev_i]["ofi"]
    if obi_ch >= th["obi_high"] and ofi_ch >= th["ofi_high"]:
        return 1
    if obi_ch <= th["obi_low"] and ofi_ch <= th["ofi_low"]:
        return -1
    return 0


def last_index_at_or_before(data, start, target_time):
    lo, hi = start, len(data)
    while lo < hi:
        mid = (lo + hi) // 2
        if data[mid]["time"] <= target_time:
            lo = mid + 1
        else:
            hi = mid
    return lo - 1


def max_drawdown(pnls):
    equity = 0.0
    peak = 0.0
    dd = 0.0
    for pnl in pnls:
        equity += pnl
        peak = max(peak, equity)
        dd = min(dd, equity - peak)
    return abs(dd)


def profit_factor(pnls):
    gross_profit = sum(x for x in pnls if x > 0)
    gross_loss = -sum(x for x in pnls if x < 0)
    if gross_loss == 0:
        return float("inf") if gross_profit > 0 else 0.0
    return gross_profit / gross_loss


def run_symbol(data, symbol, horizon_sec, tp, sl):
    n = len(data)
    if n < 100:
        return None

    fold_size = n // FOLDS
    all_pnls = []
    fold_rows = []

    for fold in range(1, FOLDS):
        train_end = fold * fold_size
        test_end = min((fold + 1) * fold_size, n) if fold < FOLDS - 1 else n
        train = data[:train_end]
        th = thresholds(train)
        if th is None:
            continue

        trades = 0
        wins = 0
        losses = 0
        timeouts = 0
        gross_total = 0.0
        net_total = 0.0
        pnls = []
        i = train_end

        while i < test_end - 1:
            direction = signal(data, i, th)
            if direction == 0:
                i += 1
                continue

            entry = data[i]["ask"] if direction == 1 else data[i]["bid"]
            deadline = data[i]["time"] + timedelta(seconds=horizon_sec)
            last_i = last_index_at_or_before(data, i + 1, deadline)
            if last_i >= test_end:
                last_i = test_end - 1
            if last_i <= i:
                i += 1
                continue

            result = "TIMEOUT"
            gross = 0.0
            exit_i = last_i

            for j in range(i + 1, last_i + 1):
                exit_price = data[j]["bid"] if direction == 1 else data[j]["ask"]
                change = exit_price / entry - 1 if direction == 1 else entry / exit_price - 1
                hit_tp = change >= tp
                hit_sl = change <= -sl

                if hit_tp and hit_sl:
                    result = "LOSS"
                    gross = -sl
                    exit_i = j
                    break
                if hit_tp:
                    result = "WIN"
                    gross = tp
                    exit_i = j
                    break
                if hit_sl:
                    result = "LOSS"
                    gross = -sl
                    exit_i = j
                    break

            if result == "TIMEOUT":
                exit_price = data[exit_i]["bid"] if direction == 1 else data[exit_i]["ask"]
                gross = exit_price / entry - 1 if direction == 1 else entry / exit_price - 1

            net = gross - ROUND_TRIP_FEE
            trades += 1
            gross_total += gross
            net_total += net
            pnls.append(net)
            all_pnls.append(net)

            if result == "WIN":
                wins += 1
            elif result == "LOSS":
                losses += 1
            else:
                timeouts += 1

            i = exit_i + 1

        fold_rows.append((fold, trades, wins, losses, timeouts, gross_total, net_total, max_drawdown(pnls)))

    trades = sum(x[1] for x in fold_rows)
    wins = sum(x[2] for x in fold_rows)
    losses = sum(x[3] for x in fold_rows)
    timeouts = sum(x[4] for x in fold_rows)
    gross = sum(x[5] for x in fold_rows)
    net = sum(x[6] for x in fold_rows)
    fees = trades * ROUND_TRIP_FEE

    return {
        "symbol": symbol,
        "horizon": horizon_sec,
        "tp": tp,
        "sl": sl,
        "trades": trades,
        "wins": wins,
        "losses": losses,
        "timeouts": timeouts,
        "gross": gross,
        "fees": fees,
        "net": net,
        "win_rate": wins / trades if trades else 0.0,
        "profit_factor": profit_factor(all_pnls),
        "max_drawdown": max_drawdown(all_pnls),
        "folds": fold_rows,
    }


def main():
    print("=== BitpinAI TP/SL economic walk-forward v2 ===")
    print("DATA:", DATA_FILE)
    print("FEE PER SIDE:", FEE_PER_SIDE * 100, "%")
    print("ROUND TRIP FEE:", ROUND_TRIP_FEE * 100, "%")
    print("HORIZONS:", HORIZONS_SEC)
    print("CONFIGS:", [(tp * 100, sl * 100) for tp, sl in CONFIGS])
    print("NOTE: no slippage is assumed; results are therefore before any extra slippage cost.")

    by_symbol = load_data()
    for symbol, rows in by_symbol.items():
        if rows:
            print(symbol, "rows =", len(rows), "from", rows[0]["time"], "to", rows[-1]["time"])

    results = []
    for symbol in SYMBOLS:
        data = by_symbol[symbol]
        for horizon in HORIZONS_SEC:
            for tp, sl in CONFIGS:
                result = run_symbol(data, symbol, horizon, tp, sl)
                if result is not None:
                    results.append(result)
                    print(
                        symbol,
                        "H=", horizon,
                        "TP=", round(tp * 100, 3),
                        "SL=", round(sl * 100, 3),
                        "TRADES=", result["trades"],
                        "NET%=", round(result["net"] * 100, 4),
                        "PF=", "INF" if math.isinf(result["profit_factor"]) else round(result["profit_factor"], 3),
                        "DD%=", round(result["max_drawdown"] * 100, 4),
                    )

    with open("tp_sl_results_v2.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow([
            "symbol", "horizon_sec", "tp", "sl", "trades", "wins", "losses",
            "timeouts", "gross", "fees", "net", "win_rate", "profit_factor", "max_drawdown"
        ])
        for r in results:
            w.writerow([
                r["symbol"], r["horizon"], r["tp"], r["sl"], r["trades"],
                r["wins"], r["losses"], r["timeouts"], r["gross"], r["fees"],
                r["net"], r["win_rate"], r["profit_factor"], r["max_drawdown"]
            ])

    print("RESULT FILE: tp_sl_results_v2.csv")
    print("=== TEST FINISHED ===")


if __name__ == "__main__":
    main()
