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

    if j < 0:
        continue

    if z - m[j]["time"] > h.MAX_MARKET_STALE_SEC:
        continue

    k = j + 1

    if k >= len(m):
        continue

    a = h.make_label(m, mt, m[j], m[j]["ask"])
    b = h.make_label(m, mt, m[k], m[k]["ask"])

    if a is None or b is None:
        continue

    if a[0] != b[0]:
        c[(a[4], b[4])] += 1
        n += 1

print("CHANGED=", n)
print("BREAKDOWN=", dict(c))