import csv

FEE = 0.0035
MAX_HOLD = 10

CONFIGS = [
    (0.008, 0.004),
    (0.010, 0.005),
    (0.012, 0.006),
    (0.015, 0.0075),
    (0.010, 0.008),
    (0.012, 0.008),
]

data = []

with open("market_data.csv", encoding="utf-8-sig") as f:
    for r in csv.DictReader(f):
        if r["symbol"] == "SOL_USDT":
            data.append({
                "bid": float(r["bid"]),
                "ask": float(r["ask"]),
                "mid": float(r["mid"]),
                "obi": float(r["obi10"]),
                "ofi": float(r["ofi_norm"])
            })

print("SOL rows =", len(data))

n = len(data)
window = n // 5


def run_test(TP, SL):

    total_trades = 0
    total_wins = 0
    total_losses = 0
    total_timeouts = 0
    total_gross = 0.0
    total_net = 0.0

    print("")
    print("========================================")
    print("TP =", TP * 100, "%  SL =", SL * 100, "%")
    print("========================================")

    for fold in range(1, 5):

        train_end = fold * window
        test_end = min((fold + 1) * window, n)

        train = data[:train_end]

        obi_change = []
        ofi_change = []

        for i in range(3, len(train)):
            obi_change.append(train[i]["obi"] - train[i-3]["obi"])
            ofi_change.append(train[i]["ofi"] - train[i-3]["ofi"])

        obi_sorted = sorted(obi_change)
        ofi_sorted = sorted(ofi_change)

        obi_low = obi_sorted[int(len(obi_sorted) * 0.10)]
        obi_high = obi_sorted[int(len(obi_sorted) * 0.90)]

        ofi_low = ofi_sorted[int(len(ofi_sorted) * 0.10)]
        ofi_high = ofi_sorted[int(len(ofi_sorted) * 0.90)]

        fold_trades = 0
        fold_wins = 0
        fold_losses = 0
        fold_timeouts = 0
        fold_net = 0.0

        i = train_end

        while i < test_end - 1:

            if i < 3:
                i += 1
                continue

            obi_ch = data[i]["obi"] - data[i-3]["obi"]
            ofi_ch = data[i]["ofi"] - data[i-3]["ofi"]

            direction = 0

            if obi_ch >= obi_high and ofi_ch >= ofi_high:
                direction = 1

            elif obi_ch <= obi_low and ofi_ch <= ofi_low:
                direction = -1

            if direction == 0:
                i += 1
                continue

            # Realistic execution:
            # BUY enters at ASK
            # SELL/SHORT enters at BID

            if direction == 1:
                entry = data[i]["ask"]
            else:
                entry = data[i]["bid"]

            last_i = min(i + MAX_HOLD, test_end - 1)

            result = "TIMEOUT"
            gross = 0.0
            exit_i = last_i

            for j in range(i + 1, last_i + 1):

                if direction == 1:
                    exit_price = data[j]["bid"]
                    change = exit_price / entry - 1

                    hit_tp = change >= TP
                    hit_sl = change <= -SL

                else:
                    exit_price = data[j]["ask"]
                    change = entry / exit_price - 1

                    hit_tp = change >= TP
                    hit_sl = change <= -SL

                # If both happen between two samples,
                # use LOSS conservatively.
                if hit_tp and hit_sl:
                    result = "LOSS"
                    gross = -SL
                    exit_i = j
                    break

                if hit_tp:
                    result = "WIN"
                    gross = TP
                    exit_i = j
                    break

                if hit_sl:
                    result = "LOSS"
                    gross = -SL
                    exit_i = j
                    break

            if result == "TIMEOUT":

                if direction == 1:
                    exit_price = data[last_i]["bid"]
                    gross = exit_price / entry - 1
                else:
                    exit_price = data[last_i]["ask"]
                    gross = entry / exit_price - 1

                exit_i = last_i

            # Two-sided taker fee
            net = gross - (FEE * 2)

            fold_trades += 1
            total_trades += 1

            fold_net += net
            total_gross += gross
            total_net += net

            if result == "WIN":
                fold_wins += 1
                total_wins += 1

            elif result == "LOSS":
                fold_losses += 1
                total_losses += 1

            else:
                fold_timeouts += 1
                total_timeouts += 1

            # IMPORTANT:
            # Do not allow overlapping trades.
            i = exit_i + 1

        print(
            "FOLD", fold,
            "| Trades =", fold_trades,
            "| Wins =", fold_wins,
            "| Losses =", fold_losses,
            "| Timeout =", fold_timeouts,
            "| Net % =", round(fold_net * 100, 4)
        )

    print("")
    print("FINAL")
    print("Trades =", total_trades)
    print("Wins =", total_wins)
    print("Losses =", total_losses)
    print("Timeouts =", total_timeouts)

    if total_trades > 0:

        win_rate = total_wins / total_trades * 100
        fees = total_trades * FEE * 2

        print("Win Rate % =", round(win_rate, 2))
        print("Gross % =", round(total_gross * 100, 4))
        print("Fees % =", round(fees * 100, 4))
        print("NET % =", round(total_net * 100, 4))


for TP, SL in CONFIGS:
    run_test(TP, SL)

print("")
print("========== TEST FINISHED ==========")