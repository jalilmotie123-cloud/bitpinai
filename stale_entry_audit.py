import hunter_ai_v3 as h
from bisect import bisect_right

trades = h.load_tradeflow()
market = h.load_market()
mt = [x["time"] for x in market]

n = 0
changed = 0
entry_moves = []

for x in trades:
    t = x["_time"]
    j = bisect_right(mt, t) - 1

    if j < 0:
        continue

    old = market[j]

    if t - old["time"] > h.MAX_MARKET_STALE_SEC:
        continue

    k = j + 1

    if k >= len(market):
        continue

    new = market[k]

    if new["time"] < t:
        continue

    move = (new["ask"] / old["ask"] - 1.0) * 100.0

    n += 1
    entry_moves.append(move)

    if abs(move) > 0.01:
        changed += 1

print("VALID=", n)
print("NEXT_QUOTE_CHANGE_>0.01PCT=", changed)

if entry_moves:
    entry_moves.sort()
    print("MEDIAN_ASK_MOVE=%.5f%%" % entry_moves[len(entry_moves)//2])
    print("MIN_ASK_MOVE=%.5f%%" % min(entry_moves))
    print("MAX_ASK_MOVE=%.5f%%" % max(entry_moves))