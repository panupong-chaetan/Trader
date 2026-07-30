"""
Trading Copilot v0.1 — ผู้ช่วยเทรดมือแบบเรียลไทม์ (พูดความจริงเท่านั้น)
=======================================================================
ปรัชญา: ไม่มีคำว่า "แม่นยำ" มีแต่ "แต้มต่อ + ความไม่แน่นอน"
  - บอกสภาพตลาด (regime) ก่อนเสมอ: TREND หรือ SIDEWAYS
  - สัญญาณเดียวกัน ความน่าเชื่อไม่เท่ากันในแต่ละ regime
  - คำนวณ stop + ขนาดไม้ให้ตามหลัก risk 1%
  - ไม่เคยสั่ง "ซื้อเลย!" — ให้ข้อมูล คุณตัดสินใจ

สถาปัตยกรรม: analyze() เป็น pure function แยกจาก I/O ทั้งหมด
  -> วันหน้า paper_bot.py / auto trade เรียกใช้สมองก้อนเดียวกันนี้ได้ทันที

รัน:  python copilot.py
หยุด: Ctrl+C
"""

import os
import time
from datetime import datetime
import binance_th   # ต่อ Binance TH ตรงๆ (ไม่ผ่าน ccxt เพราะไม่รองรับ)

COPILOT_LOG = "copilot.log"

