"""
oos_per_asset.py — Backtest แยกรายเหรียญ บน Binance TH จริง
==============================================================
เป้าหมาย: เช็คว่าพารามิเตอร์ที่ copilot.py ใช้อยู่ตอนนี้ (FAST=20, SLOW=50,
SLOPE_MIN=0.15, SPREAD_MIN=0.25) — ที่ปรับจูนมาจาก BTC/USDT เท่านั้น —
ใช้ได้ผลกับเหรียญอื่นบน Binance TH ด้วยหรือไม่ ก่อนปล่อยให้ auto-trade แตะมัน

ข้อจำกัดที่ต้องรู้ก่อนอ่านผล:
  Binance TH เป็น exchange ใหม่ ประวัติราคาที่ดึงได้ผ่าน REST API
  (limit สูงสุด 1000 แท่ง) จะสั้นกว่าข้อมูล BTC/USDT 8 ปีที่เคยทดสอบมาก
  ผลจากไฟล์นี้จึงเป็น "สัญญาณเตือนเบื้องต้น" ไม่ใช่บทสรุปที่หนักแน่นเท่า BTC

วิธีใช้: วางในโฟลเดอร์ Trader (ข้างๆ binance_th.py, backtest.py) แล้วรัน
    python oos_per_asset.py
"""

import numpy as np
import pandas as pd
import binance_th

FAST, SLOW = 20, 50
SLOPE_BARS, SLOPE_MIN, SPREAD_MIN = 10, 0.15, 0.25   # ค่าเดียวกับ copilot.py
FEE_RATE = 0.001
STOP_PCT = 0.10
INITIAL = 10_000.0

ASSETS = ["BTCTHB", "ETHTHB", "BNBTHB", "SOLTHB", "XRPTHB"]


def load_th_data(symbol, interval="1h", limit=1000):
    """ดึงราคาจริงจาก Binance TH ผ่าน adapter เดียวกับที่ copilot ใช้"""
    ex = binance_th.BinanceTHExchange()
    ohlcv = ex.fetch_ohlcv(symbol, interval, limit)
    df = pd.DataFrame(ohlcv, columns=["time", "open", "high", "low", "close", "volume"])
    df["time"] = pd.to_datetime(df["time"], unit="ms")
    return df.set_index("time")[["close"]]


def max_drawdown(equity):
    peak = equity.cummax()
    dd = (equity - peak) / peak
    return dd.min() * 100


def run(df, use_filter, fast=FAST, slow=SLOW, stop_pct=STOP_PCT,
        fee_rate=FEE_RATE, initial_cash=INITIAL):
    d = df.copy()
    d["ma_fast"] = d["close"].rolling(fast).mean()
    d["ma_slow"] = d["close"].rolling(slow).mean()

    if use_filter:
        ma_slow_past = d["ma_slow"].shift(SLOPE_BARS)
        slope_pct = (d["ma_slow"] - ma_slow_past) / ma_slow_past * 100
        spread_pct = (d["ma_fast"] - d["ma_slow"]).abs() / d["ma_slow"] * 100
        trending = (slope_pct.abs() >= SLOPE_MIN) & (spread_pct >= SPREAD_MIN)
        bullish_trend = (slope_pct > 0) & trending
        d["signal"] = ((d["ma_fast"] > d["ma_slow"]) & bullish_trend).astype(int)
    else:
        d["signal"] = (d["ma_fast"] > d["ma_slow"]).astype(int)

    d["position"] = d["signal"].shift(1).fillna(0)

    cash, units, fees = initial_cash, 0.0, 0.0
    trades, equity_curve, entry = [], [], None

    for _, row in d.iterrows():
        price = row["close"]
        want, holding = row["position"] == 1, units > 0

        if holding and stop_pct and price <= entry * (1 - stop_pct):
            want = False
        if want and not holding:
            fee = cash * fee_rate
            units = (cash - fee) / price
            fees += fee; cash = 0.0; entry = price
        elif not want and holding:
            gross = units * price
            fee = gross * fee_rate
            cash = gross - fee
            fees += fee
            trades.append((price / entry - 1) * 100)
            units = 0.0

        equity_curve.append(cash + units * price)

    d["equity"] = equity_curve
    if units > 0:
        trades.append((d["close"].iloc[-1] / entry - 1) * 100)

    final = d["equity"].iloc[-1]
    ret = (final / initial_cash - 1) * 100
    mdd = max_drawdown(d["equity"])
    wins = [t for t in trades if t > 0]
    wr = len(wins) / len(trades) * 100 if trades else 0
    return {"return": ret, "mdd": mdd, "trades": len(trades), "win_rate": wr}


def buy_hold(df, initial_cash=INITIAL, fee_rate=FEE_RATE):
    units = (initial_cash * (1 - fee_rate)) / df["close"].iloc[0]
    equity = units * df["close"]
    return {"return": (equity.iloc[-1] / initial_cash - 1) * 100,
            "mdd": max_drawdown(equity)}


def row(name, r):
    wr = f"{r['win_rate']:.1f}%" if "win_rate" in r else "—"
    print(f"  {name:22} | return {r['return']:>7.1f}% | MaxDD {r['mdd']:>7.1f}% | "
          f"เทรด {r.get('trades', '—'):>4} | WR {wr:>6}")


if __name__ == "__main__":
    print("กำลังดึงข้อมูลจาก Binance TH ทีละเหรียญ (แท่ง 1H สูงสุด 1000 แท่ง)...\n")
    verdicts = []

    for symbol in ASSETS:
        try:
            data = load_th_data(symbol)
        except Exception as e:
            print(f"=== {symbol} === ดึงข้อมูลไม่สำเร็จ: {e}\n")
            continue

        days = (data.index[-1] - data.index[0]).total_seconds() / 86400
        print(f"=== {symbol} === ({len(data)} แท่ง ≈ {days:.0f} วัน)")

        if len(data) < SLOW + SLOPE_BARS + 20:
            print("  ข้อมูลน้อยเกินไปจะ backtest ได้น่าเชื่อถือ (ข้ามเหรียญนี้)\n")
            continue

        split = len(data) // 2
        train, test = data.iloc[:split], data.iloc[split:]

        r_nofilter = run(test, use_filter=False)
        r_filter = run(test, use_filter=True)
        r_bh = buy_hold(test)

        row("MA ดิบ + stop 10% (OOS)", r_nofilter)
        row("MA + trend filter (OOS)", r_filter)
        print(f"  {'Buy & Hold (OOS)':22} | return {r_bh['return']:>7.1f}% | MaxDD {r_bh['mdd']:>7.1f}%")

        # ตัดสินแบบเดียวกับ oos_trend_filter.py
        if r_filter["trades"] < 3:
            v = "ข้อมูล/สัญญาณน้อยเกินจะสรุป — ต้องรอเก็บข้อมูลเพิ่ม"
        elif r_filter["return"] > r_nofilter["return"] and r_filter["mdd"] > r_nofilter["mdd"]:
            v = "filter ช่วยจริงใน OOS นี้ — พารามิเตอร์เดิมพอใช้ได้"
        else:
            v = "filter ไม่ได้ช่วยชัดเจน — ควรระวัง หรือจูนพารามิเตอร์ใหม่เฉพาะเหรียญนี้"
        print(f"  >> {v}\n")
        verdicts.append((symbol, v))

    print("=" * 60)
    print("สรุปทุกเหรียญ:")
    for symbol, v in verdicts:
        print(f"  {symbol:10} {v}")
