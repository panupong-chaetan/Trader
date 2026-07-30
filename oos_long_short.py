"""
OOS Test: Long-only vs Long+Short vs Buy & Hold
==================================================
เป้าหมาย: เรียนรู้กลไก short (ไม่ได้เอาไปใช้จริงในระบบเทรด — แค่ backtest ดูตัวเลข)
เปรียบเทียบ 3 เวอร์ชันบนข้อมูล BTC จริง 8 ปี แบ่ง train/test เหมือน OOS test อื่นๆ ทุกครั้ง

Long-only  : MA20>MA50 ถือซื้อ (ของเดิมที่ใช้อยู่ทั้งระบบตอนนี้) / นอกนั้นถือเงินสด
Long+Short : MA20>MA50 ถือซื้อ / MA20<MA50 ถือขายชอร์ต (ไม่มีถือเงินสดเปล่าๆ)
Buy & Hold : ซื้อวันแรกถือยาว (ตัวเทียบมาตรฐาน)

หมายเหตุ: short จำลองแบบง่าย (ไม่มี funding rate/liquidation จริงจัง)
เป้าหมายคือดูภาพรวมของ "เล่นได้สองทาง" ไม่ใช่จำลอง exchange เป๊ะ

วิธีใช้: วางในโฟลเดอร์ Trader (ข้างๆ backtest.py) แล้วรัน
    python oos_long_short.py
"""

import numpy as np
from backtest import load_real_data, max_drawdown

FAST, SLOW = 20, 50
FEE_RATE = 0.001
STOP_PCT = 0.10
INITIAL = 100_000.0


def run(df, mode="long_only", fast=FAST, slow=SLOW, stop_pct=STOP_PCT,
        fee_rate=FEE_RATE, initial_cash=INITIAL):
    """mode: 'long_only' หรือ 'long_short'"""
    d = df.copy()
    d["ma_fast"] = d["close"].rolling(fast).mean()
    d["ma_slow"] = d["close"].rolling(slow).mean()
    d["bullish"] = d["ma_fast"] > d["ma_slow"]
    d["position"] = d["bullish"].shift(1)  # True=long, False=short/cash เมื่อวาน

    cash, units, fees = initial_cash, 0.0, 0.0
    side = None          # "long" / "short" / None
    entry = None
    trades, equity_curve = [], []

    for _, row in d.iterrows():
        price = row["close"]
        want_long = row["position"] == True
        want_short = (mode == "long_short") and row["position"] == False

        # เช็ค stop loss ก่อนเสมอ
        if side == "long" and price <= entry * (1 - stop_pct):
            want_long = False  # บังคับออก
        if side == "short" and price >= entry * (1 + stop_pct):
            want_short = False  # บังคับออก

        # ปิดสถานะเดิมถ้าสัญญาณ/stop สั่งออก
        if side == "long" and not want_long:
            pnl_pct = (price / entry - 1) * 100
            gross = units * price
            fee = gross * fee_rate
            cash += gross - fee
            fees += fee
            trades.append(pnl_pct)
            units, side, entry = 0.0, None, None
        elif side == "short" and not want_short:
            pnl_pct = (entry / price - 1) * 100  # short: กำไรเมื่อราคาลง
            gross = units * (2 * entry - price)   # คืนเงินยืม + กำไร/ขาดทุนจากส่วนต่าง (จำลองง่าย)
            fee = abs(gross) * fee_rate
            cash += gross - fee
            fees += fee
            trades.append(pnl_pct)
            units, side, entry = 0.0, None, None

        # เปิดสถานะใหม่ถ้ายังไม่มีสถานะ
        if side is None and want_long:
            fee = cash * fee_rate
            units = (cash - fee) / price
            fees += fee
            cash = 0.0
            side, entry = "long", price
        elif side is None and want_short:
            fee = cash * fee_rate
            units = (cash - fee) / price
            fees += fee
            cash = 0.0   # เหมือน long ทุกประการ: ทุ่มเงินสดทั้งหมดเข้า position
            side, entry = "short", price

        if side == "long":
            equity_curve.append(cash + units * price)
        elif side == "short":
            equity_curve.append(cash + units * (2 * entry - price))
        else:
            equity_curve.append(cash)

    d["equity"] = equity_curve
    final = d["equity"].iloc[-1]
    ret = (final / initial_cash - 1) * 100
    mdd, _ = max_drawdown(d["equity"])
    wins = [t for t in trades if t > 0]
    wr = len(wins) / len(trades) * 100 if trades else 0
    return {"return": ret, "mdd": mdd, "trades": len(trades), "win_rate": wr, "fees": fees}