def log(msg: str):
    line = f"{datetime.now():%Y-%m-%d %H:%M:%S} | {msg}"
    print(line)
    with open(COPILOT_LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")

try:
    import notifier          # แจ้งเตือน Telegram (ไม่มีไฟล์ก็รันต่อได้)
except Exception:
    notifier = None

def alert(key, value, text):
    if notifier:
        notifier.send_on_change(key, value, text)

# ---------------- Auto-trade (ผ่านสวิตช์ toggle ใน dashboard) ----------------
import urllib.request

API_BASE = "http://localhost:8000/api"
AUTO_FILE = "auto_toggle.json"

def _api_get(path):
    with urllib.request.urlopen(f"{API_BASE}{path}", timeout=8) as r:
        return json.loads(r.read().decode())

def _api_post(path, body):
    data = json.dumps(body).encode()
    req = urllib.request.Request(f"{API_BASE}{path}", data=data,
                                  headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=8) as r:
        return json.loads(r.read().decode())

def auto_enabled(symbol):
    """เช็คสวิตช์ auto-trade เฉพาะเหรียญนี้ (แยกรายเหรียญ ไม่ใช่สวิตช์เดียวคุมหมดแล้ว)"""
    if not os.path.exists(AUTO_FILE):
        return False
    try:
        data = json.load(open(AUTO_FILE, encoding="utf-8"))
        # รองรับไฟล์เก่า (global {"enabled": bool}) เผื่อยังไม่ได้เปิด dashboard
        # ให้ backend migrate ก่อน — ถ้าเจอ ให้ใช้ค่า global นั้นชั่วคราว
        if "enabled" in data and symbol not in data:
            return data["enabled"]
        return data.get(symbol, False)
    except Exception:
        return False

def run_auto_trade(a, symbol):
    """เช็คทุก loop: ถ้าสวิตช์ของเหรียญนี้เปิด -> เปิด/ปิดไม้ในสมุด (journal) ให้อัตโนมัติ
    เรียกผ่าน backend API ตัวเดียวกับที่ dashboard ใช้ ไม่เขียน logic ซ้ำ"""
    if not auto_enabled(symbol):
        return
    try:
        j = _api_get("/journal")
    except Exception as e:
        log(f"[AUTO] ต่อ backend ไม่ได้ ({e}) — ข้ามรอบนี้ ต้องเปิด uvicorn ด้วย")
        return

    positions = j.get("positions", {})
    t = positions.get(symbol)
    price = j.get("prices", {}).get(symbol) or a["price"]

    if t is None:
        # ยังไม่มีไม้ -> เปิดถ้าเงื่อนไขครบ
        if a["regime"] == "TREND_UP" and a["bullish"]:
            stop = min(a["swing_low"], a["ma_slow"])
            if stop < price:
                try:
                    _api_post("/journal/open", {
                        "stop": round(stop, 2), "target": 0, "risk_pct": 1.0,
                        "reason": f"[AUTO] เข้าตามสัญญาณ MA{FAST}/{SLOW} ผ่าน regime filter",
                    })
                    alert("auto_open", price, f"🤖 Auto เปิดไม้ที่ {price:,.2f} (stop {stop:,.2f})")
                    log(f"[AUTO] เปิดไม้ที่ {price:,.2f} | stop={stop:,.2f} | regime={a['regime']} slope={a['slope_pct']:+.2f}% spread={a['spread_pct']:.2f}%")
                except Exception as e:
                    log(f"[AUTO] เปิดไม้ไม่สำเร็จ: {e}")
    else:
        # มีไม้อยู่ -> ปิดถ้าแตะ stop/target หรือสัญญาณดับ
        hit_stop = price <= t["stop"]
        hit_target = t["target"] and price >= t["target"]
        signal_off = not (a["regime"] == "TREND_UP" and a["bullish"])
        if hit_stop or hit_target or signal_off:
            reason = "stop" if hit_stop else "target" if hit_target else "สัญญาณดับ"
            try:
                _api_post("/journal/close", {
                    "symbol": symbol,
                    "followed_plan": True,
                    "note": f"[AUTO] ปิดตามเงื่อนไข: {reason}",
                })
                alert(f"auto_close_{symbol}", price, f"🤖 [{symbol}] Auto ปิดไม้ที่ {price:,.2f} ({reason})")
                log(f"[AUTO][{symbol}] ปิดไม้ที่ {price:,.2f} เหตุผล={reason}")
            except Exception as e:
                log(f"[AUTO] ปิดไม้ไม่สำเร็จ: {e}")

# ---------------- CONFIG ----------------
# gold จริง (XAU) ไม่มีสปอตบน Binance -> ใช้ PAXG (โทเค็นหนุนทองคำจริง) แทน
# ---- ย้ายทั้งระบบมา Binance TH แล้ว (29 ก.ค. 2569) ----
# ยืนยัน symbol จริงจาก binance_th_test.py: ต่อกันตรงๆ ไม่มีขีด เช่น BTCTHB
# เลือกเฉพาะเหรียญหลัก (market cap สูง สภาพคล่องดี) จาก 12 คู่ THB ที่มีทั้งหมด
# ตัดออก: USDTTHB (นี่คือคู่แลกเงิน ไม่ใช่สินทรัพย์ให้เทรดตามเทรนด์)
#         ASTERTHB, ZENTTHB, ATHTHB, VELOTHB, PLUMETHB (เหรียญเล็ก สภาพคล่องต่ำ
#         ไม่เหมาะกับระบบที่เน้นความสม่ำเสมอ/พิสูจน์ได้)
# หมายเหตุ: ไม่มี PAXG (โทเค็นทองคำ) บน Binance TH — ตัดออกจากลิสต์ ยังไม่มีตัวแทนทองคำ
WATCHLIST = [
    {"symbol": "BTCTHB", "exchange": "binance_th"},
    {"symbol": "ETHTHB", "exchange": "binance_th"},
    {"symbol": "BNBTHB", "exchange": "binance_th"},
    {"symbol": "SOLTHB", "exchange": "binance_th"},
    {"symbol": "XRPTHB", "exchange": "binance_th"},
]
SYMBOL = WATCHLIST[0]["symbol"]  # backward-compat
TIMEFRAME   = "1h"
FAST, SLOW  = 20, 50
PORT_SIZE   = 100_000     # ขนาดพอร์ต (ให้ตรงกับสมุดเทรด)
RISK_PCT    = 1.0         # เสี่ยงต่อไม้ %
REFRESH_SEC = 60

# เกณฑ์แยก regime (จุดเริ่มต้นที่สมเหตุสมผล — ควร backtest จูนต่อ)
SLOPE_BARS   = 10         # วัดความชัน MA50 ย้อนหลังกี่แท่ง
SLOPE_MIN    = 0.15       # MA50 ต้องขยับกี่ % ใน SLOPE_BARS ถึงนับว่ามีเทรนด์
SPREAD_MIN   = 0.25       # MA20 กับ MA50 ต้องห่างกันกี่ % ถึงนับว่าเส้นถ่างจริง

# สถิติจาก backtest จริงของเรา (BTC 1d, MA20/50+stop10%) — ความจริงไว้เตือนสติ
STATS_NOTE = ("สถิติระบบนี้จาก backtest 8 ปี: win rate ~46%, "
              "แพ้ไม้เฉลี่ย ~-6% (ไม่มี stop) | ครึ่งหลังของข้อมูล แพ้ Buy&Hold ด้วยซ้ำ "
              "-> สัญญาณคือแต้มต่อบางๆ ไม่ใช่คำพยากรณ์")

# ---------------- สมองวิเคราะห์ (pure function — บอทอนาคตใช้ตัวนี้ร่วมกัน) ----------------

def sma(values, n):
    return sum(values[-n:]) / n

def analyze(closes):
    """รับลิสต์ราคาปิด (แท่งที่ปิดแล้วเท่านั้น) -> คืน dict ผลวิเคราะห์
    ไม่มี side effect ใดๆ ทดสอบง่าย / ให้บอทเรียกใช้ได้เลย"""
    ma_fast = sma(closes, FAST)
    ma_slow = sma(closes, SLOW)

    # 1) ทิศสัญญาณพื้นฐาน
    bullish = ma_fast > ma_slow

    # 2) Regime: ตลาดมีเทรนด์จริงไหม?
    ma_slow_past = sma(closes[:-SLOPE_BARS], SLOW)          # MA50 เมื่อ N แท่งก่อน
    slope_pct  = (ma_slow - ma_slow_past) / ma_slow_past * 100
    spread_pct = abs(ma_fast - ma_slow) / ma_slow * 100

    trending = abs(slope_pct) >= SLOPE_MIN and spread_pct >= SPREAD_MIN
    if trending:
        regime = "TREND_UP" if slope_pct > 0 else "TREND_DOWN"
    else:
        regime = "SIDEWAYS"

    # 3) ระดับ stop อ้างอิงโครงสร้าง: ก้นต่ำสุด 10 แท่งล่าสุด กับเส้น MA50
    swing_low = min(closes[-10:])

    return {
        "price": closes[-1], "ma_fast": ma_fast, "ma_slow": ma_slow,
        "bullish": bullish, "regime": regime,
        "slope_pct": slope_pct, "spread_pct": spread_pct,
        "swing_low": swing_low,
    }

def position_size(port, risk_pct, entry, stop):
    """ขนาดไม้ที่ทำให้โดน stop แล้วเสียเท่ากับ risk ที่ยอมรับพอดี"""
    risk_money = port * risk_pct / 100
    per_unit = entry - stop
    if per_unit <= 0:
        return 0, 0
    units = risk_money / per_unit
    return units, min(units * entry, port)

# ---------------- แปลผลเป็นคำแนะนำที่ซื่อสัตย์ ----------------

def advise(a):
    lines = []
    p = a["price"]
    lines.append(f"ราคา {p:,.2f} | MA{FAST}={a['ma_fast']:,.2f} MA{SLOW}={a['ma_slow']:,.2f}")
    lines.append(f"ความชัน MA{SLOW}: {a['slope_pct']:+.2f}%/{SLOPE_BARS}แท่ง | "
                 f"ระยะห่างเส้น: {a['spread_pct']:.2f}%")

    if a["regime"] == "SIDEWAYS":
        lines.append("สภาพตลาด: SIDEWAYS (เส้นพันกัน/เทรนด์ไม่ชัด)")
        lines.append(">> โซนอันตรายของระบบ MA — สัญญาณช่วงนี้เชื่อถือได้ต่ำ")
        lines.append(">> คำแนะนำที่ดีที่สุดตอนนี้คือ: นั่งทับมือไว้ รอเส้นถ่างออกก่อน")
    elif a["regime"] == "TREND_DOWN":
        lines.append("สภาพตลาด: TREND DOWN (แนวโน้มใหญ่ชี้ลง)")
        lines.append(">> เราเล่นฝั่งซื้ออย่างเดียว = ช่วงนี้ไม่มีไม้ให้เล่น ถือเงินสดคือ position")
    else:  # TREND_UP
        lines.append("สภาพตลาด: TREND UP (แนวโน้มใหญ่ชี้ขึ้น)")
        if a["bullish"]:
            stop = min(a["swing_low"], a["ma_slow"])   # เลือกจุดที่ลึกกว่าเพื่อกัน whipsaw
            stop_pct = (p - stop) / p * 100
            units, cost = position_size(PORT_SIZE, RISK_PCT, p, stop)
            lines.append(f">> เงื่อนไขฝั่งซื้อครบ: MA{FAST} อยู่เหนือ MA{SLOW} ในตลาดมีเทรนด์")
            lines.append(f">> ถ้าจะเข้า (ตัดสินใจเองนะ): stop แนะนำ ~{stop:,.2f} (-{stop_pct:.2f}%)")
            lines.append(f">> ขนาดไม้ตาม risk {RISK_PCT}%: {units:.6f} BTC (~{cost:,.0f} USDT)")
            lines.append(f">> จังหวะที่ได้เปรียบกว่า: รอราคาย่อใกล้ MA{FAST} แล้วหยุดลง ไม่ไล่ราคาที่ลอยสูง")
        else:
            lines.append(f">> เทรนด์ขึ้นแต่ MA{FAST} ยังอยู่ใต้ MA{SLOW} — รอสัญญาณตัดขึ้นก่อน อย่าชิงเข้า")

    lines.append(f"[ความจริงติดจอ] {STATS_NOTE}")
    return "\n".join(lines)

# ---------------- I/O LOOP ----------------

def main():
    exchanges = {"binance_th": binance_th.BinanceTHExchange()}
    print(f"Trading Copilot — {len(WATCHLIST)} สินทรัพย์ {TIMEFRAME} | "
          f"อัปเดตทุก {REFRESH_SEC}s | Ctrl+C เพื่อหยุด")
    print("=" * 70)
    while True:
        for asset in WATCHLIST:
            symbol, ex = asset["symbol"], exchanges[asset["exchange"]]
            try:
                ohlcv = ex.fetch_ohlcv(symbol, TIMEFRAME, limit=SLOW + SLOPE_BARS + 5)
                closes = [c[4] for c in ohlcv[:-1]]     # ตัดแท่งที่ยังไม่ปิดทิ้งเสมอ
                a = analyze(closes)
                log(f"[{symbol}] " + advise(a).replace("\n", " | "))

                # ---- แจ้งเตือนเฉพาะตอนสถานะเปลี่ยน (แยก key ต่อเหรียญ) ----
                alert(f"regime_{symbol}", a["regime"],
                      f"🧭 [{symbol}] Regime เปลี่ยนเป็น {a['regime']}\n"
                      f"ราคา {a['price']:,.2f} | MA{FAST}={a['ma_fast']:,.2f} MA{SLOW}={a['ma_slow']:,.2f}")
                can_trade = a["regime"] == "TREND_UP" and a["bullish"]
                if can_trade:
                    stop_ref = min(a["swing_low"], a["ma_slow"])
                    alert(f"can_trade_{symbol}", True,
                          f"⚡ [{symbol}] สัญญาณฝั่งซื้อครบ! ({datetime.now():%H:%M})\n"
                          f"ราคา {a['price']:,.2f} | stop แนะนำ ~{stop_ref:,.2f}\n"
                          f"เปิด dashboard ดูก่อนตัดสินใจ — อย่าไล่ราคาที่ลอยสูง")
                else:
                    alert(f"can_trade_{symbol}", False,
                          f"🔕 [{symbol}] สัญญาณฝั่งซื้อดับลง ({a['regime']}) — กลับสู่โหมดรอ")

                run_auto_trade(a, symbol)   # เช็คสวิตช์ auto-trade ทุกรอบ ต่อเหรียญ

            except Exception as e:
                log(f"ERROR [{symbol}]: {e} — ลองใหม่รอบหน้า")
        time.sleep(REFRESH_SEC)

if __name__ == "__main__":
    main()
