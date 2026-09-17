import requests
import time
import csv
import os
from datetime import datetime

SYMBOLS = [
    "BTC_USDT", "ETH_USDT", "XRP_USDT",
    "SOL_USDT", "BNB_USDT", "DOGE_USDT",
    "ADA_USDT", "XAUT_USDT"
]

URL = "https://api.bitpin.org/api/v1/mth/orderbook/"
FILE = "market_data.csv"

previous = {}

if not os.path.exists(FILE) or os.path.getsize(FILE) == 0:
    with open(FILE, "w", newline="") as f:
        csv.writer(f).writerow([
            "time", "symbol", "bid", "ask", "mid",
            "spread_pct", "obi10", "ofi_norm",
            "bid10", "ask10"
        ])

while True:
    for symbol in SYMBOLS:
        try:
            d = requests.get(URL + symbol + "/", timeout=10).json()

            bid = float(d["bids"][0][0])
            ask = float(d["asks"][0][0])

            bid_vol = float(d["bids"][0][1])
            ask_vol = float(d["asks"][0][1])

            bid10 = sum(float(x[1]) for x in d["bids"][:10])
            ask10 = sum(float(x[1]) for x in d["asks"][:10])

            depth = bid10 + ask10

            obi10 = (bid10 - ask10) / depth if depth else 0
            mid = (bid + ask) / 2
            spread_pct = (ask - bid) / bid * 100

            ofi = 0.0

            if symbol in previous:
                pb, pa, pbv, pav = previous[symbol]

                if bid > pb:
                    ofi += bid_vol
                elif bid < pb:
                    ofi -= pbv

                if ask < pa:
                    ofi += ask_vol
                elif ask > pa:
                    ofi -= pav

            ofi_norm = ofi / depth if depth else 0

            previous[symbol] = (bid, ask, bid_vol, ask_vol)

            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            with open(FILE, "a", newline="") as f:
                csv.writer(f).writerow([
                    now,
                    symbol,
                    bid,
                    ask,
                    mid,
                    round(spread_pct, 6),
                    round(obi10, 6),
                    round(ofi_norm, 6),
                    bid10,
                    ask10
                ])

            print(
                symbol,
                "MID", round(mid, 6),
                "SPREAD", round(spread_pct, 4),
                "OBI", round(obi10, 3),
                "OFI", round(ofi_norm, 4)
            )

        except Exception as e:
            print(symbol, "ERROR", e)

        time.sleep(2)

    print("-" * 60)
    time.sleep(5)