import hunter_ai_v3 as h
from bisect import bisect_right

trades = h.load_tradeflow()
market = h.load_market()
mt = [x["time"] for x in market]

old_n = 0
new_n = 0
changed = 0
net_diffs = []

for x in trades:
    t = x["_time"]
    j = bisect_right(mt, t) - 1

    if j < 0 or t - market[j]["time"] > h.MAX_MARKET_STALE_SEC:
        continue

    old_entry = market[j]

    k = j + 1
    while k < len(market) and market[k]["time"] < t:
        k += 1

    if k >= len(market):
        continue

    new_entry = market[k]

    if new_entry["time"] < t:
        continue

    old_label = h.make_label(
        market, mt, old_entry, old_entry["ask"]
    )

    new_label = h.make_label(
        market, mt, new_entry, new_entry["ask"]
    )

    if old_label is None or new_label is None:
        continue

    old_n += 1
    new_n += 1

    old_net = old_label[3]
    new_net = new_label[3]

    diff = new_net - old_net
    net_diffs.append(diff)

    if old_label[0] != new_label[0]:
        changed += 1

print("OLD_VALID=", old_n)
print("NEW_VALID=", new_n)
print("LABEL_CHANGED=", changed)

if net_diffs:
    print("MEAN_NET_CHANGE=%.5f%%" % (
        sum(net_diffs) / len(net_diffs)
    ))
    print("MIN_NET_CHANGE=%.5f%%" % min(net_diffs))
    print("MAX_NET_CHANGE=%.5f%%" % max(net_diffs))