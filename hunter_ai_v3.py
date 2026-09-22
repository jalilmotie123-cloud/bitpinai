import csv
import io
import math
import os
import statistics
import sys
from bisect import bisect_left, bisect_right
from datetime import datetime

import joblib
import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.metrics import classification_report, confusion_matrix

TRADEFLOW_FILE = "tradeflow_features_v3.csv"
MARKET_FILE = "market_data_v2.csv"
MODEL_FILE = "hunter_ai_v3_model.joblib"
OOS_FILE = "hunter_ai_v3_oos.csv"

SYMBOL = "SOL_USDT"
FEE_SIDE = 0.0035

# Economic event definition.
HORIZON_SEC = 3600.0
TP_NET_PCT = 0.50
SL_NET_PCT = -1.00

MAX_MARKET_STALE_SEC = 30.0
PURGE_SEC = HORIZON_SEC
TRAIN_FRAC = 0.70

# These are decision thresholds, fixed before OOS scoring.
BUY_PROB = 0.65
SELL_PROB = 0.65

RANDOM_STATE = 42

# Features that are identifiers / non-stationary raw values and should not
# become direct model inputs.
EXCLUDE_TF = {
    "id", "time", "price", "segment_id", "segment_cvd", "base_amount",
    "quote_amount", "side"
}


def finite(v):
    try:
        return math.isfinite(float(v))
    except Exception:
        return False


def parse_time(v):
    s = str(v).strip()
    for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(s, fmt).timestamp()
        except ValueError:
            pass
    return None


def net_long(entry_ask, exit_bid):
    return ((exit_bid * (1.0 - FEE_SIDE)) /
            (entry_ask * (1.0 + FEE_SIDE)) - 1.0) * 100.0


def load_tradeflow():
    rows = []
    with open(TRADEFLOW_FILE, encoding="utf-8-sig", newline="") as f:
        for x in csv.DictReader(f):
            try:
                t = float(x["time"])
                p = float(x["price"])
                if not math.isfinite(t) or not math.isfinite(p) or p <= 0:
                    continue
                x["_time"] = t
                x["_side_num"] = 1.0 if str(x.get("side", "")).lower() == "buy" else -1.0
                rows.append(x)
            except Exception:
                continue
    rows.sort(key=lambda r: r["_time"])
    return rows


def load_market():
    raw = open(MARKET_FILE, "rb").read().replace(b"\x00", b"")
    text = raw.decode("utf-8-sig")
    rows = []
    for x in csv.DictReader(io.StringIO(text)):
        if x.get("symbol") != SYMBOL:
            continue
        t = parse_time(x.get("time", ""))
        if t is None:
            continue
        try:
            bid = float(x["bid"])
            ask = float(x["ask"])
            mid = float(x.get("mid") or ((bid + ask) / 2.0))
            spread = float(x.get("spread_pct") or ((ask / bid - 1.0) * 100.0))
            obi = float(x.get("obi10") or 0.0)
            ofi = float(x.get("ofi_norm") or 0.0)
        except Exception:
            continue
        if bid <= 0 or ask <= 0 or ask < bid or not finite(mid):
            continue
        rows.append({
            "time": t, "bid": bid, "ask": ask, "mid": mid,
            "spread_pct": spread, "obi10": obi, "ofi_norm": ofi
        })
    rows.sort(key=lambda r: r["time"])
    out = []
    seen = set()
    for r in rows:
        if r["time"] in seen:
            continue
        seen.add(r["time"])
        out.append(r)
    return out


def market_at(market, times, signal_time):
    j = bisect_right(times, signal_time) - 1
    if j < 0:
        return None
    r = market[j]
    age = signal_time - r["time"]
    if age < 0 or age > MAX_MARKET_STALE_SEC:
        return None
    z = {
        "m_spread_pct": r["spread_pct"],
        "m_obi10": r["obi10"],
        "m_ofi_norm": r["ofi_norm"],
        "m_age_sec": age,
    }
    for h in (30, 60, 120, 300, 600):
        target = r["time"] - h
        k = bisect_right(times, target, 0, j + 1) - 1
        z["m_ret_%ds" % h] = ((r["mid"] / market[k]["mid"] - 1.0) * 100.0) if k >= 0 and market[k]["mid"] > 0 else 0.0
    return z


def entry_market(market, times, signal_time):
    j = bisect_right(times, signal_time) - 1
    if j < 0:
        return None
    r = market[j]
    age = signal_time - r["time"]
    if age < 0 or age > MAX_MARKET_STALE_SEC:
        return None
    return r


