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

obi_change = []
ofi_change = []

for i in range(3, len(data)):
    obi_change.append(data[i]["obi"] - data[i-3]["obi"])
    ofi_change.append(data[i]["ofi"] - data[i-3]["ofi"])

obi_sorted = sorted(obi_change)
ofi_sorted = sorted(ofi_change)

obi_low = obi_sorted[int(len(obi_sorted) * 0.10)]
obi_high = obi_sorted[int(len(obi_sorted) * 0.90)]

ofi_low = ofi_sorted[int(len(ofi_sorted) * 0.10)]
ofi_high = ofi_sorted[int(len(ofi_sorted) * 0.90)]

buy_idx = []
sell_idx = []

for j in range(len(obi_change)):
    if obi_change[j] >= obi_high and ofi_change[j] >= ofi_high:
        buy_idx.append(j + 3)

    if obi_change[j] <= obi_low and ofi_change[j] <= ofi_low:
        sell_idx.append(j + 3)

print("BUY signals =", len(buy_idx))
print("SELL signals =", len(sell_idx))
print("=== HORIZON TEST ===")

for h in [1, 3, 5]:
    buy = []
    sell = []

    for i in buy_idx:
        if i + h < len(data):
            buy.append((data[i+h]["mid"] / data[i]["mid"] - 1) * 100)

    for i in sell_idx:
        if i + h < len(data):
            sell.append((data[i+h]["mid"] / data[i]["mid"] - 1) * 100)

    print("H", h,
          "BUY N=", len(buy),
          "BUY AVG=", round(statistics.mean(buy), 5) if buy else "NA",
          "SELL N=", len(sell),
          "SELL AVG=", round(statistics.mean(sell), 5) if sell else "NA")