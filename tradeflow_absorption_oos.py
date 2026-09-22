import csv
import io
import statistics
from bisect import bisect_right
from datetime import datetime

FEE = 0.0035
HORIZONS = (300, 600, 1200)

raw = open("market_data.csv", "rb").read()
raw = raw.replace(b"\x00", b"")

text = raw.decode("utf-8-sig")

rows = []

for x in csv.DictReader(io.StringIO(text)):
    if x.get("symbol") != "SOL_USDT":
        continue

    try:
        t = datetime.strptime(
            x["time"],
            "%Y-%m-%d %H:%M:%S"
        ).timestamp()

        bid = float(x["bid"])
        ask = float(x["ask"])

        if bid > 0 and ask > 0 and ask >= bid:
            rows.append((t, bid, ask))

    except Exception:
        pass

rows.sort()

times = [x[0] for x in rows]
bids = [x[1] for x in rows]
asks = [x[2] for x in rows]

print("MARKET CAPACITY TEST")
print("SOL_ROWS =", len(rows))

for h in HORIZONS:
    long_returns = []
    short_returns = []

    for i in range(len(rows)):
        j = bisect_right(times, times[i] + h) - 1

        if j <= i:
            continue

        long_r = (
            bids[j] * (1.0 - FEE)
            / (asks[i] * (1.0 + FEE))
            - 1.0
        ) * 100.0

        short_r = (
            bids[i] * (1.0 - FEE)
            / (asks[j] * (1.0 + FEE))
            - 1.0
        ) * 100.0

        long_returns.append(long_r)
        short_returns.append(short_r)

    print("")
    print("HORIZON =", h)

    if long_returns:
        print(
            "LONG  N=", len(long_returns),
            "MEDIAN=", round(statistics.median(long_returns), 5),
            "POSITIVE=", sum(x > 0 for x in long_returns),
            "POSITIVE_PCT=", round(
                sum(x > 0 for x in long_returns)
                / len(long_returns) * 100.0, 2
            )
        )

        print(
            "SHORT N=", len(short_returns),
            "MEDIAN=", round(statistics.median(short_returns), 5),
            "POSITIVE=", sum(x > 0 for x in short_returns),
            "POSITIVE_PCT=", round(
                sum(x > 0 for x in short_returns)
                / len(short_returns) * 100.0, 2
            )
        )
    else:
        print("NO_USABLE_DATA")

print("")
print("STATUS = CAPACITY_ONLY")