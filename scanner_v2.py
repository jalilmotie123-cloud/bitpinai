# -*- coding: utf-8 -*-

"""
============================================================
scanner_v2.py
Bitpin Order Book Collector - Read Only

هدف:
- جمع‌آوری Order Book برای 8 نماد
- ثبت زمان با میلی‌ثانیه
- محاسبه OBI در سطوح 1/3/5/10
- محاسبه OFI بر اساس تغییر Best Bid/Ask
- ثبت تغییر قیمت و حجم Bid/Ask
- ذخیره در market_data_v2.csv

هیچ معامله‌ای انجام نمی‌شود.
============================================================
"""

import csv
import os
import time
from datetime import datetime

import requests


# ============================================================
# تنظیمات
# ============================================================

SYMBOLS = [
    "BTC_USDT",
    "ETH_USDT",
    "XRP_USDT",
    "SOL_USDT",
    "BNB_USDT",
    "DOGE_USDT",
    "ADA_USDT",
    "XAUT_USDT",
]

URL = "https://api.bitpin.org/api/v1/mth/orderbook/"

FILE = "market_data_v2.csv"

REQUEST_TIMEOUT = 10

# فاصله بین درخواست‌های هر نماد
SYMBOL_DELAY_SEC = 2.0

# فاصله اضافه بعد از تکمیل یک دور
ROUND_DELAY_SEC = 2.0


# ============================================================
# State
# ============================================================

previous = {}


# ============================================================
# CSV
# ============================================================

HEADER = [
    "time",
    "symbol",

    "bid",
    "ask",
    "mid",
    "spread_pct",

    "bid_change",
    "ask_change",

    "bid_vol1",
    "ask_vol1",

    "bid3",
    "ask3",
    "bid5",
    "ask5",
    "bid10",
    "ask10",

    "obi1",
    "obi3",
    "obi5",
    "obi10",

    "ofi_raw",
    "ofi_norm",

    "bid_vol_change",
    "ask_vol_change",
]


def ensure_file():
    if not os.path.exists(FILE) or os.path.getsize(FILE) == 0:
        with open(
            FILE,
            "w",
            newline="",
            encoding="utf-8-sig"
        ) as f:
            writer = csv.writer(f)
            writer.writerow(HEADER)


# ============================================================
# Helpers
# ============================================================

def now_string():
    return datetime.now().strftime(
        "%Y-%m-%d %H:%M:%S.%f"
    )[:-3]


def safe_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def depth_sum(levels, count):
    total = 0.0

    for item in levels[:count]:
        if len(item) >= 2:
            total += safe_float(item[1])

    return total


def calculate_obi(bid_volume, ask_volume):
    depth = bid_volume + ask_volume

    if depth <= 0:
        return 0.0

    return (bid_volume - ask_volume) / depth


# ============================================================
# OFI
# ============================================================

def calculate_ofi(
    previous_bid,
    current_bid,
    previous_bid_volume,
    current_bid_volume,
    previous_ask,
    current_ask,
    previous_ask_volume,
    current_ask_volume,
):
    """
    Best-quote OFI:

    Bid:
      bid price up   -> + current bid volume
      bid price down -> - previous bid volume
      same price     -> current - previous bid volume

    Ask:
      ask price down -> + current ask volume
      ask price up   -> - previous ask volume
      same price     -> current - previous ask volume
    """

    ofi_bid = 0.0
    ofi_ask = 0.0

    if current_bid > previous_bid:
        ofi_bid = current_bid_volume

    elif current_bid < previous_bid:
        ofi_bid = -previous_bid_volume

    else:
        ofi_bid = (
            current_bid_volume
            - previous_bid_volume
        )

    if current_ask < previous_ask:
        ofi_ask = current_ask_volume

    elif current_ask > previous_ask:
        ofi_ask = -previous_ask_volume

    else:
        ofi_ask = (
            current_ask_volume
            - previous_ask_volume
        )

    return ofi_bid + ofi_ask


# ============================================================
# Main
# ============================================================