def make_label(market, times, entry, entry_ask):
    start = bisect_right(times, entry["time"])
    end_t = entry["time"] + HORIZON_SEC
    up_hit = False
    down_hit = False
    last_bid = None
    last_t = None

    for j in range(start, len(market)):
        r = market[j]
        if r["time"] > end_t:
            break
        last_bid = r["bid"]
        last_t = r["time"]
        ret = net_long(entry_ask, r["bid"])
        if ret >= TP_NET_PCT:
            up_hit = True
            return 1, r["time"], r["bid"], ret, "BUY"
        if ret <= SL_NET_PCT:
            down_hit = True
            return -1, r["time"], r["bid"], ret, "SELL"

    if last_bid is None:
        return None

    ret = net_long(entry_ask, last_bid)
    # Timeout is HOLD unless the final state itself is materially positive/negative.
    if ret >= TP_NET_PCT:
        return 1, last_t, last_bid, ret, "BUY"
    if ret <= SL_NET_PCT:
        return -1, last_t, last_bid, ret, "SELL"
    return 0, last_t, last_bid, ret, "HOLD"


def build_dataset(trades, market):
    mt = [r["time"] for r in market]
    records = []
    feature_names = set()

    for i, x in enumerate(trades):
        t = x["_time"]
        mr = market_at(market, mt, t)
        entry = entry_market(market, mt, t)
        if mr is None or entry is None:
            continue
        if entry["time"] + HORIZON_SEC > mt[-1]:
            continue

        feats = {}
        for k, v in x.items():
            if k.startswith("_") or k in EXCLUDE_TF:
                continue
            try:
                fv = float(v)
            except Exception:
                continue
            if finite(fv):
                feats["tf_" + k] = fv
        feats["tf_side_num"] = x["_side_num"]
        feats.update(mr)
        feature_names.update(feats.keys())

        lab = make_label(market, mt, entry, entry["ask"])
        if lab is None:
            continue

        y, exit_time, exit_bid, net_pct, action = lab
        records.append({
            "time": t,
            "features": feats,
            "label": y,
            "exit_time": exit_time,
            "exit_bid": exit_bid,
            "net_pct": net_pct,
            "action": action,
            "entry_ask": entry["ask"],
        })

    names = sorted(feature_names)
    return records, names


def matrix(records, names):
    return np.asarray([
        [r["features"].get(n, np.nan) for n in names]
        for r in records
    ], dtype=float)


def evaluate(model, imputer, records, names):
    X = imputer.transform(matrix(records, names))
    probs = model.predict_proba(X)
    classes = list(model.classes_)

    p_buy = np.array([probs[:, classes.index(1)] if 1 in classes else np.zeros(len(records))][0])
    p_sell = np.array([probs[:, classes.index(-1)] if -1 in classes else np.zeros(len(records))][0])

    actions = []
    for pb, ps in zip(p_buy, p_sell):
        if pb >= BUY_PROB and pb > ps:
            actions.append("BUY")
        elif ps >= SELL_PROB and ps > pb:
            actions.append("SELL")
        else:
            actions.append("HOLD")

    return p_buy, p_sell, actions


