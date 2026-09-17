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

# =========================
# TRAIN / TEST SPLIT
# =========================

split = int(len(data) * 0.70)

train = data[:split]
test = data[split:]

print("TRAIN rows =", len(train))
print("TEST rows  =", len(test))

# =========================
# TRAIN THRESHOLDS
# =========================

obi_change_train = []
ofi_change_train = []

for i in range(3, len(train)):
    obi_change_train.append(train[i]["obi"] - train[i-3]["obi"])
    ofi_change_train.append(train[i]["ofi"] - train[i-3]["ofi"])

obi_sorted = sorted(obi_change_train)
ofi_sorted = sorted(ofi_change_train)

obi_low = obi_sorted[int(len(obi_sorted) * 0.10)]
obi_high = obi_sorted[int(len(obi_sorted) * 0.90)]

ofi_low = ofi_sorted[int(len(ofi_sorted) * 0.10)]
ofi_high = ofi_sorted[int(len(ofi_sorted) * 0.90)]

print("TRAIN thresholds:")
print("OBI LOW =", round(obi_low, 6))
print("OBI HIGH =", round(obi_high, 6))
print("OFI LOW =", round(ofi_low, 6))
print("OFI HIGH =", round(ofi_high, 6))

# =========================
# TEST
# Use 3 previous records across
# the train/test boundary
# =========================

test_start = split

buy_idx = []
sell_idx = []

for i in range(test_start, len(data)):

    if i < 3:
        continue

    obi_ch = data[i]["obi"] - data[i-3]["obi"]
    ofi_ch = data[i]["ofi"] - data[i-3]["ofi"]

    if obi_ch >= obi_high and ofi_ch >= ofi_high:
        buy_idx.append(i)

    if obi_ch <= obi_low and ofi_ch <= ofi_low:
        sell_idx.append(i)

print("TEST BUY signals =", len(buy_idx))
print("TEST SELL signals =", len(sell_idx))

# =========================
# HORIZON TEST
# =========================

print("=== CLEAN TRAIN / TEST HORIZON ===")

for h in [1, 3, 5]:

    buy = []
    sell = []

    for i in buy_idx:
        if i + h < len(data):
            result = (data[i+h]["mid"] / data[i]["mid"] - 1) * 100
            buy.append(result)

    for i in sell_idx:
        if i + h < len(data):
            result = (data[i+h]["mid"] / data[i]["mid"] - 1) * 100
            sell.append(result)

    print()
    print("H", h)

    if buy:
        wins = sum(1 for x in buy if x > 0)
        print("BUY N =", len(buy))
        print("BUY AVG =", round(statistics.mean(buy), 5))
        print("BUY WINRATE =", round(wins / len(buy) * 100, 2), "%")
        print("BUY BEST =", round(max(buy), 5))
        print("BUY WORST =", round(min(buy), 5))
    else:
        print("BUY N = 0")

    if sell:
        wins = sum(1 for x in sell if x < 0)
        print("SELL N =", len(sell))
        print("SELL AVG =", round(statistics.mean(sell), 5))
        print("SELL WINRATE =", round(wins / len(sell) * 100, 2), "%")
        print("SELL BEST =", round(max(sell), 5))
        print("SELL WORST =", round(min(sell), 5))
    else:
        print("SELL N = 0")