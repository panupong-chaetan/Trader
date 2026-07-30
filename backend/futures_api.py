"""
Futures API — APIRouter แยกจาก spot เดิมทั้งหมด
===============================================
เสียบเข้า main.py เดิมด้วย 2 บรรทัด (ไม่ต้องแก้ endpoint เดิมแม้แต่บรรทัดเดียว):

    from futures_api import router as futures_router
    app.include_router(futures_router)

ทุก path อยู่ใต้ /api/futures/... จึงไม่ชนกับ /api/analysis, /api/journal ของ spot

รวมบอทอัตโนมัติ (เดิมเคยเป็น futures_bot.py ต้องรันแยกเทอร์มินัล) เข้ามาเป็น
background thread ในนี้เลย เหตุผลเดียวกับที่ทำกับ spot auto-trade: เดิมถ้าลืมเปิด
เทอร์มินัลที่ 3 ไว้ สวิตช์ในเว็บ (ถ้ามี) ก็จะไม่มีความหมายเลย — ย้ายมาไว้ในนี้
รับประกันว่าแค่เปิด uvicorn ก็พร้อมทำงานทันที (ปิดอยู่โดย default ต้องกดเปิดเอง
ในหน้าเว็บ เพราะเป็นการเทรดด้วย leverage อัตโนมัติ ควรเป็นการตัดสินใจที่ชัดเจน)
"""

import json
import os
import sys
import threading
import time
from datetime import datetime

import ccxt
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

import futures as fx

_here = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _here)
sys.path.insert(0, os.path.dirname(_here))
from copilot import analyze, FAST, SLOW, SLOPE_BARS, RISK_PCT  # สมองเดียวกับบอท spot

router = APIRouter(prefix="/api/futures", tags=["futures"])

# ให้ TP/SL/liquidation เดินต่อแม้ปิดเบราว์เซอร์
fx.start_background_ticker(interval=10)

# ─────────────── บอทอัตโนมัติ (BTC/USDT เท่านั้น, leverage ตายตัว 5x) ───────────────
BOT_SYMBOL = "BTC/USDT"
BOT_TIMEFRAME = "1h"
BOT_POLL_SEC = 60
BOT_LEVERAGE = 5          # ตายตัว ไม่มีช่องให้ UI ปรับสูงกว่านี้ กันมือลื่นขยับ risk
BOT_MIN_MARGIN = 6.0
BOT_TOGGLE_FILE = os.path.join(_here, "futures_bot_toggle.json")
BOT_LOG = os.path.join(_here, "futures_bot.log")

_bot_ex = ccxt.binanceusdm({"enableRateLimit": True})
_bot_status: dict = {"enabled": False, "checked_at": None, "action": None, "detail": None}


