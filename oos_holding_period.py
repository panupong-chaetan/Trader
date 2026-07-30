"""
OOS Test: เทรดสั้น vs เทรดยาว (holding period)
==================================================
"เทรดสั้น" ในที่นี้ = ถือไม้ระยะสั้น เข้าออกถี่ (ไม่ใช่ short-selling / ขายชอร์ต)
วัดตรงๆ ว่า MA คู่ไหนทำให้ถือสั้น/ยาวแค่ไหน แล้ว "สั้น" คุ้มจริงไหมหลังหัก fee

วิธีใช้: วางในโฟลเดอร์ Trader (ข้างๆ backtest.py) แล้วรัน
    python oos_holding_period.py
"""

import numpy as np
from backtest import load_real_data, max_drawdown

FEE_RATE = 0.001
STOP_PCT = 0.10
INITIAL = 100_000.0

# คู่ MA ไล่จาก "สั้นสุด" ไป "ยาวสุด"
PAIRS = [(5, 15), (10, 30), (20, 50), (30, 80), (50, 100), (50, 200)]


def run(df, fast, slow, stop_pct=STOP_PCT, fee_rate=FEE_RATE, initial_cash=INITIAL):
    """เหมือน run_backtest_with_stop เดิม แต่เก็บ 'จำนวนวันที่ถือ' ต่อไม้ด้วย"""
    d = df.copy()
    d["ma_fast"] = d["close"].rolling(fast).mean()
    d["ma_slow"] = d["close"].rolling(slow).mean()
    d["signal"] = (d["ma_fast"] > d["ma_slow"]).astype(int)
    d["position"] = d["signal"].shift(1).fillna(0)

    cash, units, fees = initial_cash, 0.0, 0.0
    trades, hold_days, equity_curve = [], [], []
    entry, entry_idx = None, None

    for i, (_, row) in enumerate(d.iterrows()):
        price = row["close"]
        want, holding = row["position"] == 1, units > 0

        if holding and price <= entry * (1 - stop_pct):
            want = False  # โดน stop บังคับออก

        if want and not holding:
            fee = cash * fee_rate
            units = (cash - fee) / price
            fees += fee; cash = 0.0
            entry, entry_idx = price, i
        elif not want and holding:
            gross = units * price
            fee = gross * fee_rate
            cash = gross - fee
            fees += fee
            trades.append((price / entry - 1) * 100)
            hold_days.append(i - entry_idx)
            units = 0.0

        equity_curve.append(cash + units * price)

    d["equity"] = equity_curve
    if units > 0:
        trades.append((d["close"].iloc[-1] / entry - 1) * 100)
        hold_days.append(len(d) - 1 - entry_idx)

    final = d["equity"].iloc[-1]
    ret = (final / initial_cash - 1) * 100
    mdd, _ = max_drawdown(d["equity"])
    wins = [t for t in trades if t > 0]
    wr = len(wins) / len(trades) * 100 if trades else 0
    avg_hold = np.mean(hold_days) if hold_days else 0
    fee_drag_pct = fees / initial_cash * 100  # ค่าธรรมเนียมกินพอร์ตไปกี่ % รวม
    return {"return": ret, "mdd": mdd, "trades": len(trades), "win_rate": wr,
            "avg_hold_days": avg_hold, "fee_drag_pct": fee_drag_pct}


def report(name, r):
    print(f"{name:10} | return {r['return']:>8.1f}% | MaxDD {r['mdd']:>7.1f}% | "
          f"เทรด {r['trades']:>4} | ถือเฉลี่ย {r['avg_hold_days']:>5.1f} วัน | "
          f"fee กิน {r['fee_drag_pct']:>4.2f}%")


if __name__ == "__main__":
    data = load_real_data("BTC-USD")
    split = len(data) // 2
    train, test = data.iloc[:split], data.iloc[split:]
    print(f"ข้อมูลทั้งหมด {len(data)} วัน -> train {len(train)} / test {len(test)}\n")

    for label, chunk in [("=== IN-SAMPLE (train) ===", train),
                          ("=== OUT-OF-SAMPLE (test) — ข้อสอบจริง ===", test)]:
        print(label)
        results = {}
        for fast, slow in PAIRS:
            r = run(chunk, fast, slow)
            results[(fast, slow)] = r
            report(f"{fast}/{slow}", r)
        print()

    # ---- สรุปเฉพาะ OOS: เทรดสั้นสุด vs ยาวสุด ----
    r_short = run(test, *PAIRS[0])   # 5/15 = สั้นสุด
    r_long = run(test, *PAIRS[-1])   # 50/200 = ยาวสุด

    print("=== สรุป: เทรดสั้น (5/15) vs เทรดยาว (50/200) ใน OOS ===")
    print(f"เทรดสั้น: ถือเฉลี่ย {r_short['avg_hold_days']:.1f} วัน/ไม้ | "
          f"{r_short['trades']} ไม้ | fee กินพอร์ตไป {r_short['fee_drag_pct']:.2f}% | "
          f"return {r_short['return']:+.1f}%")
    print(f"เทรดยาว:  ถือเฉลี่ย {r_long['avg_hold_days']:.1f} วัน/ไม้ | "
          f"{r_long['trades']} ไม้ | fee กินพอร์ตไป {r_long['fee_drag_pct']:.2f}% | "
          f"return {r_long['return']:+.1f}%")

    fee_ratio = r_short['fee_drag_pct'] / max(r_long['fee_drag_pct'], 0.001)
    print(f"\nเทรดสั้นเสีย fee มากกว่าเทรดยาว {fee_ratio:.1f} เท่า "
          f"(เข้าออกถี่กว่า {r_short['trades'] / max(r_long['trades'],1):.1f} เท่า)")

    if r_short["return"] > r_long["return"]:
        print(">> เทรดสั้นชนะใน OOS นี้ — แต่เช็คด้วยว่าคุ้มกับความเหนื่อย/เวลาเฝ้าจอที่มากกว่าไหม")
    else:
        print(">> เทรดยาวชนะใน OOS นี้ — สอดคล้องกับที่มักพบทั่วไป: ถือยาวมักเสีย fee น้อยกว่า")
    print(">> ข้อควรระวัง: บนกราฟรายวัน 'เทรดสั้น' ยังถือเป็นวัน ถ้าเทียบกับเทรดสั้นจริงๆ "
          "แบบเปิด-ปิดในไม่กี่ชั่วโมง (เช่นบอท 5m ที่เราเคยรัน) fee drag จะสูงกว่านี้อีกมาก")
