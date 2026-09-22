import hunter_ai_v3 as h
from bisect import bisect_right
from collections import Counter

t = h.load_tradeflow()
m = h.load_market()
mt = [x["time"] for x in m]

c = Counter()
n = 0

for x in t:
    z = x["_time"]
    j = bisect_right(mt, z) - 1

    if j < 0 or z - m[j]["time"] > h.MAX_MARKET_STALE_SEC:
        continue

    a = h.make_label(m, mt, m[j], m[j]["ask"])

    if a is None:
        continue

    c[a[4]] += 1
    n += 1

print("VALID=", n)
print("LABELS=", dict(c))

for k in ("BUY", "SELL", "HOLD"):
    print(
        k,
        "=",
        c[k],
        "RATE=%.2f%%" % (100.0 * c[k] / n if n else 0)
    )