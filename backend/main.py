"""
Trading Dashboard Backend — FastAPI
====================================
ห่อสมองเดิมทั้งหมด ไม่เขียน logic ใหม่:
  - /api/analysis   -> copilot.analyze() ตัวเดิม
  - /api/candles    -> ccxt (Binance)
  - /api/journal    -> อ่าน/เขียน journal_state.json (format เดียวกับ journal.py)
  - /api/bot        -> อ่าน paper_state.json + ท้าย log

วางไฟล์นี้ไว้ในโฟลเดอร์เดียวกับ copilot.py / journal_state.json / paper_state.json
รัน:  pip install fastapi uvicorn ccxt
      uvicorn main:app --reload --port 8000
"""

import json
import os
import sys
import threading
import time
from datetime import datetime

import ccxt
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

# ให้ import copilot.py / binance_th.py ที่อยู่โฟลเดอร์เดียวกันได้
_here = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _here)
sys.path.insert(0, os.path.dirname(_here))  # เผื่อวางไว้ใน backend/ ย่อย
from copilot import analyze, position_size, FAST, SLOW, SLOPE_BARS, RISK_PCT  # สมองเดิม
import binance_th
from futures_api import router as futures_router  # เมนู futures แยก (เงินปลอม)

# ---- ย้ายทั้งระบบมา Binance TH แล้ว (29 ก.ค. 2569) ----
# ยืนยัน symbol จริงจาก binance_th_test.py — เลือกเฉพาะเหรียญหลักสภาพคล่องดี
# ตัดออก: USDTTHB (คู่แลกเงิน ไม่ใช่สินทรัพย์เทรดตามเทรนด์), เหรียญเล็กสภาพคล่องต่ำ
# หมายเหตุ: ไม่มี PAXG (ทองคำ) บน Binance TH — ตัดออก ยังไม่มีตัวแทนทองคำตอนนี้
WATCHLIST = [
    {"symbol": "BTCTHB", "exchange": "binance_th"},
    {"symbol": "ETHTHB", "exchange": "binance_th"},
    {"symbol": "BNBTHB", "exchange": "binance_th"},
    {"symbol": "SOLTHB", "exchange": "binance_th"},
    {"symbol": "XRPTHB", "exchange": "binance_th"},
]
SYMBOL_LIST = [a["symbol"] for a in WATCHLIST]
SYMBOL = SYMBOL_LIST[0]

EXCHANGES = {"binance_th": binance_th.BinanceTHExchange()}

# บอท (paper_bot.py) เป็นกลุ่มควบคุมของการทดลอง — เทรด BTC/USDT ผ่าน Binance Global
# มาตั้งแต่ต้น ต้อง "คงเดิม" เสมอ ไม่สลับมา THB ตามหลัก ไม่งั้นเทียบผลกันไม่ได้
BOT_SYMBOL = "BTC/USDT"
_bot_exchange = ccxt.binance()

def asset_cfg(symbol: str) -> dict:
    for a in WATCHLIST:
        if a["symbol"] == symbol:
            return a
    raise HTTPException(400, f"ไม่รู้จัก symbol {symbol}")

def ex_for(symbol: str):
    return EXCHANGES[asset_cfg(symbol)["exchange"]]
FEE_RATE = 0.001
INITIAL = 10_000.0
MAX_RISK_PCT = 2.0
JOURNAL_FILE = "journal_state.json"
BOT_STATE = "paper_state.json"
BOT_LOG = "paper_trades.log"
AUTO_FILE = "auto_toggle.json"
AUTO_LOG = "auto_trade.log"
AUTO_POLL_SEC = 60   # ความถี่ที่ background thread เช็คสัญญาณ+auto-trade (แยกจาก REFRESH_SEC ของ copilot.py console)

# journal_state.json ถูกอ่าน/เขียนได้ทั้งจาก HTTP handler (thread pool ของ uvicorn)
# และจาก background auto-trade thread พร้อมกัน -> ต้องมี lock กันสองฝั่งเขียนชนกัน
_journal_lock = threading.RLock()

app = FastAPI(title="Trading Copilot API")
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173"],
                   allow_methods=["*"], allow_headers=["*"])
app.include_router(futures_router)

# ---------------- helpers ----------------

def load_json(path, default):
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return default

def save_json(path, data):
    # เขียนแบบ atomic (เขียนไฟล์ชั่วคราวแล้ว rename) กันคนอ่านเจอไฟล์เขียนค้างครึ่งเดียว
    # จำเป็นตอนนี้เพราะมีทั้ง background auto-trade thread และ HTTP handler เขียนไฟล์เดียวกัน
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)

def journal_default():
    return {"cash": INITIAL, "positions": {s: None for s in SYMBOL_LIST}, "closed_trades": []}