def buy_hold(df, initial_cash=INITIAL, fee_rate=FEE_RATE):
    units = (initial_cash * (1 - fee_rate)) / df["close"].iloc[0]
    equity = units * df["close"]
    ret = (equity.iloc[-1] / initial_cash - 1) * 100
    mdd, _ = max_drawdown(equity)
    return {"return": ret, "mdd": mdd, "trades": 1, "win_rate": None, "fees": initial_cash * fee_rate}


def row(name, r):
    wr = f"{r['win_rate']:.1f}%" if r["win_rate"] is not None else "—"
    print(f"{name:22} | return {r['return']:>8.1f}% | MaxDD {r['mdd']:>7.1f}% | "
          f"เทรด {r['trades']:>4} | WR {wr:>6}")


if __name__ == "__main__":
    data = load_real_data("BTC-USD")
    split = len(data) // 2
    train, test = data.iloc[:split], data.iloc[split:]
    print(f"ข้อมูลทั้งหมด {len(data)} วัน -> train {len(train)} / test {len(test)}\n")

    for label, chunk in [("=== IN-SAMPLE (train) ===", train),
                          ("=== OUT-OF-SAMPLE (test) — ข้อสอบจริง ===", test)]:
        print(label)
        r_long = run(chunk, "long_only")
        r_ls = run(chunk, "long_short")
        r_bh = buy_hold(chunk)
        row("Long-only (ของเดิม)", r_long)
        row("Long+Short", r_ls)
        row("Buy & Hold", r_bh)
        print()

    # ---- สรุปเฉพาะ OOS เพราะนั่นคือข้อสอบจริง ----
    r_long_t = run(test, "long_only")
    r_ls_t = run(test, "long_short")
    r_bh_t = buy_hold(test)

    print("=== สรุป (เทียบเฉพาะ OOS) ===")
    print(f"Short ช่วยเพิ่ม return เทียบ long-only: {r_ls_t['return'] - r_long_t['return']:+.1f} จุด")
    print(f"Short ทำ MaxDD เปลี่ยนไป: {r_ls_t['mdd'] - r_long_t['mdd']:+.1f} จุด "
          f"(ลบ = เสี่ยงกว่าเดิม, บวก = ตื้นขึ้น)")
    print(f"Long+Short เทียบ Buy & Hold: {r_ls_t['return'] - r_bh_t['return']:+.1f} จุด")

    if r_ls_t["return"] > r_long_t["return"] and r_ls_t["mdd"] > r_long_t["mdd"]:
        verdict = "Short ช่วยทั้ง return และ MaxDD ใน OOS — มีเหตุผลให้ศึกษาต่อจริงจัง"
    elif r_ls_t["return"] > r_long_t["return"]:
        verdict = "Short ช่วย return แต่ MaxDD แย่ลง — ได้กำไรเพิ่มแลกกับความเสี่ยงที่สูงขึ้น (ต้องชั่งใจ)"
    else:
        verdict = "Short ไม่ได้ช่วยจริงใน OOS — อย่าเพิ่งเชื่อว่า 'เล่นได้สองทางย่อมดีกว่า'"
    print(f"\n>> {verdict}")
    print(">> อย่าลืม: นี่คือ backtest ทดลองความรู้เท่านั้น ไม่มีการเปิดไม้ short จริงในระบบเทรดของคุณ")
