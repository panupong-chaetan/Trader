"""
Paper Trading Bot v0.1 — ราคาจริง เงินปลอม
============================================
กลยุทธ์: MA crossover + stop loss (ตัวเดียวกับที่ backtest มา)
ข้อมูล : ราคาจริงจาก Binance (public API, ไม่ต้องมี account)
คำสั่ง : จำลองในเครื่อง (ยังไม่ส่งไป exchange)

หยุดบอท: กด Ctrl+C  (state ถูกเซฟไว้ รันใหม่แล้วพอร์ตต่อจากเดิม)
"""

import ccxt
import json
import os
import time
from datetime import datetime

# ---------------- CONFIG ----------------
SYMBOL     = "BTC/USDT"
TIMEFRAME  = "1h"        # แท่ง 1 ชั่วโมง: เร็วพอเห็นบอทขยับใน 1-2 วัน (แค่ทดสอบระบบ)
FAST, SLOW = 20, 50
STOP_PCT   = 0.10
FEE_RATE   = 0.001
INITIAL    = 100_000.0   # USDT ปลอม
POLL_SEC   = 60          # เช็คทุกกี่วินาที
STATE_FILE = "paper_state.json"
LOG_FILE   = "paper_trades.log"

# ---------------- STATE ----------------
def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            return json.load(f)
    return {"cash": INITIAL, "units": 0.0, "entry_price": None,
            "stopped_out": False, "total_fees": 0.0, "trades": 0}

def save_state(s):
    with open(STATE_FILE, "w") as f:
        json.dump(s, f, indent=2)

def log(msg):
    line = f"{datetime.now():%Y-%m-%d %H:%M:%S} | {msg}"
    print(line)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")

# ---------------- EXCHANGE ----------------
ex = ccxt.binance()   # public เท่านั้น ไม่มี key

def get_closed_candles():
    """ดึงแท่งเทียน แล้วตัดแท่งล่าสุดทิ้ง (มันยังไม่ปิด = ห้ามใช้ตัดสินใจ)"""
    ohlcv = ex.fetch_ohlcv(SYMBOL, TIMEFRAME, limit=SLOW + 5)
    closes = [c[4] for c in ohlcv[:-1]]        # index 4 = ราคาปิด
    live_price = ohlcv[-1][4]                  # ราคาปัจจุบัน ใช้เป็นราคาซื้อขาย
    return closes, live_price

# ---------------- STRATEGY ----------------
def compute_signal(closes):
    ma_fast = sum(closes[-FAST:]) / FAST
    ma_slow = sum(closes[-SLOW:]) / SLOW
    return ma_fast > ma_slow, ma_fast, ma_slow

# ---------------- MAIN LOOP ----------------
def run():
    state = load_state()
    log(f"บอทเริ่มทำงาน | cash={state['cash']:,.2f} units={state['units']:.6f}")

    while True:
        try:
            closes, price = get_closed_candles()
            want, ma_f, ma_s = compute_signal(closes)
            holding = state["units"] > 0
            equity = state["cash"] + state["units"] * price

            # 1) เช็ค stop loss ก่อนเสมอ
            if holding and price <= state["entry_price"] * (1 - STOP_PCT):
                gross = state["units"] * price
                fee = gross * FEE_RATE
                state.update(cash=gross - fee, units=0.0,
                             total_fees=state["total_fees"] + fee,
                             stopped_out=True, trades=state["trades"] + 1)
                log(f"*** STOP LOSS ขายที่ {price:,.2f} | equity={state['cash']:,.2f}")
                save_state(state)

            # 2) สัญญาณดับ -> ปลดล็อกให้กลับเข้าได้รอบหน้า
            elif not want and state["stopped_out"]:
                state["stopped_out"] = False
                save_state(state)

            # 3) เข้าซื้อ
            elif want and not holding and not state["stopped_out"]:
                fee = state["cash"] * FEE_RATE
                state.update(units=(state["cash"] - fee) / price,
                             entry_price=price, cash=0.0,
                             total_fees=state["total_fees"] + fee)
                log(f">>> BUY ที่ {price:,.2f} | MA{FAST}={ma_f:,.2f} MA{SLOW}={ma_s:,.2f}")
                save_state(state)

            # 4) ขายตามสัญญาณ
            elif not want and holding:
                gross = state["units"] * price
                fee = gross * FEE_RATE
                pnl = (price / state["entry_price"] - 1) * 100
                state.update(cash=gross - fee, units=0.0,
                             total_fees=state["total_fees"] + fee,
                             trades=state["trades"] + 1)
                log(f"<<< SELL ที่ {price:,.2f} | ไม้นี้ {pnl:+.2f}% | equity={state['cash']:,.2f}")
                save_state(state)

            # 5) heartbeat — ไม่ทำอะไรก็รายงานชีพจร
            else:
                pos = "ถือ BTC" if holding else "ถือเงินสด"
                log(f"เฝ้าดู | {price:,.2f} | MA{FAST}={ma_f:,.2f} MA{SLOW}={ma_s:,.2f} "
                    f"| {pos} | equity={equity:,.2f}")

        except Exception as e:
            log(f"ERROR: {e} — ลองใหม่รอบหน้า")   # เน็ตสะดุด/exchange ล่ม บอทต้องไม่ตาย

        time.sleep(POLL_SEC)

if __name__ == "__main__":
    run()