def bot_log(msg: str) -> None:
    line = f"{datetime.now():%Y-%m-%d %H:%M:%S} | {msg}"
    print(line)
    with open(BOT_LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def bot_enabled() -> bool:
    if not os.path.exists(BOT_TOGGLE_FILE):
        return False
    try:
        return json.load(open(BOT_TOGGLE_FILE, encoding="utf-8")).get("enabled", False)
    except Exception:
        return False


def set_bot_enabled(v: bool) -> None:
    with open(BOT_TOGGLE_FILE, "w", encoding="utf-8") as f:
        json.dump({"enabled": v}, f)


def _bot_decide(a: dict, closes: list) -> tuple[str | None, float | None]:
    if a["regime"] == "TREND_UP" and a["bullish"]:
        return "long", min(a["swing_low"], a["ma_slow"])
    if a["regime"] == "TREND_DOWN" and not a["bullish"]:
        return "short", max(max(closes[-10:]), a["ma_slow"])
    return None, None


def _bot_size_margin(equity: float, price: float, stop: float, leverage: int) -> float:
    stop_dist_pct = abs(price - stop) / price
    if stop_dist_pct <= 0:
        return 0.0
    return (equity * RISK_PCT / 100) / (stop_dist_pct * leverage)


def _futures_bot_tick() -> None:
    enabled = bot_enabled()
    _bot_status["enabled"] = enabled
    if not enabled:
        return

    try:
        ohlcv = _bot_ex.fetch_ohlcv(BOT_SYMBOL, BOT_TIMEFRAME, limit=SLOW + SLOPE_BARS + 5)
        closes = [c[4] for c in ohlcv[:-1]]
        a = analyze(closes)
        side_wanted, stop = _bot_decide(a, closes)
    except Exception as e:
        _bot_status.update(checked_at=datetime.now().isoformat(timespec="seconds"),
                           action="error", detail=str(e))
        bot_log(f"ดึงราคา/วิเคราะห์ไม่ได้: {e} — ลองใหม่รอบหน้า")
        return

    acc = fx.account()
    equity = acc["equity"]
    existing = next((p for p in acc["positions"] if p["symbol"] == BOT_SYMBOL), None)
    status = {"checked_at": datetime.now().isoformat(timespec="seconds"),
              "enabled": True, "regime": a["regime"], "price": a["price"]}

    if existing:
        held = existing["side"]
        if side_wanted != held:
            reason = "สัญญาณดับ" if side_wanted is None else f"สัญญาณกลับด้าน -> {side_wanted}"
            try:
                r = fx.close_position(BOT_SYMBOL, 1.0, f"[BOT] {reason}", trigger="manual")
                status.update(action="closed", detail=f"ปิด {held.upper()} เพราะ {reason} "
                              f"PnL {r['net_pnl']:+.2f} USDT")
                bot_log(f"ปิด {held.upper()} เพราะ {reason} | PnL {r['net_pnl']:+.2f} USDT")
            except ValueError as e:
                status.update(action="error", detail=str(e))
        else:
            status.update(action="holding",
                          detail=f"ถือ {held.upper()} อยู่ | ROE {existing['roe_pct']:+.1f}%")
    elif side_wanted:
        margin = _bot_size_margin(equity, a["price"], stop, BOT_LEVERAGE)
        floored = margin < BOT_MIN_MARGIN
        margin = max(margin, BOT_MIN_MARGIN)
        if margin > acc["available_margin"] * 0.9:
            status.update(action="waiting",
                          detail=f"margin ไม่พอ (ต้องการ {margin:.2f} เหลือ {acc['available_margin']:.2f})")
        else:
            try:
                r = fx.open_position(BOT_SYMBOL, side_wanted, margin=round(margin, 2),
                                     leverage=BOT_LEVERAGE, sl=round(stop, 2),
                                     reason=f"[BOT] {a['regime']} MA{FAST}/{SLOW} "
                                            f"slope={a['slope_pct']:+.2f}%")
                note = " (ปัดขึ้นถึงขั้นต่ำ)" if floored else ""
                status.update(action="opened",
                              detail=f"เปิด {side_wanted.upper()} margin={margin:.2f}{note} "
                                     f"@ {r['entry_price']:,.2f}")
                bot_log(f"เปิด {side_wanted.upper()} margin={margin:.2f} {BOT_LEVERAGE}x "
                       f"@ {r['entry_price']:,.2f} sl={stop:,.2f}")
            except ValueError as e:
                status.update(action="error", detail=str(e))
    else:
        status.update(action="waiting", detail=f"regime={a['regime']} — ยังไม่เข้าเงื่อนไข")

    _bot_status.update(status)


def _futures_bot_loop() -> None:
    bot_log(f"Futures bot thread พร้อมทำงาน | {BOT_SYMBOL} {BOT_TIMEFRAME} | "
           f"leverage {BOT_LEVERAGE}x ตายตัว | ปิดอยู่โดย default รอเปิดจากหน้าเว็บ")
    while True:
        try:
            _futures_bot_tick()
        except Exception as e:
            bot_log(f"ERROR ใน bot loop: {e} — ลองใหม่รอบหน้า")
        time.sleep(BOT_POLL_SEC)


threading.Thread(target=_futures_bot_loop, daemon=True, name="futures-bot").start()


# ─────────────── schemas ───────────────

class OrderIn(BaseModel):
    symbol: str
    side: str = Field(pattern="^(long|short)$")
    margin: float | None = Field(default=None, gt=0, description="USDT ที่วางเป็นหลักประกัน")
    qty: float | None = Field(default=None, gt=0, description="จำนวนเหรียญ (ถ้าระบุจะแทน margin)")
    leverage: int | None = Field(default=None, ge=1, le=125)
    tp: float | None = None
    sl: float | None = None
    reason: str = ""


class CloseIn(BaseModel):
    symbol: str
    portion: float = Field(default=1.0, gt=0, le=1)
    note: str = ""


class LeverageIn(BaseModel):
    symbol: str
    leverage: int = Field(ge=1, le=125)


class ResetIn(BaseModel):
    balance: float | None = Field(default=None, gt=0)
    confirm: bool = False


# ─────────────── read ───────────────

@router.get("/account")
def get_account():
    """พอร์ต + ไม้ที่เปิดอยู่ (ตีราคาตลาดสด). เดิน tick ก่อนตอบ เพื่อให้เลขบนจอตรงกับ engine"""
    try:
        fx.tick()
    except Exception:
        pass  # ดึงราคาไม่ได้ก็ยังตอบพอร์ตล่าสุดได้
    return fx.account()


@router.get("/market")
def get_market(symbol: str | None = None):
    """ราคา mark + funding rate ของวอชลิสต์ (หรือตัวเดียวถ้าระบุ symbol)"""
    targets = [s for s in fx.SYMBOLS if not symbol or s["symbol"] == symbol]
    if not targets:
        raise HTTPException(400, f"ไม่รู้จัก {symbol}")
    out = []
    for s in targets:
        try:
            out.append({
                **s,
                "mark_price": fx.mark_price(s["symbol"]),
                "funding_rate_pct": fx.funding_rate(s["symbol"]) * 100,
            })
        except Exception as e:
            out.append({**s, "error": str(e)})
    return {"markets": out}


@router.get("/candles")
def get_candles(symbol: str = "BTC/USDT", tf: str = "15m", limit: int = Query(200, le=1000)):
    try:
        rows = fx.candles(symbol, tf, limit)
    except Exception as e:
        raise HTTPException(502, f"ดึงแท่งเทียนไม่ได้: {e}")
    return {"symbol": symbol, "timeframe": tf,
            "candles": [{"time": r[0] // 1000, "open": r[1], "high": r[2],
                         "low": r[3], "close": r[4], "volume": r[5]} for r in rows]}


@router.get("/preview")
def get_preview(symbol: str, side: str, margin: float, leverage: int,
                tp: float | None = None, sl: float | None = None):
    """คำนวณก่อนกด: qty, liq price, ค่าธรรมเนียมไปกลับ, ความเสี่ยงจริงเป็น USDT, R:R"""
    try:
        return fx.preview(symbol, side, margin, leverage, tp, sl)
    except Exception as e:
        raise HTTPException(400, str(e))


@router.get("/history")
def get_history(limit: int = Query(50, le=500)):
    return {"trades": fx.history(limit)}


@router.get("/stats")
def get_stats():
    return fx.stats()


# ─────────────── write ───────────────

@router.post("/order")
def post_order(body: OrderIn):
    if not body.margin and not body.qty:
        raise HTTPException(400, "ต้องระบุ margin หรือ qty อย่างน้อยหนึ่งอย่าง")
    try:
        return fx.open_position(
            body.symbol, body.side, margin=body.margin, qty=body.qty,
            leverage=body.leverage, tp=body.tp, sl=body.sl, reason=body.reason)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(502, f"เปิดไม้ไม่สำเร็จ: {e}")


@router.post("/close")
def post_close(body: CloseIn):
    try:
        return fx.close_position(body.symbol, body.portion, body.note)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(502, f"ปิดไม้ไม่สำเร็จ: {e}")


@router.post("/close-all")
def post_close_all():
    closed, failed = [], []
    for symbol in list(fx.load_state()["positions"].keys()):
        try:
            closed.append(fx.close_position(symbol, 1.0, "ปิดทั้งหมด"))
        except Exception as e:
            failed.append({"symbol": symbol, "error": str(e)})
    return {"closed": closed, "failed": failed}


@router.post("/leverage")
def post_leverage(body: LeverageIn):
    try:
        return fx.set_leverage(body.symbol, body.leverage)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/tick")
def post_tick():
    """เดินเวลาเอง 1 ครั้ง (ปกติ background ticker ทำให้อยู่แล้ว)"""
    return fx.tick()


@router.post("/reset")
def post_reset(body: ResetIn):
    if not body.confirm:
        raise HTTPException(400, "ต้องส่ง confirm=true — การล้างพอร์ตย้อนกลับไม่ได้")
    return {"ok": True, "wallet_balance": fx.reset(body.balance)["wallet_balance"]}


# ─────────────── บอทอัตโนมัติ ───────────────

class BotToggleIn(BaseModel):
    enabled: bool

@router.get("/bot-status")
def get_bot_status():
    """สถานะบอท — ให้หน้าเว็บเห็นว่าเช็คล่าสุดเมื่อไหร่ กำลังทำอะไรอยู่ ไม่ใช่สวิตช์ลอยๆ"""
    return {**_bot_status, "enabled": bot_enabled(), "symbol": BOT_SYMBOL,
            "leverage": BOT_LEVERAGE, "poll_sec": BOT_POLL_SEC}

@router.post("/bot-toggle")
def post_bot_toggle(body: BotToggleIn):
    set_bot_enabled(body.enabled)
    bot_log(f"บอทถูก{'เปิด' if body.enabled else 'ปิด'}จากหน้าเว็บ")
    return {"enabled": body.enabled}
