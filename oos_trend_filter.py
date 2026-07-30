"""
OOS Test: MA ดิบ vs MA + Trend Filter (regime)
=================================================
พิสูจน์ว่า filter ที่ copilot.py ใช้กรองไม้อยู่ตอนนี้ "คุ้ม" จริงไหม
เกณฑ์ filter เดียวกับ copilot.py เป๊ะ: SLOPE_MIN=0.15, SPREAD_MIN=0.25, SLOPE_BARS=10

วิธีใช้: วางไฟล์นี้ในโฟลเดอร์ Trader (ข้างๆ backtest.py) แล้วรัน
    python oos_trend_filter.py
ต้องมี data_BTC-USD.csv (cache จาก backtest.py) หรือเน็ตต่อ yfinance ได้
"""

import numpy as np
import pandas as pd
from backtest import load_real_data, max_drawdown  # ใช้ของเดิม ไม่เขียนซ้ำ

FAST, SLOW = 20, 50
SLOPE_BARS, SLOPE_MIN, SPREAD_MIN = 10, 0.15, 0.25
FEE_RATE = 0.001
INITIAL = 100_000.0


def run(df, fast=FAST, slow=SLOW, stop_pct=0.10, use_filter=False,
        fee_rate=FEE_RATE, initial_cash=INITIAL):
    """Backtest MA crossover + stop loss, มี/ไม่มี trend filter (เกณฑ์เดียวกับ copilot.py)"""
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
            gross = units * price; fee = gross * fee_rate
            cash = gross - fee; fees += fee
            trades.append((price / entry - 1) * 100)
            units = 0.0; want = False   # กันเข้าซ้ำแท่งเดียวกัน
        elif want and not holding:
            fee = cash * fee_rate
            units = (cash - fee) / price; fees += fee; cash = 0.0; entry = price
        elif not want and holding:
            gross = units * price; fee = gross * fee_rate
            cash = gross - fee; fees += fee
            trades.append((price / entry - 1) * 100)
            units = 0.0

        equity_curve.append(cash + units * price)

    d["equity"] = equity_curve
    if units > 0:
        trades.append((d["close"].iloc[-1] / entry - 1) * 100)

    final = d["equity"].iloc[-1]
    ret = (final / initial_cash - 1) * 100
    mdd, _ = max_drawdown(d["equity"])
    wins = [t for t in trades if t > 0]
    wr = len(wins) / len(trades) * 100 if trades else 0
    return {"return": ret, "mdd": mdd, "trades": len(trades), "win_rate": wr, "fees": fees}


def report(name, r):
    print(f"{name:28} | return {r['return']:>8.1f}% | MaxDD {r['mdd']:>7.1f}% | "
          f"เทรด {r['trades']:>4} | WR {r['win_rate']:>5.1f}%")


if __name__ == "__main__":
    data = load_real_data("BTC-USD")
    split = len(data) // 2
    train, test = data.iloc[:split], data.iloc[split:]

    print(f"ข้อมูลทั้งหมด {len(data)} วัน -> train {len(train)} / test {len(test)}\n")

    print("=== IN-SAMPLE (train) ===")
    r1 = run(train, use_filter=False); report("MA ดิบ + stop 10%", r1)
    r2 = run(train, use_filter=True);  report("MA + trend filter + stop 10%", r2)

    print("\n=== OUT-OF-SAMPLE (test) — ข้อสอบจริง ===")
    r3 = run(test, use_filter=False); report("MA ดิบ + stop 10%", r3)
    r4 = run(test, use_filter=True);  report("MA + trend filter + stop 10%", r4)

    print("\n=== สรุป ===")
    print(f"filter ช่วยเพิ่ม OOS return: {r4['return'] - r3['return']:+.1f} จุด")
    print(f"filter ช่วยลด OOS MaxDD:     {r4['mdd'] - r3['mdd']:+.1f} จุด (บวก=ตื้นขึ้น=ดี)")
    print(f"filter ตัดจำนวนเทรดจาก {r3['trades']} เหลือ {r4['trades']} "
          f"({(1 - r4['trades']/max(r3['trades'],1))*100:.0f}% ลดลง)")
    if r4["return"] > r3["return"] and r4["mdd"] > r3["mdd"]:
        print(">> filter ผ่านทั้งสองมิติใน OOS — มีเหตุผลให้เก็บไว้ใน copilot ต่อ")
    else:
        print(">> filter ไม่ได้ดีขึ้นทุกมิติใน OOS — ควรทบทวนเกณฑ์ SLOPE_MIN/SPREAD_MIN")
