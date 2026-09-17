# -*- coding: utf-8 -*-
"""
Bitpin Strategy Backtest - Version 10

Python: 3.8.10
Platform: Windows 7
Mode: READ-ONLY / PAPER BACKTEST
No real orders are sent to Bitpin.
"""

import csv
from datetime import datetime
from typing import Dict, List, Optional, Tuple


# ============================================================
# Configuration
# ============================================================

CSV_FILE = "market_data.csv"

HORIZON = 5
TRAIN_SIZE = 600
TEST_SIZE = 200

SIGNAL_THRESHOLD = 0.20
MIN_MOVE_PCT = 0.02

# Previous project baseline:
# 0.35% fee per side.
FEE_PER_SIDE = 0.0035

INITIAL_CAPITAL = 1000.0

# Only one position at a time per symbol.
# Long-only because this backtest assumes spot trading.
LONG_ONLY = True


# ============================================================
# Data Types
# ============================================================

Row = Dict[str, float]


# ============================================================
# Helpers
# ============================================================

def load_market_data(filename: str) -> Dict[str, List[Row]]:
    """
    Load and validate market data from CSV.

    Returns:
        Dictionary mapping each symbol to chronological rows.

    Raises:
        FileNotFoundError: if CSV does not exist.
        ValueError: if required columns are missing or data is invalid.
    """
    required = {
        "time",
        "symbol",
        "bid",
        "ask",
        "mid",
        "obi10",
        "ofi_norm",
    }

    data: Dict[str, List[Row]] = {}

    with open(filename, "r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)

        if reader.fieldnames is None:
            raise ValueError("CSV header not found.")

        missing = required.difference(reader.fieldnames)

        if missing:
            raise ValueError(
                "Missing columns: " + ", ".join(sorted(missing))
            )

        for line_number, record in enumerate(reader, start=2):
            try:
                symbol = record["symbol"].strip()

                data.setdefault(symbol, []).append({
                    "time": datetime.strptime(
                        record["time"],
                        "%Y-%m-%d %H:%M:%S"
                    ),
                    "bid": float(record["bid"]),
                    "ask": float(record["ask"]),
                    "mid": float(record["mid"]),
                    "obi": float(record["obi10"]),
                    "ofi": float(record["ofi_norm"]),
                })

            except (ValueError, TypeError, KeyError) as exc:
                print(
                    "WARNING: invalid row {}: {}".format(
                        line_number,
                        exc
                    )
                )

    for symbol in data:
        data[symbol].sort(key=lambda item: item["time"])

    return data


def calculate_score(rows: List[Row], index: int) -> float:
    """
    Calculate the normalized strategy score.

    Returns:
        Score in approximately [-1, 1].
    """
    mid = rows[index]["mid"]
    old_mid = rows[index - 5]["mid"]

    if old_mid <= 0:
        return 0.0

    momentum = (mid - old_mid) / old_mid * 100.0

    obi = max(-1.0, min(1.0, rows[index]["obi"]))
    ofi = max(-1.0, min(1.0, rows[index]["ofi"]))

    momentum_score = max(
        -1.0,
        min(1.0, momentum / 0.1)
    )

    return (
        obi * 0.40
        + ofi * 0.35
        + momentum_score * 0.25
    )


def select_mode(
    rows: List[Row],
    train_start: int,
    train_end: int
) -> Optional[str]:
    """
    Select NORMAL or REVERSE using training data only.
    """
    normal_correct = 0
    reverse_correct = 0
    total = 0

    for index in range(
        max(train_start, 5),
        train_end - HORIZON
    ):
        mid = rows[index]["mid"]
        future = rows[index + HORIZON]["mid"]

        if mid <= 0:
            continue

        move = (future - mid) / mid * 100.0

        if abs(move) < MIN_MOVE_PCT:
            continue

        score = calculate_score(rows, index)

        if abs(score) < SIGNAL_THRESHOLD:
            continue

        predicted = 1 if score > 0 else -1
        actual = 1 if move > 0 else -1

        total += 1

        if predicted == actual:
            normal_correct += 1

        if predicted != actual:
            reverse_correct += 1

    if total == 0:
        return None

    if reverse_correct > normal_correct:
        return "REVERSE"

    return "NORMAL"


def calculate_trade_return(
    entry_price: float,
    exit_price: float
) -> float:
    """
    Calculate net return after entry and exit fees.
    """
    if entry_price <= 0 or exit_price <= 0:
        return 0.0

    entry_cost = entry_price * (1.0 + FEE_PER_SIDE)
    exit_value = exit_price * (1.0 - FEE_PER_SIDE)

    return (exit_value / entry_cost) - 1.0


# ============================================================
# Main Backtest
# ============================================================

def backtest_symbol(
    symbol: str,
    rows: List[Row]
) -> None:
    """
    Run walk-forward paper backtest for one symbol.
    """
    if len(rows) < TRAIN_SIZE + TEST_SIZE:
        print(
            "\n{}: insufficient data ({} rows)".format(
                symbol,
                len(rows)
            )
        )
        return

    capital = INITIAL_CAPITAL
    peak_capital = capital
    max_drawdown = 0.0

    total_trades = 0
    winning_trades = 0
    losing_trades = 0

    gross_profit = 0.0
    gross_loss = 0.0

    trade_returns: List[float] = []

    start = TRAIN_SIZE

    while start < len(rows):

        train_start = start - TRAIN_SIZE
        train_end = start

        test_start = start
        test_end = min(
            start + TEST_SIZE,
            len(rows)
        )

        mode = select_mode(
            rows,
            train_start,
            train_end
        )

        if mode is None:
            start += TEST_SIZE
            continue

        for index in range(
            max(test_start, 5),
            test_end - HORIZON
        ):
            score = calculate_score(rows, index)

            if abs(score) < SIGNAL_THRESHOLD:
                continue

            predicted = 1 if score > 0 else -1

            if mode == "REVERSE":
                predicted *= -1

            # Spot/long-only backtest.
            if LONG_ONLY and predicted < 0:
                continue

            entry_ask = rows[index]["ask"]
            exit_bid = rows[index + HORIZON]["bid"]

            if entry_ask <= 0 or exit_bid <= 0:
                continue

            trade_return = calculate_trade_return(
                entry_ask,
                exit_bid
            )

            capital *= (1.0 + trade_return)

            trade_returns.append(trade_return)

            total_trades += 1

            if trade_return > 0:
                winning_trades += 1
                gross_profit += trade_return
            elif trade_return < 0:
                losing_trades += 1
                gross_loss += abs(trade_return)

            if capital > peak_capital:
                peak_capital = capital

            drawdown = (
                (peak_capital - capital)
                / peak_capital
                if peak_capital > 0
                else 0.0
            )

            if drawdown > max_drawdown:
                max_drawdown = drawdown

        start += TEST_SIZE

    print("\n" + "=" * 70)
    print(symbol)
    print("=" * 70)

    if total_trades == 0:
        print("No valid trades.")
        return

    win_rate = (
        winning_trades / total_trades * 100.0
    )

    total_return = (
        capital / INITIAL_CAPITAL - 1.0
    ) * 100.0

    average_trade = (
        sum(trade_returns)
        / len(trade_returns)
        * 100.0
    )

    if gross_loss > 0:
        profit_factor = gross_profit / gross_loss
    else:
        profit_factor = float("inf")

    print(
        "Trades            :",
        total_trades
    )

    print(
        "Winning trades    :",
        winning_trades
    )

    print(
        "Losing trades     :",
        losing_trades
    )

    print(
        "Win rate          :",
        round(win_rate, 2),
        "%"
    )

    print(
        "Initial capital   :",
        round(INITIAL_CAPITAL, 2)
    )

    print(
        "Final capital     :",
        round(capital, 2)
    )

    print(
        "Net return        :",
        round(total_return, 2),
        "%"
    )

    print(
        "Average trade     :",
        round(average_trade, 4),
        "%"
    )

    print(
        "Profit factor     :",
        (
            round(profit_factor, 3)
            if profit_factor != float("inf")
            else "INF"
        )
    )

    print(
        "Max drawdown      :",
        round(max_drawdown * 100.0, 2),
        "%"
    )


def main() -> None:
    """
    Entry point for the read-only backtest.
    """
    try:
        data = load_market_data(CSV_FILE)

        print("=" * 70)
        print("Bitpin PAPER BACKTEST - analyze10")
        print("=" * 70)
        print("File:", CSV_FILE)
        print("Horizon:", HORIZON)
        print("Fee per side:", FEE_PER_SIDE)
        print("Initial capital:", INITIAL_CAPITAL)
        print("Mode: READ-ONLY")
        print("=" * 70)

        for symbol, rows in sorted(data.items()):
            backtest_symbol(symbol, rows)

    except FileNotFoundError:
        print(
            "ERROR: {} not found.".format(CSV_FILE)
        )

    except ValueError as exc:
        print(
            "ERROR: invalid market data: {}".format(exc)
        )

    except OSError as exc:
        print(
            "ERROR: file access failed: {}".format(exc)
        )

    except Exception as exc:
        print(
            "ERROR: unexpected failure: {}".format(exc)
        )


if __name__ == "__main__":
    main()