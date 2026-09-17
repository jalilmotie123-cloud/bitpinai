import csv
import statistics

data = []

with open("market_data.csv", encoding="utf-8-sig") as f:
    rows = csv.DictReader(f)

    for r in rows:
        if r["symbol"] == "SOL_USDT":
            data.append({
                "mid": float(r["mid"]),
                "ofi": float(r["ofi_norm"])
            })

print("SOL rows =", len(data))

changes = []
future_moves = []

for i in range(3, len(data) - 1):
    ofi_change = data[i]["ofi"] - data[i-3]["ofi"]
    future_move = (data[i+1]["mid"] / data[i]["mid"] - 1) * 100

    changes.append(ofi_change)
    future_moves.append(future_move)

pairs = list(zip(changes, future_moves))
sorted_changes = sorted(changes)

low = sorted_changes[int(len(sorted_changes) * 0.10)]
high = sorted_changes[int(len(sorted_changes) * 0.90)]

bottom = [move for change, move in pairs if change <= low]
top = [move for change, move in pairs if change >= high]

print("=== SOL OFI CHANGE TEST ===")
print("BOTTOM 10% N =", len(bottom))
print("BOTTOM AVG =", round(statistics.mean(bottom), 5))
print("TOP 10% N =", len(top))
print("TOP AVG =", round(statistics.mean(top), 5))