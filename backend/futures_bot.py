"""
Futures Paper Bot — บอทเปิด/ปิดไม้ futures อัตโนมัติ (เงินปลอมทั้งหมด)
========================================================================
ไม่เขียนสัญญาณใหม่ — ใช้ "สมอง" ก้อนเดียวกับ copilot.py (MA20/50 + regime filter)
เป๊ะๆ เพื่อให้เทียบผลกับบอท spot เดิมได้ตรงๆ ว่า leverage/short ช่วยหรือพัง:

    TREND_UP   + MA20 > MA50   -> LONG   (เงื่อนไขเดียวกับบอท spot ทุกตัวอักษร)
    TREND_DOWN + MA20 < MA50   -> SHORT  (ความสามารถใหม่ที่ futures มีแต่ spot ไม่มี
                                           ใช้สัญญาณตัวเดียวกัน แค่กลับด้าน)
    SIDEWAYS หรือสัญญาณกำกวม   -> ไม่เปิดไม้ นั่งทับมือ

กรอบความเสี่ยงที่ตั้งใจ "ตีแคบ" ไว้ตายตัวในโค้ด (ไม่ใช่ parameter ปรับจาก UI ได้)
เพราะให้ระบบตัดสินใจเปิดไม้เองแทนคน แม้จะเป็นเงินปลอมก็ตาม:
    - เทรดเฉพาะ BTC/USDT เหรียญเดียว
    - leverage คงที่ 5x ไม่ขยับเกินนี้เด็ดขาด
    - เสี่ยงต่อไม้ 1% ของ equity เท่านั้น (margin คำนวณจากระยะ stop จริง ไม่ใช่ all-in)
    - สัญญาณดับ/กลับด้าน -> ปิดเองทันที ไม่รอให้ liquidation เป็นทางออก
    - liquidation ยังทำงานอิสระจาก background ticker ใน futures_api.py อยู่แล้ว
      (บอทนี้แค่พยายามไม่ให้ไปถึงจุดนั้น ไม่ได้ปิดมันทิ้ง)

สถาปัตยกรรม: เหมือน copilot.py เป๊ะ — วิเคราะห์ตลาดต่อ exchange ตรง (เร็ว ไม่ต้องรอ
dashboard) แต่ "สั่งซื้อขาย" ผ่าน HTTP API ของ main.py เท่านั้น (ไม่แตะ futures_state.json
ตรงๆ) กัน race condition ระหว่างโปรเซสนี้กับ background ticker ที่รันอยู่ใน uvicorn อยู่แล้ว

ต้องรัน uvicorn (main.py) ค้างไว้ก่อนเสมอ:
    python futures_bot.py
หยุดบอท: Ctrl+C — state อยู่ใน futures_state.json ไฟล์เดียวกับ dashboard ปิดบอทแล้วพอร์ตไม่หาย
"""

import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime

import ccxt

_here = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _here)
import copilot  # ใช้ analyze() ตัวเดียวกับบอท spot — "สมอง" ก้อนเดียว ไม่แยกกัน

# ---------------- CONFIG (กรอบความเสี่ยงตายตัว — แก้ในนี้เท่านั้น ไม่มีสวิตช์จาก UI) ----------------
SYMBOL = "BTC/USDT"
TIMEFRAME = "1h"
POLL_SEC = 60
RISK_PCT = 1.0          # % ของ equity ที่ยอมเสียต่อไม้ ถ้าโดน stop พอดี
LEVERAGE = 5             # ตายตัว — ตามที่กำหนดไว้ ห้ามบอทขยับเกินนี้
MIN_MARGIN = 6.0         # กันไม้เล็กกว่าขั้นต่ำ notional 5 USDT ของ engine
API_BASE = "http://localhost:8000/api/futures"
LOG_FILE = os.path.join(_here, "futures_bot.log")

FAST, SLOW, SLOPE_BARS = copilot.FAST, copilot.SLOW, copilot.SLOPE_BARS

_ex = ccxt.binanceusdm({"enableRateLimit": True})  # อ่านราคาตรง เร็ว ไม่ผ่าน dashboard


def log(msg: str) -> None:
    line = f"{datetime.now():%Y-%m-%d %H:%M:%S} | {msg}"
    print(line)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")


# ---------------- คุยกับ dashboard ผ่าน HTTP เท่านั้น (เหมือน copilot.py เป๊ะ) ----------------

def api_get(path: str) -> dict:
    with urllib.request.urlopen(f"{API_BASE}{path}", timeout=10) as r:
        return json.loads(r.read().decode())