def journal_migrate(s):
    """รองรับ state เก่าที่ยังใช้ open_trade เดี่ยว (ก่อนมี multi-asset)"""
    if "positions" not in s:
        old = s.pop("open_trade", None)
        s["positions"] = {sym: (old if sym == SYMBOL else None) for sym in SYMBOL_LIST}
    for sym in SYMBOL_LIST:
        s["positions"].setdefault(sym, None)
    return s

def live_price(symbol: str = SYMBOL) -> float:
    return ex_for(symbol).fetch_ticker(symbol)["last"]

def bot_live_price() -> float:
    """ราคาเฉพาะสำหรับพอร์ตบอท (BTC/USDT คงเดิม ไม่สลับมา THB)"""
    return _bot_exchange.fetch_ticker(BOT_SYMBOL)["last"]

@app.get("/api/assets")
def assets():
    return {"watchlist": WATCHLIST}

# ---------------- market ----------------

@app.get("/api/candles")
def candles(symbol: str = SYMBOL, timeframe: str = "1h", limit: int = 200):
    ohlcv = ex_for(symbol).fetch_ohlcv(symbol, timeframe, limit=min(limit, 500))
    return [{"time": c[0] // 1000, "open": c[1], "high": c[2],
             "low": c[3], "close": c[4]} for c in ohlcv]

def _run_analysis(symbol: str) -> dict:
    """สมองวิเคราะห์ — ใช้ร่วมกันทั้ง /api/analysis (แสดงผลบนจอ) และ background
    auto-trade thread (ตัดสินใจจริง) เพื่อไม่ให้สองที่นี้เห็นสัญญาณไม่ตรงกัน"""
    ohlcv = ex_for(symbol).fetch_ohlcv(symbol, "1h", limit=SLOW + SLOPE_BARS + 5)
    closes = [c[4] for c in ohlcv[:-1]]          # แท่งปิดแล้วเท่านั้น
    a = analyze(closes)
    a["symbol"] = symbol
    a["live_price"] = ohlcv[-1][4]
    a["can_trade"] = a["regime"] == "TREND_UP" and a["bullish"]
    return a

@app.get("/api/analysis")
def analysis(symbol: str = SYMBOL):
    return _run_analysis(symbol)

# ---------------- journal (เงินปลอม) ----------------

class OpenTrade(BaseModel):
    symbol: str = SYMBOL
    stop: float
    target: float = 0
    risk_pct: float = Field(gt=0, le=MAX_RISK_PCT)
    reason: str = Field(min_length=4)

class CloseSymbol(BaseModel):
    symbol: str = SYMBOL

class CloseTrade(BaseModel):
    symbol: str = SYMBOL
    followed_plan: bool
    note: str = ""

# ---------------- auto-trade toggle (แยกรายเหรียญ) ----------------

class AutoToggle(BaseModel):
    symbol: str
    enabled: bool

def auto_default():
    return {sym: False for sym in SYMBOL_LIST}

def auto_migrate(s):
    """รองรับไฟล์เก่าที่เคยเป็น global {"enabled": bool} ตัวเดียว
    -> ใช้ค่าเดิมนั้นตั้งต้นให้ทุกเหรียญ แล้วเปลี่ยนโครงสร้างถาวร"""
    if "enabled" in s and not any(sym in s for sym in SYMBOL_LIST):
        old_value = s["enabled"]
        s = {sym: old_value for sym in SYMBOL_LIST}
    for sym in SYMBOL_LIST:
        s.setdefault(sym, False)
    return s

@app.get("/api/auto")
def get_auto():
    return auto_migrate(load_json(AUTO_FILE, auto_default()))

@app.post("/api/auto")
def set_auto(body: AutoToggle):
    if body.symbol not in SYMBOL_LIST:
        raise HTTPException(400, f"ไม่รู้จัก symbol {body.symbol}")
    s = auto_migrate(load_json(AUTO_FILE, auto_default()))
    s[body.symbol] = body.enabled
    save_json(AUTO_FILE, s)
    return s

# ---------------- background auto-trade loop (ทำงานอยู่ใน uvicorn เอง) ----------------
# เดิมต้องรัน `python copilot.py` แยกเทอร์มินัลถึงจะเช็ค/เปิด/ปิดไม้จริง — สวิตช์ในเว็บ
# แค่เขียน flag เฉยๆ ถ้าลืมรัน copilot.py ก็เหมือนสวิตช์เปิดแต่ไม่มีใครทำงานให้เลย
# ย้าย loop มาไว้เป็น thread ในนี้แทน -> แค่เปิด uvicorn (ต้องเปิดอยู่แล้วให้เว็บทำงาน)
# ก็ทำงานจริงทันที ไม่ต้องเปิดเทอร์มินัลที่ 3 อีกต่อไป

