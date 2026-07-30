"""
Futures API — APIRouter แยกจาก spot เดิมทั้งหมด
===============================================
เสียบเข้า main.py เดิมด้วย 2 บรรทัด (ไม่ต้องแก้ endpoint เดิมแม้แต่บรรทัดเดียว):

    from futures_api import router as futures_router
    app.include_router(futures_router)

ทุก path อยู่ใต้ /api/futures/... จึงไม่ชนกับ /api/analysis, /api/journal ของ spot
"""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

import futures as fx

router = APIRouter(prefix="/api/futures", tags=["futures"])

# ให้ TP/SL/liquidation เดินต่อแม้ปิดเบราว์เซอร์
fx.start_background_ticker(interval=10)


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
