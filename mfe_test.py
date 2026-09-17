import csv

MAX_HORIZONS = [5, 10, 20, 50]

data = []

with open("market_data.csv", encoding="utf-8-sig") as f:
    for r in csv.DictReader(f):
        if r["symbol"] == "SOL_USDT":
            data.append({
                "bid": float(r["bid"]),
                "ask": float(r["ask"]),
                "obi": float(r["obi10"]),
                "ofi": float(r["ofi_norm"])
            })

print("SOL rows =", len(data))

n = len(data)
window = n // 5

results = {}

for h in MAX_HORIZONS:
    results[h] = {
        "buy": [],
        "sell": []
    }

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

    signals = 0

    for i in range(train_end, test_end):

        if i < 3:
            continue

        obi_ch = data[i]["obi"] - data[i-3]["obi"]
        ofi_ch = data[i]["ofi"] - data[i-3]["ofi"]

        direction = 0

        if obi_ch >= obi_high and ofi_ch >= ofi_high:
            direction = 1

        elif obi_ch <= obi_low and ofi_ch <= ofi_low:
            direction = -1

        if direction == 0:
            continue

        signals += 1

        # Executable entry price
        if direction == 1:
            entry = data[i]["ask"]
        else:
            entry = data[i]["bid"]

        for h in MAX_HORIZONS:

            last_i = min(i + h, test_end - 1)

            if last_i <= i:
                continue

            max_move = None

            for j in range(i + 1, last_i + 1):

                if direction == 1:
                    # BUY: exit realistically at BID
                    move = data[j]["bid"] / entry - 1
                else:
                    # SELL: exit realistically at ASK
                    move = entry / data[j]["ask"] - 1

                if max_move is None or move > max_move:
                    max_move = move

            if direction == 1:
                results[h]["buy"].append(max_move)
            else:
                results[h]["sell"].append(max_move)

    print("")
    print("FOLD", fold, "| Signals =", signals)

print("")
print("========================================")
print("MFE RESULTS")
print("========================================")

for h in MAX_HORIZONS:

    buy = results[h]["buy"]
    sell = results[h]["sell"]

    print("")
    print("HORIZON =", h)

    if buy:
        buy_avg = sum(buy) / len(buy)
        buy_best = max(buy)
        buy_positive = sum(1 for x in buy if x > 0) / len(buy) * 100

        print(
            "BUY  N =", len(buy),
            "| AVG % =", round(buy_avg * 100, 4),
            "| BEST % =", round(buy_best * 100, 4),
            "| POSITIVE % =", round(buy_positive, 2)
        )

    if sell:
        sell_avg = sum(sell) / len(sell)
        sell_best = max(sell)
        sell_positive = sum(1 for x in sell if x > 0) / len(sell) * 100

        print(
            "SELL N =", len(sell),
            "| AVG % =", round(sell_avg * 100, 4),
            "| BEST % =", round(sell_best * 100, 4),
            "| POSITIVE % =", round(sell_positive, 2)
        )

print("")
print("========== FINISHED ==========")