def main():
    print("HUNTER AI V3 - EVENT PROBABILITY ENGINE")
    print("SYMBOL =", SYMBOL)
    print("TARGET = executable event direction")
    print("HORIZON_SEC =", HORIZON_SEC)
    print("TP_NET_PCT =", TP_NET_PCT)
    print("SL_NET_PCT =", SL_NET_PCT)
    print("FEE_SIDE =", FEE_SIDE)
    print("BUY_PROB =", BUY_PROB)
    print("SELL_PROB =", SELL_PROB)

    if not os.path.exists(TRADEFLOW_FILE):
        print("MISSING", TRADEFLOW_FILE)
        return
    if not os.path.exists(MARKET_FILE):
        print("MISSING", MARKET_FILE)
        return

    trades = load_tradeflow()
    market = load_market()
    print("TRADEFLOW_ROWS =", len(trades))
    print("MARKET_ROWS =", len(market))

    records, names = build_dataset(trades, market)
    records.sort(key=lambda r: r["time"])
    print("LABELED_ROWS =", len(records))
    print("FEATURES =", len(names))

    if len(records) < 500:
        print("TOO_FEW_LABELED_ROWS")
        return

    split_i = int(len(records) * TRAIN_FRAC)
    split_time = records[split_i]["time"]

    train = [r for r in records if r["time"] < split_time - PURGE_SEC]
    test = [r for r in records if r["time"] > split_time + PURGE_SEC]

    print("TRAIN_ROWS =", len(train))
    print("OOS_ROWS =", len(test))

    X_train = matrix(train, names)
    y_train = np.asarray([r["label"] for r in train], dtype=int)
    X_test = matrix(test, names)
    y_test = np.asarray([r["label"] for r in test], dtype=int)

    print("TRAIN_CLASS_COUNTS =", {int(k): int(v) for k, v in zip(*np.unique(y_train, return_counts=True))})
    print("OOS_CLASS_COUNTS =", {int(k): int(v) for k, v in zip(*np.unique(y_test, return_counts=True))})

    imputer = SimpleImputer(strategy="median")
    X_train = imputer.fit_transform(X_train)
    X_test = imputer.transform(X_test)

    model = RandomForestClassifier(
        n_estimators=500,
        max_depth=12,
        min_samples_leaf=8,
        max_features="sqrt",
        class_weight="balanced_subsample",
        random_state=RANDOM_STATE,
        n_jobs=-1,
    )
    model.fit(X_train, y_train)

    preds = model.predict(X_test)
    print("\nCLASSIFICATION REPORT")
    print(classification_report(y_test, preds, labels=[-1, 0, 1], target_names=["SELL", "HOLD", "BUY"], zero_division=0))
    print("CONFUSION_MATRIX")
    print(confusion_matrix(y_test, preds, labels=[-1, 0, 1]))

    p_buy, p_sell, actions = evaluate(model, imputer, test, names)

    # Economic OOS score: simulate the model's decisions on the already-labeled events.
    # SELL means exit an existing long at the same event outcome; BUY means enter.
    rows = []
    last_exit = -1e30
    for r, pb, ps, act in zip(test, p_buy, p_sell, actions):
        if act == "HOLD":
            continue
        if r["time"] < last_exit:
            continue
        rows.append((r, pb, ps, act))
        last_exit = r["exit_time"]

    buy_rows = [x for x in rows if x[3] == "BUY"]
    sell_rows = [x for x in rows if x[3] == "SELL"]

    buy_returns = [x[0]["net_pct"] for x in buy_rows]
    sell_returns = [-x[0]["net_pct"] for x in sell_rows]

    print("\nEXECUTABLE OOS SIGNALS")
    print("SIGNALS =", len(rows))
    print("BUY_SIGNALS =", len(buy_rows))
    print("SELL_SIGNALS =", len(sell_rows))
    if buy_returns:
        print("BUY_MEAN_NET=%.5f%%" % statistics.mean(buy_returns))
        print("BUY_SUM_NET=%.5f%%" % sum(buy_returns))
    else:
        print("BUY_MEAN_NET=0.00000%")
        print("BUY_SUM_NET=0.00000%")
    if sell_returns:
        print("SELL_MEAN_EXIT_MOVE=%.5f%%" % statistics.mean(sell_returns))
        print("SELL_SUM_EXIT_MOVE=%.5f%%" % sum(sell_returns))
    else:
        print("SELL_MEAN_EXIT_MOVE=0.00000%")
        print("SELL_SUM_EXIT_MOVE=0.00000%")

    with open(OOS_FILE, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["time", "prob_buy", "prob_sell", "action", "label", "net_pct", "entry_ask", "exit_bid", "outcome_action"])
        for r, pb, ps, act in zip(test, p_buy, p_sell, actions):
            w.writerow([
                "%.6f" % r["time"], "%.6f" % pb, "%.6f" % ps, act,
                r["label"], "%.6f" % r["net_pct"], "%.10f" % r["entry_ask"],
                "%.10f" % r["exit_bid"], r["action"]
            ])

    artifact = {
        "model": model,
        "imputer": imputer,
        "feature_names": names,
        "symbol": SYMBOL,
        "fee_side": FEE_SIDE,
        "horizon_sec": HORIZON_SEC,
        "tp_net_pct": TP_NET_PCT,
        "sl_net_pct": SL_NET_PCT,
        "buy_prob": BUY_PROB,
        "sell_prob": SELL_PROB,
        "classes": classes if 'classes' in locals() else list(model.classes_),
    }
    joblib.dump(artifact, MODEL_FILE)

    pairs = sorted(zip(names, model.feature_importances_), key=lambda z: z[1], reverse=True)
    print("\nTOP_FEATURES")
    for name, importance in pairs[:20]:
        print("%s = %.6f" % (name, importance))

    print("\nMODEL_SAVED =", MODEL_FILE)
    print("OOS_SAVED =", OOS_FILE)
    print("\nPOLICY: BUY when P(BUY)>=%.2f and exceeds P(SELL); SELL when P(SELL)>=%.2f and exceeds P(BUY); otherwise HOLD." % (BUY_PROB, SELL_PROB))
    print("NOTE: SELL is an EXIT signal for an existing spot long, not a naked short.")


if __name__ == "__main__":
    main()
