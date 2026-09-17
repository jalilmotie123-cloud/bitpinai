import csv
import statistics

data = []

with open("market_data.csv", encoding="utf-8-sig") as f:
    rows = csv.DictReader(f)

    for r in rows:
        if r["symbol"] == "SOL_USDT":
            data.append({
                "mid": float(r["mid"]),
                "obi": float(r["obi10"]),
                "ofi": float(r["ofi_norm"])
            })

print("SOL rows =", len(data))

obi_changes = []
ofi_changes = []
future_moves = []

for i in range(3, len(data) - 1):
    obi_change = data[i]["obi"] - data[i-3]["obi"]
    ofi_change = data[i]["ofi"] - data[i-3]["ofi"]
    future_move = (data[i+1]["mid"] / data[i]["mid"] - 1) * 100

    obi_changes.append(obi_change)
    ofi_changes.append(ofi_change)
    future_moves.append(future_move)

obi_low = sorted(obi_changes)[int(len(obi_changes) * 0.10)]
obi_high = sorted(obi_changes)[int(len(obi_changes) * 0.90)]

ofi_low = sorted(ofi_changes)[int(len(ofi_changes) * 0.10)]
ofi_high = sorted(ofi_changes)[int(len(ofi_changes) * 0.90)]

both_buy = []
both_sell = []

for i in range(len(future_moves)):
    oc = obi_changes[i]
    fc = ofi_changes[i]
    move = future_moves[i]

    if oc >= obi_high and fc >= ofi_high:
        both_buy.append(move)

    if oc <= obi_low and fc <= ofi_low:
        both_sell.append(move)

print("=== SOL OBI + OFI CHANGE ===")
print("BOTH POSITIVE N =", len(both_buy))
if both_buy:
    print("BOTH POSITIVE AVG =", round(statistics.mean(both_buy), 5))

print("BOTH NEGATIVE N =", len(both_sell))
if both_sell:
    print("BOTH NEGATIVE AVG =", round(statistics.mean(both_sell), 5))