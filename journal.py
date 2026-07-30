"""
สมุดเทรดมือ v0.1 — พอร์ตจำลอง เงินปลอม ราคาจริงจาก Binance
=============================================================
ใช้คู่กับ paper_bot.py: กลไกเดียวกัน (fee 0.1%, ราคา BTC/USDT จริง)
เพื่อแข่ง "คุณ vs บอท" อย่างยุติธรรม

วิธีใช้:  python journal.py   แล้วเลือกเมนู
กติกาเหล็ก: ระบบจะไม่ยอมเปิดไม้ถ้าไม่กรอก stop loss
"""

import ccxt
import json
import os
from datetime import datetime

SYMBOL       = "BTC/USDT"
FEE_RATE     = 0.001
INITIAL      = 10_000.0       # THB ปลอม (เท่า dashboard)
MAX_RISK_PCT = 2.0            # เสี่ยงต่อไม้ได้ไม่เกินกี่ % ของพอร์ต
STATE_FILE   = "journal_state.json"

ex = ccxt.binance()

# ---------------- STATE ----------------
def load():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, encoding="utf-8") as f:
            return json.load(f)
    return {"cash": INITIAL, "open_trade": None, "closed_trades": []}

def save(s):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(s, f, ensure_ascii=False, indent=2)

def live_price():
    return ex.fetch_ticker(SYMBOL)["last"]

def ask_float(prompt):
    while True:
        try:
            return float(input(prompt).replace(",", ""))
        except ValueError:
            print("  พิมพ์ตัวเลขครับ")

# ---------------- OPEN ----------------
def open_trade(s):
    if s["open_trade"]:
        print("มีไม้เปิดอยู่แล้ว ปิดก่อนถึงเปิดใหม่ได้ (ระบบนี้ถือทีละไม้)")
        return
    price = live_price()
    equity = s["cash"]
    print(f"\nราคา {SYMBOL} ตอนนี้: {price:,.2f} | พอร์ต: {equity:,.2f}")

    # --- กติกาเหล็ก: ต้องมี stop ก่อนทุกอย่าง ---
    stop = ask_float("จุด stop loss (ราคา): ")
    if stop >= price:
        print("!! stop ต้องต่ำกว่าราคาปัจจุบัน (เราเล่นฝั่งซื้อ) — ยกเลิกไม้")
        return
    risk_per_unit = price - stop
    stop_pct = risk_per_unit / price * 100

    # --- position sizing จาก risk ไม่ใช่จากเงินที่มี ---
    risk_pct = ask_float(f"เสี่ยงกี่ % ของพอร์ต (สูงสุด {MAX_RISK_PCT}): ")
    if risk_pct > MAX_RISK_PCT:
        print(f"!! เกินเพดาน {MAX_RISK_PCT}% — ปรับลงเหลือ {MAX_RISK_PCT}%")
        risk_pct = MAX_RISK_PCT
    risk_money = equity * risk_pct / 100
    units = risk_money / risk_per_unit          # ขนาดไม้ที่ทำให้โดน stop แล้วเสียตาม risk พอดี
    cost = units * price
    if cost > equity:                            # ไม่มี leverage — จำกัดที่เงินสดที่มี
        units = equity / price
        cost = equity
        print(f"(ขนาดไม้ถูกจำกัดด้วยเงินสด: ถ้าโดน stop จะเสีย ~{units*risk_per_unit:,.0f})")

    target = ask_float("เป้ากำไร (ราคา, 0 = ไม่ตั้ง): ")
    reason = input("เหตุผลเข้าไม้ (1 บรรทัด): ").strip()
    if not reason:
        print("!! ไม่มีเหตุผล = ไม่มีไม้ — ยกเลิก (ถ้าเขียนเหตุผลไม่ได้ แปลว่ายังไม่ควรเข้า)")
        return

    rr = (target - price) / risk_per_unit if target > price else 0
    fee = cost * FEE_RATE
    s["cash"] -= (cost + fee)
    s["open_trade"] = {
        "time_in": f"{datetime.now():%Y-%m-%d %H:%M:%S}",
        "entry": price, "stop": stop, "target": target,
        "units": units, "cost": cost, "fee_in": fee,
        "risk_pct": risk_pct, "reason": reason,
    }
    save(s)
    print(f"\n>>> เปิดไม้: ซื้อ {units:.6f} BTC ที่ {price:,.2f}")
    print(f"    stop {stop:,.2f} (-{stop_pct:.2f}%) | เสี่ยงจริง ~{units*risk_per_unit:,.0f} "
          f"({risk_pct}% ของพอร์ต) | R:R = 1:{rr:.1f}" if target > price else
          f"    stop {stop:,.2f} (-{stop_pct:.2f}%) | เสี่ยงจริง ~{units*risk_per_unit:,.0f}")

