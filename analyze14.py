import csv
from collections import defaultdict
from datetime import datetime


FILE = "market_data.csv"

HORIZONS = [5, 15, 30]

SIGNAL_THRESHOLD = 0.20

# فعلاً صفر می‌گذاریم تا فقط اثر spread را اندازه بگیریم.
# بعداً کارمزد واقعی را جداگانه وارد می‌کنیم.
FEE_PER_SIDE = 0.0

INITIAL_CAPITAL = 1000.0


def pct_change(old_price, new_price):
    if old_price == 0:
        return 0.0
    return (new_price - old_price) / old_price * 100.0


def calculate_signal(items, i):
    """
    همان منطق پایه قبلی:
    OBI + OFI + momentum
    """
    if i < 5:
        return 0.0

    current_mid = items[i]["mid"]
    old_mid = items[i - 5]["mid"]

    if old_mid == 0:
        return 0.0

    momentum = (
        (current_mid - old_mid)
        / old_mid
        * 100.0
    )

    return (
        items[i]["obi10"]
        + items[i]["ofi_norm"]
        + momentum
    )


def apply_fee(value, fee):
    return value * (1.0 - fee)


def main():

    try:
        with open(
            FILE,
            "r",
            encoding="utf-8-sig",
            newline=""
        ) as f:
            rows = list(csv.DictReader(f))

    except Exception as e:
        print("ERROR reading file:", e)
        return

    data = defaultdict(list)

    for row in rows:
        try:
            data[row["symbol"]].append({
                "time": datetime.strptime(
                    row["time"],
                    "%Y-%m-%d %H:%M:%S"
                ),
                "bid": float(row["bid"]),
                "ask": float(row["ask"]),
                "mid": float(row["mid"]),
                "obi10": float(row["obi10"]),
                "ofi_norm": float(row["ofi_norm"]),
            })
        except Exception:
            continue

    print("=" * 95)
    print("ECONOMIC SIGNAL BACKTEST")
    print("File:", FILE)
    print("Signal threshold:", SIGNAL_THRESHOLD)
    print("Fee per side:", FEE_PER_SIDE)
    print("Initial capital:", INITIAL_CAPITAL)
    print("=" * 95)

    for symbol in sorted(data):

        items = data[symbol]

        print("\n" + "#" * 95)
        print("SYMBOL:", symbol)
        print("ROWS:", len(items))
        print("#" * 95)

        for horizon in HORIZONS:

            capital = INITIAL_CAPITAL

            trades = 0
            wins = 0
            losses = 0

            total_return = 0.0
            returns = []

            i = 5

            while i < len(items) - horizon:

                signal = calculate_signal(items, i)

                direction = 0

                if signal >= SIGNAL_THRESHOLD:
                    direction = 1
                elif signal <= -SIGNAL_THRESHOLD:
                    direction = -1

                if direction == 0:
                    i += 1
                    continue

                entry = items[i]
                exit_item = items[i + horizon]

                if direction == 1:
                    # Long:
                    # خرید با ASK
                    # فروش با BID
                    entry_price = entry["ask"]
                    exit_price = exit_item["bid"]

                    entry_after_fee = apply_fee(
                        entry_price,
                        FEE_PER_SIDE
                    )

                    exit_after_fee = apply_fee(
                        exit_price,
                        FEE_PER_SIDE
                    )

                    trade_return = (
                        exit_after_fee
                        / entry_after_fee
                        - 1.0
                    ) * 100.0

                else:
                    # Short:
                    # فروش با BID
                    # خرید با ASK
                    entry_price = entry["bid"]
                    exit_price = exit_item["ask"]

                    entry_after_fee = apply_fee(
                        entry_price,
                        FEE_PER_SIDE
                    )

                    exit_after_fee = apply_fee(
                        exit_price,
                        FEE_PER_SIDE
                    )

                    trade_return = (
                        entry_after_fee
                        / exit_after_fee
                        - 1.0
                    ) * 100.0

                capital *= (
                    1.0 + trade_return / 100.0
                )

                total_return += trade_return
                returns.append(trade_return)

                trades += 1

                if trade_return > 0:
                    wins += 1
                elif trade_return < 0:
                    losses += 1

                # جلوگیری از ورودهای پشت سر هم
                # تا پایان معامله صبر می‌کنیم.
                i += horizon

            if trades > 0:

                win_rate = (
                    wins / trades * 100.0
                )

                avg_trade = (
                    total_return / trades
                )

                net_return = (
                    (capital / INITIAL_CAPITAL) - 1.0
                ) * 100.0

                print(
                    "\nHORIZON:",
                    horizon
                )

                print(
                    "Trades:",
                    trades
                )

                print(
                    "Wins:",
                    wins
                )

                print(
                    "Losses:",
                    losses
                )

                print(
                    "Win rate (%):",
                    round(win_rate, 2)
                )

                print(
                    "Average trade (%):",
                    round(avg_trade, 4)
                )

                print(
                    "Final capital:",
                    round(capital, 4)
                )

                print(
                    "Net return (%):",
                    round(net_return, 4)
                )

            else:

                print(
                    "\nHORIZON:",
                    horizon,
                    "NO TRADES"
                )

    print("\n" + "=" * 95)
    print("ECONOMIC BACKTEST FINISHED")
    print("=" * 95)


if __name__ == "__main__":
    main()