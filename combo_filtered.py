import csv
import statistics

data = []

with open("market_data.csv", encoding="utf-8-sig") as f:
    for r in csv.DictReader(f):
        if r["symbol"] == "SOL_USDT":
            data.append({
                "mid": float(r["mid"]),
                "obi": float(r["obi10"]),
                "ofi": float(r["ofi_norm"]),
                "spread": float(r["spread_pct"])
            })

print("SOL rows =", len(data))

n = len(data)
window = n // 5

for fold in range(1, 5):

    train_end = fold * window
    test_end = (fold + 1) * window

    train = data[:train_end]
    test_start = train_end

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

    spreads = sorted(x["spread"] for x in train)
    spread_max = spreads[int(len(spreads) * 0.75)]

    buy_idx = []
    sell_idx = []

    for i in range(test_start, min(test_end, n)):

        if i < 3:
            continue

        obi_ch = data[i]["obi"] - data[i-3]["obi"]
        ofi_ch = data[i]["ofi"] - data[i-3]["ofi"]
        price_ch = data[i]["mid"] - data[i-3]["mid"]

        if (
            obi_ch >= obi_high
            and ofi_ch >= ofi_high
            and price_ch > 0
            and data[i]["spread"] <= spread_max
        ):
            buy_idx.append(i)

        if (
            obi_ch <= obi_low
            and ofi_ch <= ofi_low
            and price_ch < 0
            and data[i]["spread"] <= spread_max
        ):
            sell_idx.append(i)

    print("")
    print("FOLD", fold)
    print("TRAIN", train_end, "TEST", min(test_end, n))
    print("BUY signals =", len(buy_idx))
    print("SELL signals =", len(sell_idx))

    for h in [1, 3, 5]:

        buy = []
        sell = []

        for i in buy_idx:
            if i + h < n and i + h < test_end:
                ret = (data[i+h]["mid"] / data[i]["mid"] - 1) * 100
                buy.append(ret)

        for i in sell_idx:
            if i + h < n and i + h < test_end:
                ret = (data[i+h]["mid"] / data[i]["mid"] - 1) * 100
                sell.append(ret)

        buy_avg = statistics.mean(buy) if buy else None
        sell_avg = statistics.mean(sell) if sell else None

        buy_win = sum(x > 0 for x in buy)
        sell_win = sum(x < 0 for x in sell)

        print(
            "H", h,
            "BUY N=", len(buy),
            "AVG=", round(buy_avg, 5) if buy_avg is not None else "NA",
            "WINRATE=", round(buy_win / len(buy) * 100, 2) if buy else "NA"
        )

        print(
            "H", h,
            "SELL N=", len(sell),
            "AVG=", round(sell_avg, 5) if sell_avg is not None else "NA",
            "WINRATE=", round(sell_win / len(sell) * 100, 2) if sell else "NA"
        )