# ---------------- CLOSE ----------------
def close_trade(s):
    t = s["open_trade"]
    if not t:
        print("ไม่มีไม้เปิดอยู่")
        return
    price = live_price()
    pnl_pct = (price / t["entry"] - 1) * 100
    print(f"\nราคาตอนนี้ {price:,.2f} | เข้าที่ {t['entry']:,.2f} | ไม้นี้ {pnl_pct:+.2f}%")
    print(f"แผนเดิม: stop {t['stop']:,.2f} / target {t['target']:,.2f}")
    confirm = input("ปิดไม้ที่ราคานี้? (y/n): ").lower()
    if confirm != "y":
        return

    # --- หัวใจของสมุด: บันทึกว่าทำตามแผนไหม ---
    print("การปิดครั้งนี้คือ:")
    print("  1 = ตามแผน (ถึง stop / ถึง target / สัญญาณกลยุทธ์บอกออก)")
    print("  2 = นอกแผน (กลัว/โลภ/เบื่อ/เหตุผลอื่นที่ไม่ได้เขียนไว้ตอนเข้า)")
    plan = input("เลือก 1 หรือ 2: ").strip()
    note = input("โน้ตสั้นๆ (เกิดอะไรขึ้น): ").strip()

    gross = t["units"] * price
    fee = gross * FEE_RATE
    s["cash"] += gross - fee
    t.update(time_out=f"{datetime.now():%Y-%m-%d %H:%M:%S}",
             exit=price, fee_out=fee, pnl_pct=pnl_pct,
             pnl_money=gross - fee - t["cost"] - t["fee_in"],
             followed_plan=(plan == "1"), note=note)
    s["closed_trades"].append(t)
    s["open_trade"] = None
    save(s)
    tag = "ตามแผน" if plan == "1" else "นอกแผน !"
    print(f"<<< ปิดไม้ {pnl_pct:+.2f}% ({t['pnl_money']:+,.2f}) [{tag}] | พอร์ต: {s['cash']:,.2f}")

# ---------------- STATUS / STATS ----------------
def status(s):
    price = live_price()
    t = s["open_trade"]
    equity = s["cash"] + (t["units"] * price if t else 0)
    print(f"\nพอร์ต: {equity:,.2f} ({(equity/INITIAL-1)*100:+.2f}% จากเริ่มต้น)")
    if t:
        pnl = (price / t["entry"] - 1) * 100
        print(f"ไม้เปิด: เข้า {t['entry']:,.2f} | ตอนนี้ {price:,.2f} ({pnl:+.2f}%) "
              f"| stop {t['stop']:,.2f} | เหตุผล: {t['reason']}")
    else:
        print("ไม่มีไม้เปิด")

def stats(s):
    trades = s["closed_trades"]
    if not trades:
        print("ยังไม่มีไม้ที่ปิดแล้ว")
        return
    wins = [t for t in trades if t["pnl_pct"] > 0]
    losses = [t for t in trades if t["pnl_pct"] <= 0]
    followed = [t for t in trades if t["followed_plan"]]
    wr = len(wins) / len(trades) * 100
    aw = sum(t["pnl_pct"] for t in wins) / len(wins) if wins else 0
    al = sum(t["pnl_pct"] for t in losses) / len(losses) if losses else 0
    expectancy = (wr/100) * aw + (1 - wr/100) * al
    print(f"\n===== สถิติ ({len(trades)} ไม้) =====")
    print(f"Win Rate     : {wr:.1f}%")
    print(f"ชนะเฉลี่ย    : {aw:+.2f}% | แพ้เฉลี่ย: {al:+.2f}%")
    print(f"Expectancy   : {expectancy:+.3f}% ต่อไม้  {'(บวก = ระยะยาวไปต่อได้)' if expectancy > 0 else '(ลบ = เทรดต่อ = จนลง หยุดทบทวน)'}")
    print(f"วินัย        : ทำตามแผน {len(followed)}/{len(trades)} ไม้ ({len(followed)/len(trades)*100:.0f}%)")
    off_plan_pnl = sum(t["pnl_pct"] for t in trades if not t["followed_plan"])
    if len(followed) < len(trades):
        print(f"ไม้นอกแผนรวมกันได้ {off_plan_pnl:+.2f}% — ดูเลขนี้บ่อยๆ ว่าการแหกแผน 'คุ้ม' จริงไหม")

# ---------------- MENU ----------------
def main():
    s = load()
    print(f"สมุดเทรด {SYMBOL} | พิมพ์เลขเลือกเมนู")
    while True:
        print("\n[1] เปิดไม้  [2] ปิดไม้  [3] ดูพอร์ต  [4] สถิติ  [5] ออก")
        c = input("> ").strip()
        if c == "1": open_trade(s)
        elif c == "2": close_trade(s)
        elif c == "3": status(s)
        elif c == "4": stats(s)
        elif c == "5": break
        else: print("เลือก 1-5")

if __name__ == "__main__":
    main()
