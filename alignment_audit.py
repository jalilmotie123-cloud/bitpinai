import hunter_ai_v3 as h
import statistics
from bisect import bisect_right

trades = h.load_tradeflow()
market = h.load_market()
mt = [x["time"] for x in market]

gaps = []
moves = []

for x in trades:
    t = x["_time"]
    j = bisect_right(mt, t) - 1

    if j < 0:
        continue

    m = market[j]
    gap = t - m["time"]

    if gap > 30:
        continue

    gaps.append(gap)

    k = bisect_right(mt, t) - 1
    move = (market[k]["mid"] / m["mid"] - 1.0) * 100.0
    moves.append(move)

print("SAMPLES=", len(gaps))
print("GAP_MEAN=%.3fs" % statistics.mean(gaps))
print("GAP_MEDIAN=%.3fs" % statistics.median(gaps))
print("GAP_MAX=%.3fs" % max(gaps))

print("PRE_SIGNAL_MOVE_MEAN=%.6f%%" % statistics.mean(moves))
print("PRE_SIGNAL_MOVE_MIN=%.6f%%" % min(moves))
print("PRE_SIGNAL_MOVE_MAX=%.6f%%" % max(moves))