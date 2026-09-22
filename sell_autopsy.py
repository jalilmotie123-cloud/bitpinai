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

    entry = m[j]

    label = h.make_label(
        m, mt, entry, entry["ask"]
    )

    if label is None:
        continue

    if label[4] != "SELL":
        continue

    n += 1

    exit_time = label[1]
    exit_bid = label[2]
    net = label[3]

    if net <= h.SL_NET_PCT:
        c["SL_REACHED"] += 1
    else:
        c["OTHER"] += 1

    c["TOTAL"] += 1

print("SELL_TOTAL=", n)
print("BREAKDOWN=", dict(c))

if n:
    print(
        "SL_RATE=%.2f%%" %
        (100.0 * c["SL_REACHED"] / n)
    )
    print(
        "OTHER_RATE=%.2f%%" %
        (100.0 * c["OTHER"] / n)
    )