def main():

    ensure_file()

    session = requests.Session()

    print("=" * 70)
    print("BITPIN SCANNER V2")
    print("READ ONLY - NO TRADING")
    print("FILE:", FILE)
    print("SYMBOLS:", len(SYMBOLS))
    print("START:", now_string())
    print("STOP: Ctrl+C")
    print("=" * 70)

    total_ok = 0
    total_error = 0

    try:

        while True:

            for symbol in SYMBOLS:

                timestamp = now_string()

                try:
                    response = session.get(
                        URL + symbol + "/",
                        timeout=REQUEST_TIMEOUT
                    )

                    response.raise_for_status()

                    data = response.json()

                    bids = data.get("bids", [])
                    asks = data.get("asks", [])

                    if not bids or not asks:
                        raise ValueError(
                            "Empty order book"
                        )

                    # ------------------------------------------------
                    # Best prices / volumes
                    # ------------------------------------------------

                    bid = safe_float(bids[0][0])
                    ask = safe_float(asks[0][0])

                    bid_vol1 = safe_float(bids[0][1])
                    ask_vol1 = safe_float(asks[0][1])

                    # ------------------------------------------------
                    # Depth
                    # ------------------------------------------------

                    bid1 = bid_vol1
                    ask1 = ask_vol1

                    bid3 = depth_sum(bids, 3)
                    ask3 = depth_sum(asks, 3)

                    bid5 = depth_sum(bids, 5)
                    ask5 = depth_sum(asks, 5)

                    bid10 = depth_sum(bids, 10)
                    ask10 = depth_sum(asks, 10)

                    # ------------------------------------------------
                    # Mid / Spread
                    # ------------------------------------------------

                    mid = (bid + ask) / 2.0

                    if mid > 0:
                        spread_pct = (
                            (ask - bid)
                            / mid
                            * 100.0
                        )
                    else:
                        spread_pct = 0.0

                    # ------------------------------------------------
                    # OBI
                    # ------------------------------------------------

                    obi1 = calculate_obi(
                        bid1,
                        ask1
                    )

                    obi3 = calculate_obi(
                        bid3,
                        ask3
                    )

                    obi5 = calculate_obi(
                        bid5,
                        ask5
                    )

                    obi10 = calculate_obi(
                        bid10,
                        ask10
                    )

                    # ------------------------------------------------
                    # OFI
                    # ------------------------------------------------

                    ofi_raw = 0.0
                    bid_change = 0.0
                    ask_change = 0.0
                    bid_vol_change = 0.0
                    ask_vol_change = 0.0

                    if symbol in previous:

                        old = previous[symbol]

                        old_bid = old["bid"]
                        old_ask = old["ask"]

                        old_bid_vol = old["bid_vol"]
                        old_ask_vol = old["ask_vol"]

                        bid_change = bid - old_bid
                        ask_change = ask - old_ask

                        bid_vol_change = (
                            bid_vol1
                            - old_bid_vol
                        )

                        ask_vol_change = (
                            ask_vol1
                            - old_ask_vol
                        )

                        ofi_raw = calculate_ofi(
                            old_bid,
                            bid,
                            old_bid_vol,
                            bid_vol1,
                            old_ask,
                            ask,
                            old_ask_vol,
                            ask_vol1
                        )

                    depth10 = bid10 + ask10

                    if depth10 > 0:
                        ofi_norm = (
                            ofi_raw
                            / depth10
                        )
                    else:
                        ofi_norm = 0.0

                    # ------------------------------------------------
                    # Save previous state
                    # ------------------------------------------------

                    previous[symbol] = {
                        "bid": bid,
                        "ask": ask,
                        "bid_vol": bid_vol1,
                        "ask_vol": ask_vol1,
                    }

                    # ------------------------------------------------
                    # Save CSV
                    # ------------------------------------------------

                    record = [
                        timestamp,
                        symbol,

                        bid,
                        ask,
                        mid,
                        round(spread_pct, 6),

                        bid_change,
                        ask_change,

                        bid_vol1,
                        ask_vol1,

                        bid3,
                        ask3,
                        bid5,
                        ask5,
                        bid10,
                        ask10,

                        round(obi1, 6),
                        round(obi3, 6),
                        round(obi5, 6),
                        round(obi10, 6),

                        round(ofi_raw, 8),
                        round(ofi_norm, 8),

                        bid_vol_change,
                        ask_vol_change,
                    ]

                    with open(
                        FILE,
                        "a",
                        newline="",
                        encoding="utf-8"
                    ) as f:

                        writer = csv.writer(f)
                        writer.writerow(record)

                    total_ok += 1

                    print(
                        timestamp,
                        "|",
                        symbol,
                        "| MID",
                        round(mid, 6),
                        "| SPR",
                        round(spread_pct, 4),
                        "| OBI10",
                        round(obi10, 4),
                        "| OFI",
                        round(ofi_norm, 4)
                    )

                except Exception as e:

                    total_error += 1

                    print(
                        timestamp,
                        "|",
                        symbol,
                        "| ERROR:",
                        e
                    )

                time.sleep(SYMBOL_DELAY_SEC)

            print("-" * 70)
            print(
                "OK:",
                total_ok,
                "| ERRORS:",
                total_error,
                "| TIME:",
                now_string()
            )
            print("-" * 70)

            time.sleep(ROUND_DELAY_SEC)

    except KeyboardInterrupt:

        print("\n")
        print("=" * 70)
        print("STOPPED BY USER")
        print("=" * 70)
        print("Total OK:", total_ok)
        print("Total errors:", total_error)
        print("File:", FILE)
        print("END:", now_string())
        print("=" * 70)

    finally:
        session.close()


if __name__ == "__main__":
    main()