_auto_status: dict[str, dict] = {}   # symbol -> {checked_at, regime, can_trade, action, detail}

def auto_log(msg: str) -> None:
    line = f"{datetime.now():%Y-%m-%d %H:%M:%S} | {msg}"
    print(line)
    with open(AUTO_LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")

def _auto_trade_tick() -> None:
    """เช็คทุกเหรียญที่เปิดสวิตช์ไว้ 1 รอบ — ใช้ analyze() ก้อนเดียวกับที่ /api/analysis
    แสดงบนจอ (ผ่าน _run_analysis) เพื่อไม่ให้สิ่งที่เห็นกับสิ่งที่บอททำไม่ตรงกัน"""
    enabled = auto_migrate(load_json(AUTO_FILE, auto_default()))
    for symbol in SYMBOL_LIST:
        if not enabled.get(symbol):
            continue
        try:
            a = _run_analysis(symbol)
        except Exception as e:
            _auto_status[symbol] = {"checked_at": datetime.now().isoformat(timespec="seconds"),
                                     "action": "error", "detail": str(e)}
            auto_log(f"[{symbol}] ดึงราคา/วิเคราะห์ไม่ได้: {e} — ลองใหม่รอบหน้า")
            continue

        with _journal_lock:
            j = journal_migrate(load_json(JOURNAL_FILE, journal_default()))
            t = j["positions"].get(symbol)
        price = a["live_price"]

        status = {"checked_at": datetime.now().isoformat(timespec="seconds"),
                  "regime": a["regime"], "can_trade": a["can_trade"], "price": price}

        if t is None:
            if a["can_trade"]:
                stop = min(a["swing_low"], a["ma_slow"])
                if stop < price:
                    try:
                        r = open_trade(OpenTrade(
                            symbol=symbol, stop=round(stop, 2), risk_pct=RISK_PCT,
                            reason=f"[AUTO] เข้าตามสัญญาณ MA{FAST}/{SLOW} ผ่าน regime filter"))
                        status["action"] = "opened"
                        status["detail"] = f"เปิดที่ {r['entry']:,.2f}"
                        auto_log(f"[{symbol}] AUTO เปิดไม้ที่ {r['entry']:,.2f} | stop={stop:,.2f} "
                                 f"| regime={a['regime']} slope={a['slope_pct']:+.2f}%")
                    except HTTPException as e:
                        status["action"] = "error"
                        status["detail"] = e.detail
                        auto_log(f"[{symbol}] เปิดไม้ไม่สำเร็จ: {e.detail}")
                else:
                    status["action"] = "waiting"
                    status["detail"] = "stop คำนวณได้สูงกว่าราคาปัจจุบัน — ข้ามรอบนี้"
            else:
                status["action"] = "waiting"
                status["detail"] = f"regime={a['regime']} — เงื่อนไขฝั่งซื้อยังไม่ครบ"
        else:
            hit_stop = price <= t["stop"]
            hit_target = t["target"] and price >= t["target"]
            signal_off = not a["can_trade"]
            if hit_stop or hit_target or signal_off:
                reason = "stop" if hit_stop else "target" if hit_target else "สัญญาณดับ"
                try:
                    r = close_trade(CloseTrade(symbol=symbol, followed_plan=True,
                                               note=f"[AUTO] ปิดตามเงื่อนไข: {reason}"))
                    status["action"] = "closed"
                    status["detail"] = f"ปิดที่ {r['exit']:,.2f} ({reason}) PnL {r['pnl_pct']:+.2f}%"
                    auto_log(f"[{symbol}] AUTO ปิดไม้ที่ {r['exit']:,.2f} เหตุผล={reason}")
                except HTTPException as e:
                    status["action"] = "error"
                    status["detail"] = e.detail
                    auto_log(f"[{symbol}] ปิดไม้ไม่สำเร็จ: {e.detail}")
            else:
                status["action"] = "holding"
                status["detail"] = f"ถือตั้งแต่ {t['time_in']} @ {t['entry']:,.2f}"

        _auto_status[symbol] = status

def _auto_trade_loop() -> None:
    auto_log(f"Auto-trade thread เริ่มทำงานใน uvicorn เอง | เช็คทุก {AUTO_POLL_SEC}s "
             f"| ไม่ต้องรัน copilot.py แยกอีกต่อไปเพื่อให้ auto-trade ทำงาน")
    while True:
        try:
            _auto_trade_tick()
        except Exception as e:
            auto_log(f"ERROR ใน auto-trade loop: {e} — ลองใหม่รอบหน้า")
        time.sleep(AUTO_POLL_SEC)

threading.Thread(target=_auto_trade_loop, daemon=True, name="auto-trade").start()

@app.get("/api/auto/status")
def auto_status():
    """สถานะล่าสุดของบอทต่อเหรียญ — ให้หน้าเว็บเห็นว่า 'มีใครเฝ้าดูอยู่จริง' ไม่ใช่แค่ toggle ว่างๆ"""
    return _auto_status

@app.get("/api/journal")
def journal():
    s = journal_migrate(load_json(JOURNAL_FILE, journal_default()))
    positions_value = 0.0
    prices = {}
    for sym, t in s["positions"].items():
        if t:
            p = live_price(sym)
            prices[sym] = p
            positions_value += t["units"] * p
    equity = s["cash"] + positions_value
    return {**s, "equity": equity, "prices": prices}

@app.post("/api/journal/open")
def open_trade(body: OpenTrade):
    with _journal_lock:
        s = journal_migrate(load_json(JOURNAL_FILE, journal_default()))
        if body.symbol not in s["positions"]:
            raise HTTPException(400, f"ไม่รู้จัก symbol {body.symbol}")
        if s["positions"][body.symbol]:
            raise HTTPException(400, f"มีไม้ {body.symbol} เปิดอยู่แล้ว — ปิดก่อนถึงเปิดใหม่ได้")
        price = live_price(body.symbol)
        if body.stop >= price:
            raise HTTPException(400, "stop ต้องต่ำกว่าราคาปัจจุบัน (เราเล่นฝั่งซื้อ)")
        units, cost = position_size(s["cash"], body.risk_pct, price, body.stop)
        cost = min(cost, s["cash"])
        units = cost / price
        fee = cost * FEE_RATE
        s["cash"] -= (cost + fee)
        s["positions"][body.symbol] = {
            "symbol": body.symbol,
            "time_in": f"{datetime.now():%Y-%m-%d %H:%M:%S}",
            "entry": price, "stop": body.stop, "target": body.target,
            "units": units, "cost": cost, "fee_in": fee,
            "risk_pct": body.risk_pct, "reason": body.reason.strip(),
        }
        save_json(JOURNAL_FILE, s)
        return {"ok": True, "entry": price, "units": units}

@app.post("/api/journal/close")
def close_trade(body: CloseTrade):
    with _journal_lock:
        s = journal_migrate(load_json(JOURNAL_FILE, journal_default()))
        t = s["positions"].get(body.symbol)
        if not t:
            raise HTTPException(400, f"ไม่มีไม้ {body.symbol} เปิดอยู่")
        price = live_price(body.symbol)
        gross = t["units"] * price
        fee = gross * FEE_RATE
        s["cash"] += gross - fee
        t.update(time_out=f"{datetime.now():%Y-%m-%d %H:%M:%S}", exit=price,
                 fee_out=fee, pnl_pct=(price / t["entry"] - 1) * 100,
                 pnl_money=gross - fee - t["cost"] - t["fee_in"],
                 followed_plan=body.followed_plan, note=body.note.strip())
        s["closed_trades"].append(t)
        s["positions"][body.symbol] = None
        save_json(JOURNAL_FILE, s)
        return {"ok": True, "exit": price, "pnl_pct": t["pnl_pct"]}

@app.get("/api/journal/stats")
def stats():
    s = journal_migrate(load_json(JOURNAL_FILE, journal_default()))
    tr = s["closed_trades"]
    if not tr:
        return {"trades": 0}
    wins = [t for t in tr if t["pnl_pct"] > 0]
    losses = [t for t in tr if t["pnl_pct"] <= 0]
    followed = [t for t in tr if t.get("followed_plan")]
    wr = len(wins) / len(tr)
    aw = sum(t["pnl_pct"] for t in wins) / len(wins) if wins else 0
    al = sum(t["pnl_pct"] for t in losses) / len(losses) if losses else 0
    return {"trades": len(tr), "win_rate": wr * 100,
            "avg_win": aw, "avg_loss": al,
            "expectancy": wr * aw + (1 - wr) * al,
            "discipline": len(followed) / len(tr) * 100,
            "off_plan_pnl": sum(t["pnl_pct"] for t in tr if not t.get("followed_plan"))}

# ---------------- bot (อ่านอย่างเดียว) ----------------

@app.get("/api/bot")
def bot():
    s = load_json(BOT_STATE, None)
    if s is None:
        return {"running": False}
    price = bot_live_price()
    equity = s["cash"] + s["units"] * price
    tail = []
    if os.path.exists(BOT_LOG):
        with open(BOT_LOG, encoding="utf-8") as f:
            tail = f.readlines()[-20:]
    # ถือว่า "รันอยู่" ถ้า log ขยับใน 5 นาทีล่าสุด
    running = False
    if os.path.exists(BOT_LOG):
        running = (datetime.now().timestamp() - os.path.getmtime(BOT_LOG)) < 300
    return {"running": running, "equity": equity, "holding": s["units"] > 0,
            "trades": s.get("trades", 0), "log_tail": tail}
