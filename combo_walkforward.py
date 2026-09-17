import csv
import statistics

data = []

with open("market_data.csv", encoding="utf-8-sig") as f:
    for r in csv.DictReader(f):
        if r["symbol"] == "SOL_USDT":
            data.append({
                "mid": float(r["mid"]),
                "obi": float(r["obi10"]),
                "ofi": float(r["ofi_norm"])
            })

print("SOL rows =", len(data))

# ==========================================
# WALK-FORWARD TEST
# 4 sequential test windows
# ==========================================

n = len(data)
window = n // 5

results = []

for fold in range(1, 5):

    train_end = fold * window
    test_start = train_end
    test_end = (fold + 1) * window if fold < 4 else n

    train = data[:train_end]

    print()
    print("================================")
    print("FOLD", fold)
    print("TRAIN:", 0, "to", train_end - 1)
    print("TEST :", test_start, "to", test_end - 1)
    print("================================")

    # ------------------------------
    # TRAIN thresholds
    # ------------------------------

    obi_change = []
    ofi_change = []

    for i in range(3, len(train)):
        obi_change.append(train[i]["obi"] - train[i-3]["obi"])
        ofi_change.append(train[i]["ofi"] - train[i-3]["ofi"])

    obi_change.sort()
    ofi_change.sort()

    obi_low = obi_change[int(len(obi_change) * 0.10)]
    obi_high = obi_change[int(len(obi_change) * 0.90)]

    ofi_low = ofi_change[int(len(ofi_change) * 0.10)]
    ofi_high = ofi_change[int(len(ofi_change) * 0.90)]

    print("Thresholds:")
    print("OBI LOW =", round(obi_low, 6))
    print("OBI HIGH =", round(obi_high, 6))
    print("OFI LOW =", round(ofi_low, 6))
    print("OFI HIGH =", round(ofi_high, 6))

    # ------------------------------
    # TEST signals
    # ------------------------------

    buy_idx = []
    sell_idx = []

    for i in range(test_start, test_end):

        if i < 3:
            continue

        obi_ch = data[i]["obi"] - data[i-3]["obi"]
        ofi_ch = data[i]["ofi"] - data[i-3]["ofi"]

        if obi_ch >= obi_high and ofi_ch >= ofi_high:
            buy_idx.append(i)

        if obi_ch <= obi_low and ofi_ch <= ofi_low:
            sell_idx.append(i)

    print("BUY signals =", len(buy_idx))
    print("SELL signals =", len(sell_idx))

    # ------------------------------
    # Horizons
    # ------------------------------

    for h in [1, 3, 5]:

        buy = []
        sell = []

        for i in buy_idx:
            if i + h < test_end and i + h < n:
                x = (data[i+h]["mid"] / data[i]["mid"] - 1) * 100
                buy.append(x)

        for i in sell_idx:
            if i + h < test_end and i + h < n:
                x = (data[i+h]["mid"] / data[i]["mid"] - 1) * 100
                sell.append(x)

        if buy:
            buy_avg = statistics.mean(buy)
            buy_win = sum(x > 0 for x in buy) / len(buy) * 100
        else:
            buy_avg = 0
            buy_win = 0

        if sell:
            sell_avg = statistics.mean(sell)
            sell_win = sum(x < 0 for x in sell) / len(sell) * 100
        else:
            sell_avg = 0
            sell_win = 0

        print(
            "H", h,
            "| BUY N", len(buy),
            "AVG", round(buy_avg, 5),
            "WIN", round(buy_win, 2), "%",
            "| SELL N", len(sell),
            "AVG", round(sell_avg, 5),
            "WIN", round(sell_win, 2), "%"
        )

        results.append({
            "fold": fold,
            "h": h,
            "buy_avg": buy_avg,
            "buy_win": buy_win,
            "sell_avg": sell_avg,
            "sell_win": sell_win
        })

# ==========================================
# SUMMARY
# ==========================================

print()
print("================================")
print("WALK-FORWARD SUMMARY")
print("================================")

for h in [1, 3, 5]:

    r = [x for x in results if x["h"] == h]

    buy_avg = statistics.mean(x["buy_avg"] for x in r)
    buy_win = statistics.mean(x["buy_win"] for x in r)

    sell_avg = statistics.mean(x["sell_avg"] for x in r)
    sell_win = statistics.mean(x["sell_win"] for x in r)

    print()
    print("H", h)
    print("BUY AVG =", round(buy_avg, 5))
    print("BUY AVG WINRATE =", round(buy_win, 2), "%")
    print("SELL AVG =", round(sell_avg, 5))
    print("SELL AVG WINRATE =", round(sell_win, 2), "%")