def api_post(path: str, body: dict) -> dict:
    data = json.dumps(body).encode()
    req = urllib.request.Request(f"{API_BASE}{path}", data=data,
                                  headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        detail = json.loads(e.read().decode()).get("detail", str(e))
        raise RuntimeError(detail) from e


# ---------------- วิเคราะห์ตลาด (สมองเดียวกับบอท spot) ----------------

def get_closed_candles():
    """ดึงแท่งเทียน futures จริง ตัดแท่งล่าสุดที่ยังไม่ปิดทิ้งเสมอ — ห้ามใช้ตัดสินใจ"""
    ohlcv = _ex.fetch_ohlcv(SYMBOL, TIMEFRAME, limit=SLOW + SLOPE_BARS + 5)
    closes = [c[4] for c in ohlcv[:-1]]
    return closes


def decide(a: dict, closes: list) -> tuple[str | None, float | None]:
    """แปลผล analyze() เป็น ('long'|'short'|None, stop_price|None)
    ใช้เงื่อนไขเดียวกับบอท spot สำหรับฝั่ง long เป๊ะ — short คือกลับด้านของตรรกะเดียวกัน"""
    if a["regime"] == "TREND_UP" and a["bullish"]:
        stop = min(a["swing_low"], a["ma_slow"])
        return "long", stop
    if a["regime"] == "TREND_DOWN" and not a["bullish"]:
        swing_high = max(closes[-10:])
        stop = max(swing_high, a["ma_slow"])
        return "short", stop
    return None, None


def size_margin(equity: float, price: float, stop: float, leverage: int) -> float:
    """margin ที่ทำให้ขาดทุนพอดี RISK_PCT% ของ equity ถ้าราคาไปโดน stop จริง
    notional = margin * leverage ; loss ที่ stop ≈ notional * stop_dist_pct
    -> margin = (equity * RISK_PCT/100) / (stop_dist_pct * leverage)"""
    stop_dist_pct = abs(price - stop) / price
    if stop_dist_pct <= 0:
        return 0.0
    risk_money = equity * RISK_PCT / 100
    return risk_money / (stop_dist_pct * leverage)


# ---------------- MAIN LOOP ----------------

def run():
    log(f"Futures Bot เริ่มทำงาน | {SYMBOL} {TIMEFRAME} | leverage {LEVERAGE}x ตายตัว "
        f"| เสี่ยง {RISK_PCT}%/ไม้ | เงินปลอม 100%")
    log("กรอบ: BTC/USDT เหรียญเดียว, ไม่เกิน 5x, ปิดเองทันทีถ้าสัญญาณดับ ไม่รอ liquidation")

    while True:
        try:
            closes = get_closed_candles()
            a = copilot.analyze(closes)
            side_wanted, stop = decide(a, closes)

            acc = api_get("/account")
            equity = acc["equity"]
            existing = next((p for p in acc["positions"] if p["symbol"] == SYMBOL), None)

            if existing:
                held = existing["side"]
                if side_wanted != held:
                    reason = "สัญญาณดับ" if side_wanted is None else f"สัญญาณกลับด้าน -> {side_wanted}"
                    rec = api_post("/close", {
                        "symbol": SYMBOL, "portion": 1.0, "note": f"[BOT] {reason}"})
                    log(f"[BOT] ปิด {held.upper()} เพราะ {reason} | "
                        f"PnL {rec['net_pnl']:+.2f} USDT ({rec['roe_pct']:+.1f}% ROE)")
                else:
                    log(f"[BOT] เฝ้าดู | ถือ {held.upper()} อยู่ | regime={a['regime']} "
                        f"| ROE ลอยตัว {existing['roe_pct']:+.1f}%")

            elif side_wanted:
                margin = size_margin(equity, a["price"], stop, LEVERAGE)
                floored = margin < MIN_MARGIN
                margin = max(margin, MIN_MARGIN)
                if margin > acc["available_margin"] * 0.9:
                    log(f"[BOT] อยากเปิด {side_wanted.upper()} แต่ margin ไม่พอ "
                        f"(ต้องการ {margin:.2f} เหลือ {acc['available_margin']:.2f}) — ข้ามรอบนี้")
                else:
                    if floored:
                        log(f"[BOT] หมายเหตุ: margin ที่คำนวณจาก risk {RISK_PCT}% ต่ำกว่าขั้นต่ำของ "
                            f"engine ปัดขึ้นเป็น {MIN_MARGIN} USDT (เสี่ยงเกิน {RISK_PCT}% เล็กน้อยรอบนี้)")
                    rec = api_post("/order", {
                        "symbol": SYMBOL, "side": side_wanted,
                        "margin": round(margin, 2), "leverage": LEVERAGE,
                        "sl": round(stop, 2),
                        "reason": (f"[BOT] {a['regime']} MA{FAST}/{SLOW} "
                                   f"slope={a['slope_pct']:+.2f}% spread={a['spread_pct']:.2f}%"),
                    })
                    log(f"[BOT] เปิด {side_wanted.upper()} margin={margin:.2f} {LEVERAGE}x "
                        f"@ {rec['entry_price']:,.2f} sl={stop:,.2f} liq={rec['liq_price']:,.2f}")
            else:
                log(f"[BOT] เฝ้าดู | ไม่มีไม้ | regime={a['regime']} | ราคา {a['price']:,.2f} "
                    f"| MA{FAST}={a['ma_fast']:,.2f} MA{SLOW}={a['ma_slow']:,.2f}")

        except urllib.error.URLError as e:
            log(f"[BOT] ต่อ dashboard ไม่ได้ ({e}) — ต้องเปิด uvicorn (main.py) ค้างไว้ก่อน")
        except Exception as e:
            log(f"[BOT] ERROR: {e} — ลองใหม่รอบหน้า")

        time.sleep(POLL_SEC)


if __name__ == "__main__":
    run()
