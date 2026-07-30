"""
Binance Futures Paper Trading Engine — ราคาจริง เงินปลอม
=========================================================
เครื่องยนต์จำลองการเทรด USDⓈ-M Perpetual Futures ให้ใกล้ของจริงเท่าที่จำเป็น
ต่อการ "ฝึกฝน สังเกต และทดลอง" โดยไม่ต้องมี API key และไม่มีเงินจริงเข้ามาเกี่ยวข้อง

สิ่งที่จำลองไว้ (เรื่องที่ทำให้ futures ต่างจาก spot อย่างมีนัยสำคัญ):
  - Leverage + Initial Margin        : margin = notional / leverage
  - Long / Short                    : กำไรได้ทั้งสองทาง
  - Liquidation                      : คำนวณราคาบังคับขายจาก maintenance margin จริง
  - Maintenance margin tier          : ตารางแบบย่อ (tier 1 = 0.4% ครอบคลุมไม้ขนาดฝึกซ้อม)
  - Funding rate                     : ดึงเรตจริง เก็บ/จ่ายทุก 8 ชม. (00/08/16 UTC)
  - Taker/Maker fee                  : 0.05% / 0.02% ของ notional
  - TP / SL                          : ตรวจทุก tick ด้วย mark price
  - Partial close                    : ปิดบางส่วน คิด PnL ตามสัดส่วน
  - Average entry                    : เติมไม้ทางเดิม -> ถัวเฉลี่ยราคาเข้า
  - One-way mode                     : 1 สัญลักษณ์ = 1 ฝั่ง (ตรงกับค่าเริ่มต้นของ Binance)

สิ่งที่ "ยัง" ไม่จำลอง (จงใจ — เพื่อไม่หลอกตัวเองว่าเหมือนของจริง 100%):
  - Order book / slippage / partial fill : เติมที่ mark price เต็มจำนวนทันที
  - Limit order รอคิว                    : ทุกคำสั่งเป็น market (taker)
  - Cross margin แบบรวมพอร์ตจริง         : ใช้ isolated ต่อไม้เป็นหลัก
  - ADL / insurance fund                 : liquidation = เสีย margin ก้อนนั้นทั้งก้อน

ไฟล์ที่เขียน: futures_state.json (พอร์ต) / futures_trades.log (บันทึกทุกเหตุการณ์)
ไม่แตะไฟล์ของ spot เดิม (journal_state.json / paper_state.json) เลย
"""

from __future__ import annotations

import json
import math
import os
import threading
import time
from datetime import datetime, timezone

import ccxt

# ───────────────────────────── CONFIG ─────────────────────────────

HERE = os.path.dirname(os.path.abspath(__file__))
STATE_FILE = os.path.join(HERE, "futures_state.json")
LOG_FILE = os.path.join(HERE, "futures_trades.log")

INITIAL_BALANCE = 10_000.0          # USDT ปลอมตั้งต้น
TAKER_FEE = 0.0005                  # 0.05%
MAKER_FEE = 0.0002                  # 0.02%
MAX_LEVERAGE = 125
MIN_NOTIONAL = 5.0                  # ขั้นต่ำต่อไม้ (USDT) ตามกฎ Binance
PRICE_TTL = 2.0                     # cache ราคา (วินาที) กันยิง API ถี่เกิน
FUNDING_INTERVAL_H = 8

# วอชลิสต์ futures — perpetual USDⓈ-M
SYMBOLS = [
    {"symbol": "BTC/USDT", "label": "BTC perp", "max_lev": 125},
    {"symbol": "ETH/USDT", "label": "ETH perp", "max_lev": 100},
    {"symbol": "SOL/USDT", "label": "SOL perp", "max_lev": 50},
    {"symbol": "BNB/USDT", "label": "BNB perp", "max_lev": 75},
]

# ตาราง maintenance margin แบบย่อ (notional เพดาน, อัตรา, ค่าหัก)
# ของจริงแยกตามเหรียญ; ไม้ขนาดฝึกซ้อมจะอยู่ tier แรกแทบทั้งหมด
MMR_TIERS = [
    (50_000, 0.0040, 0.0),
    (500_000, 0.0050, 50.0),
    (1_000_000, 0.0100, 2_550.0),
    (5_000_000, 0.0250, 17_550.0),
    (float("inf"), 0.0500, 142_550.0),
]

# ───────────────────────────── EXCHANGE ─────────────────────────────

_ex = ccxt.binanceusdm({"enableRateLimit": True})
_markets_loaded = False
_price_cache: dict[str, tuple[float, float]] = {}   # symbol -> (price, ts)
_funding_cache: dict[str, tuple[float, float]] = {}  # symbol -> (rate, ts)
_lock = threading.RLock()


def _ensure_markets():
    global _markets_loaded
    if not _markets_loaded:
        _ex.load_markets()
        _markets_loaded = True


def _resolve(symbol: str) -> str:
    """คืนสัญลักษณ์ที่ ccxt เวอร์ชันนี้รู้จัก (รองรับทั้ง BTC/USDT และ BTC/USDT:USDT)"""
    try:
        _ensure_markets()
    except Exception:
        return symbol
    if symbol in _ex.markets:
        return symbol
    base, _, quote = symbol.partition("/")
    quote = quote.split(":")[0]
    alt = f"{base}/{quote}:{quote}"
    return alt if alt in _ex.markets else symbol


def mark_price(symbol: str, force: bool = False) -> float:
    """mark price ล่าสุด (cache 2 วิ). ใช้ mark ไม่ใช่ last เพราะ liquidation ของจริงยึด mark"""
    now = time.time()
    hit = _price_cache.get(symbol)
    if hit and not force and now - hit[1] < PRICE_TTL:
        return hit[0]
    sym = _resolve(symbol)
    price = None
    try:
        fr = _ex.fetch_funding_rate(sym)
        price = float(fr.get("markPrice") or (fr.get("info") or {}).get("markPrice") or 0) or None
        rate = fr.get("fundingRate")
        if rate is not None:
            _funding_cache[symbol] = (float(rate), now)
    except Exception:
        pass
    if not price:
        price = float(_ex.fetch_ticker(sym)["last"])
    _price_cache[symbol] = (price, now)
    return price


def funding_rate(symbol: str) -> float:
    """เรต funding ปัจจุบัน (ต่อรอบ 8 ชม.) — บวก = ฝั่ง long จ่ายฝั่ง short"""
    hit = _funding_cache.get(symbol)
    if hit and time.time() - hit[1] < 60:
        return hit[0]
    try:
        fr = _ex.fetch_funding_rate(_resolve(symbol))
        rate = float(fr.get("fundingRate") or 0.0)
    except Exception:
        rate = 0.0
    _funding_cache[symbol] = (rate, time.time())
    return rate


def candles(symbol: str, timeframe: str = "15m", limit: int = 200) -> list[list]:
    """แท่งเทียน futures จริง [[ts, o, h, l, c, v], ...]"""
    return _ex.fetch_ohlcv(_resolve(symbol), timeframe, limit=limit)


# ───────────────────────────── STATE ─────────────────────────────

def _blank_state() -> dict:
    return {
        "wallet_balance": INITIAL_BALANCE,
        "initial_balance": INITIAL_BALANCE,
        "positions": {},          # symbol -> position dict
        "history": [],            # ไม้ที่ปิดแล้ว
        "events": [],             # เหตุการณ์ล่าสุด (liquidation/tp/sl/funding)
        "leverage": {},           # symbol -> leverage ที่ตั้งไว้
        "peak_equity": INITIAL_BALANCE,
        "max_drawdown_pct": 0.0,
        "total_fees": 0.0,
        "total_funding": 0.0,
        "liquidations": 0,
        "created_at": _now_iso(),
        "last_funding_slot": None,
    }


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def load_state() -> dict:
    with _lock:
        if os.path.exists(STATE_FILE):
            try:
                with open(STATE_FILE, encoding="utf-8") as f:
                    st = json.load(f)
                for k, v in _blank_state().items():
                    st.setdefault(k, v)
                return st
            except (json.JSONDecodeError, OSError):
                pass
        st = _blank_state()
        save_state(st)
        return st


def save_state(st: dict) -> None:
    with _lock:
        tmp = STATE_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(st, f, ensure_ascii=False, indent=2)
        os.replace(tmp, STATE_FILE)


def _log(line: str) -> None:
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"[{_now_iso()}] {line}\n")
    except OSError:
        pass


def _event(st: dict, kind: str, symbol: str, message: str, **extra) -> dict:
    ev = {"ts": _now_iso(), "kind": kind, "symbol": symbol, "message": message, **extra}
    st["events"].insert(0, ev)
    del st["events"][60:]
    _log(f"{kind.upper()} {symbol} — {message}")
    return ev


def reset(balance: float | None = None) -> dict:
    """ล้างพอร์ตเริ่มใหม่ — เก็บ log ไว้ (ประวัติการฝึกไม่ควรหาย)"""
    st = _blank_state()
    if balance and balance > 0:
        st["wallet_balance"] = st["initial_balance"] = st["peak_equity"] = float(balance)
    _log(f"RESET wallet={st['wallet_balance']:.2f}")
    save_state(st)
    return st


# ───────────────────────── MARGIN MATH ─────────────────────────

def mmr_for(notional: float) -> tuple[float, float]:
    """คืน (maintenance margin rate, maintenance amount) ตาม tier"""
    for cap, rate, amount in MMR_TIERS:
        if notional <= cap:
            return rate, amount
    return MMR_TIERS[-1][1], MMR_TIERS[-1][2]


def liquidation_price(side: str, entry: float, qty: float, margin: float) -> float:
    """
    ราคาที่ margin เหลือไม่พอ maintenance -> ถูกบังคับปิด
    ที่มา: margin + uPnL = maintenance_margin
      long : margin + (P-entry)*qty = mmr*P*qty - ma
             -> P = (entry*qty - margin - ma) / (qty*(1-mmr))
      short: margin + (entry-P)*qty = mmr*P*qty - ma
             -> P = (entry*qty + margin + ma) / (qty*(1+mmr))
    ตรวจสอบ: mmr=0, lev=10 -> long เจ๊งที่ -10%, short ที่ +10% ✓
    """
    notional = entry * qty
    mmr, ma = mmr_for(notional)
    if side == "long":
        p = (entry * qty - margin - ma) / (qty * (1 - mmr))
        return max(p, 0.0)
    p = (entry * qty + margin + ma) / (qty * (1 + mmr))
    return p


def unrealized(side: str, entry: float, qty: float, mark: float) -> float:
    return (mark - entry) * qty if side == "long" else (entry - mark) * qty


def _position_view(symbol: str, pos: dict, mark: float) -> dict:
    """ทำ snapshot ของไม้ที่มีเลขครบสำหรับหน้าจอ"""
    upnl = unrealized(pos["side"], pos["entry_price"], pos["qty"], mark)
    notional = mark * pos["qty"]
    margin = pos["margin"]
    mmr, ma = mmr_for(pos["entry_price"] * pos["qty"])
    maint = notional * mmr - ma
    liq = pos.get("liq_price") or liquidation_price(
        pos["side"], pos["entry_price"], pos["qty"], margin)
    equity_pos = margin + upnl
    dist = (liq - mark) / mark * 100 if mark else 0.0
    return {
        **pos,
        "symbol": symbol,
        "mark_price": mark,
        "notional": notional,
        "unrealized_pnl": upnl,
        "roe_pct": (upnl / margin * 100) if margin else 0.0,
        "liq_price": liq,
        "liq_distance_pct": abs(dist),
        "maint_margin": max(maint, 0.0),
        "margin_ratio_pct": (max(maint, 0.0) / equity_pos * 100) if equity_pos > 0 else 100.0,
        "break_even": pos["entry_price"] * (1 + (2 * TAKER_FEE if pos["side"] == "long" else -2 * TAKER_FEE)),
    }


# ───────────────────────── ACCOUNT VIEW ─────────────────────────

def account(refresh_prices: bool = True) -> dict:
    """สรุปบัญชี + ไม้ที่เปิดอยู่ทั้งหมด (ตีราคาตลาดสด)"""
    st = load_state()
    positions, upnl_total, margin_used, maint_total = [], 0.0, 0.0, 0.0
    for symbol, pos in list(st["positions"].items()):
        try:
            mk = mark_price(symbol, force=False) if refresh_prices else pos["entry_price"]
        except Exception:
            mk = pos["entry_price"]
        view = _position_view(symbol, pos, mk)
        positions.append(view)
        upnl_total += view["unrealized_pnl"]
        margin_used += pos["margin"]
        maint_total += view["maint_margin"]

    wallet = st["wallet_balance"]
    equity = wallet + upnl_total
    st = _track_drawdown(st, equity)

    return {
        "wallet_balance": wallet,
        "initial_balance": st["initial_balance"],
        "equity": equity,
        "unrealized_pnl": upnl_total,
        "margin_used": margin_used,
        "available_margin": max(wallet - margin_used, 0.0),
        "maint_margin": maint_total,
        "margin_ratio_pct": (maint_total / equity * 100) if equity > 0 else 0.0,
        "total_pnl": equity - st["initial_balance"],
        "total_pnl_pct": (equity - st["initial_balance"]) / st["initial_balance"] * 100,
        "total_fees": st["total_fees"],
        "total_funding": st["total_funding"],
        "liquidations": st["liquidations"],
        "max_drawdown_pct": st["max_drawdown_pct"],
        "positions": positions,
        "events": st["events"][:12],
        "leverage": st["leverage"],
        "symbols": SYMBOLS,
        "fees": {"taker": TAKER_FEE, "maker": MAKER_FEE},
        "updated_at": _now_iso(),
    }


def _track_drawdown(st: dict, equity: float) -> dict:
    changed = False
    if equity > st.get("peak_equity", 0):
        st["peak_equity"] = equity
        changed = True
    peak = st.get("peak_equity") or st["initial_balance"]
    dd = (peak - equity) / peak * 100 if peak > 0 else 0.0
    if dd > st.get("max_drawdown_pct", 0):
        st["max_drawdown_pct"] = dd
        changed = True
    if changed:
        save_state(st)
    return st


def set_leverage(symbol: str, leverage: int) -> dict:
    lev = int(leverage)
    cfg = next((s for s in SYMBOLS if s["symbol"] == symbol), None)
    cap = cfg["max_lev"] if cfg else MAX_LEVERAGE
    if not 1 <= lev <= cap:
        raise ValueError(f"leverage ต้องอยู่ระหว่าง 1–{cap}x สำหรับ {symbol}")
    st = load_state()
    if symbol in st["positions"]:
        raise ValueError("เปลี่ยน leverage ไม่ได้ตอนถือไม้อยู่ — ปิดไม้ก่อน")
    st["leverage"][symbol] = lev
    save_state(st)
    return {"symbol": symbol, "leverage": lev}


# ───────────────────────── OPEN / CLOSE ─────────────────────────

def open_position(symbol: str, side: str, margin: float | None = None,
                  qty: float | None = None, leverage: int | None = None,
                  tp: float | None = None, sl: float | None = None,
                  reason: str = "") -> dict:
    """
    เปิด (หรือเติม) ไม้ด้วย market order
      margin  = เงินที่ยอมวางเป็นหลักประกัน (USDT)  ← วิธีที่แนะนำสำหรับการฝึก
      qty     = จำนวนเหรียญ (ถ้าระบุ จะ override margin)
    """
    side = side.lower()
    if side not in ("long", "short"):
        raise ValueError("side ต้องเป็น long หรือ short")
    if not any(s["symbol"] == symbol for s in SYMBOLS):
        raise ValueError(f"ไม่รู้จัก {symbol}")

    st = load_state()
    lev = int(leverage or st["leverage"].get(symbol, 10))
    cfg = next(s for s in SYMBOLS if s["symbol"] == symbol)
    if not 1 <= lev <= cfg["max_lev"]:
        raise ValueError(f"leverage สูงสุดของ {symbol} คือ {cfg['max_lev']}x")

    price = mark_price(symbol, force=True)
    if qty:
        qty = float(qty)
        notional = qty * price
        margin_req = notional / lev
    else:
        if not margin or margin <= 0:
            raise ValueError("ต้องระบุ margin (USDT) หรือ qty")
        margin_req = float(margin)
        notional = margin_req * lev
        qty = notional / price

    if notional < MIN_NOTIONAL:
        raise ValueError(f"ขนาดไม้ต่ำกว่าขั้นต่ำ {MIN_NOTIONAL} USDT (ตอนนี้ {notional:.2f})")

    fee = notional * TAKER_FEE
    margin_used = sum(p["margin"] for p in st["positions"].values())
    available = st["wallet_balance"] - margin_used
    if margin_req + fee > available:
        raise ValueError(
            f"margin ไม่พอ: ต้องใช้ {margin_req + fee:.2f} แต่เหลือ {available:.2f} USDT")

    existing = st["positions"].get(symbol)
    if existing and existing["side"] != side:
        raise ValueError(
            f"ถือ {existing['side'].upper()} อยู่ — โหมด one-way ต้องปิดไม้เดิมก่อนกลับข้าง")

    # ตรวจ TP/SL ให้อยู่ฝั่งที่ถูกต้อง (กันตั้งผิดข้างแล้วโดนยิงทันที)
    tp = float(tp) if tp else None
    sl = float(sl) if sl else None
    if side == "long":
        if tp and tp <= price:
            raise ValueError("ไม้ long: เป้ากำไรต้องสูงกว่าราคาเข้า")
        if sl and sl >= price:
            raise ValueError("ไม้ long: stop loss ต้องต่ำกว่าราคาเข้า")
    else:
        if tp and tp >= price:
            raise ValueError("ไม้ short: เป้ากำไรต้องต่ำกว่าราคาเข้า")
        if sl and sl <= price:
            raise ValueError("ไม้ short: stop loss ต้องสูงกว่าราคาเข้า")

    st["wallet_balance"] -= fee
    st["total_fees"] += fee

    if existing:  # เติมไม้ทางเดิม -> ถัวเฉลี่ยราคาเข้า
        new_qty = existing["qty"] + qty
        existing["entry_price"] = (
            existing["entry_price"] * existing["qty"] + price * qty) / new_qty
        existing["qty"] = new_qty
        existing["margin"] += margin_req
        existing["fees_paid"] += fee
        existing["adds"] = existing.get("adds", 0) + 1
        if tp:
            existing["tp"] = tp
        if sl:
            existing["sl"] = sl
        existing["leverage"] = lev
        existing["liq_price"] = liquidation_price(
            side, existing["entry_price"], existing["qty"], existing["margin"])
        pos = existing
        _event(st, "add", symbol,
               f"เติม {side.upper()} {qty:.6f} @ {price:,.2f} — เฉลี่ยเข้า {pos['entry_price']:,.2f}")
    else:
        pos = {
            "side": side,
            "qty": qty,
            "entry_price": price,
            "leverage": lev,
            "margin": margin_req,
            "tp": tp,
            "sl": sl,
            "fees_paid": fee,
            "funding_paid": 0.0,
            "realized_partial": 0.0,
            "opened_at": _now_iso(),
            "reason": reason,
            "adds": 0,
        }
        pos["liq_price"] = liquidation_price(side, price, qty, margin_req)
        st["positions"][symbol] = pos
        _event(st, "open", symbol,
               f"เปิด {side.upper()} {qty:.6f} @ {price:,.2f} | {lev}x | margin {margin_req:.2f} "
               f"| liq {pos['liq_price']:,.2f}")

    save_state(st)
    return _position_view(symbol, pos, price)


def close_position(symbol: str, portion: float = 1.0, note: str = "",
                   trigger: str = "manual") -> dict:
    """ปิดไม้ (portion 0–1 = ปิดบางส่วนได้)"""
    st = load_state()
    pos = st["positions"].get(symbol)
    if not pos:
        raise ValueError(f"ไม่มีไม้ {symbol} ที่เปิดอยู่")
    portion = max(min(float(portion), 1.0), 0.0001)

    price = mark_price(symbol, force=True)
    close_qty = pos["qty"] * portion
    close_margin = pos["margin"] * portion
    gross = unrealized(pos["side"], pos["entry_price"], close_qty, price)
    fee = price * close_qty * TAKER_FEE
    net = gross - fee

    st["wallet_balance"] += net
    st["total_fees"] += fee

    full = portion >= 0.9999
    record = {
        "symbol": symbol,
        "side": pos["side"],
        "qty": close_qty,
        "entry_price": pos["entry_price"],
        "exit_price": price,
        "leverage": pos["leverage"],
        "margin": close_margin,
        "gross_pnl": gross,
        "fees": fee + pos["fees_paid"] * portion,
        "funding": pos["funding_paid"] * portion,
        "net_pnl": net,
        "roe_pct": (net / close_margin * 100) if close_margin else 0.0,
        "opened_at": pos["opened_at"],
        "closed_at": _now_iso(),
        "trigger": trigger,
        "reason": pos.get("reason", ""),
        "note": note,
        "partial": not full,
    }
    st["history"].insert(0, record)
    del st["history"][500:]

    label = {"tp": "TP", "sl": "SL", "liquidation": "LIQUIDATED", "manual": "ปิดมือ"}.get(trigger, trigger)
    _event(st, "close", symbol,
           f"{label} {pos['side'].upper()} {close_qty:.6f} @ {price:,.2f} "
           f"| PnL {net:+.2f} USDT ({record['roe_pct']:+.1f}% ROE)",
           pnl=net)

    if full:
        st["positions"].pop(symbol, None)
    else:
        pos["qty"] -= close_qty
        pos["margin"] -= close_margin
        pos["realized_partial"] += net
        pos["liq_price"] = liquidation_price(
            pos["side"], pos["entry_price"], pos["qty"], pos["margin"])

    save_state(st)
    return record


def _liquidate(st: dict, symbol: str, pos: dict, mark: float) -> dict:
    """บังคับปิด: margin ก้อนนั้นหายทั้งก้อน (ไม่คืน) — บทเรียนราคาแพงที่สุดของ futures"""
    loss = -pos["margin"]
    record = {
        "symbol": symbol, "side": pos["side"], "qty": pos["qty"],
        "entry_price": pos["entry_price"], "exit_price": pos.get("liq_price", mark),
        "leverage": pos["leverage"], "margin": pos["margin"],
        "gross_pnl": loss, "fees": pos["fees_paid"], "funding": pos["funding_paid"],
        "net_pnl": loss, "roe_pct": -100.0,
        "opened_at": pos["opened_at"], "closed_at": _now_iso(),
        "trigger": "liquidation", "reason": pos.get("reason", ""),
        "note": "ถูกบังคับปิด — margin หมด", "partial": False,
    }
    st["wallet_balance"] -= pos["margin"]
    st["liquidations"] += 1
    st["history"].insert(0, record)
    st["positions"].pop(symbol, None)
    _event(st, "liquidation", symbol,
           f"⚠ ถูกล้างพอร์ตไม้นี้ที่ {record['exit_price']:,.2f} "
           f"({pos['leverage']}x) — เสีย margin {pos['margin']:.2f} USDT",
           pnl=loss)
    return record


# ───────────────────────── FUNDING ─────────────────────────

def _funding_slot(now: datetime | None = None) -> str:
    """ช่องเวลา funding ปัจจุบัน เช่น 2026-07-30T08 (รอบ 00/08/16 UTC)"""
    now = now or datetime.now(timezone.utc)
    slot_h = (now.hour // FUNDING_INTERVAL_H) * FUNDING_INTERVAL_H
    return f"{now:%Y-%m-%d}T{slot_h:02d}"


def _apply_funding(st: dict) -> list[dict]:
    """เก็บ/จ่าย funding ครั้งละรอบ; ข้ามถ้ารอบนี้จ่ายแล้ว"""
    slot = _funding_slot()
    if st.get("last_funding_slot") == slot or not st["positions"]:
        st["last_funding_slot"] = st.get("last_funding_slot") or slot
        return []
    events = []
    for symbol, pos in list(st["positions"].items()):
        try:
            rate = funding_rate(symbol)
            mk = mark_price(symbol)
        except Exception:
            continue
        notional = mk * pos["qty"]
        # long จ่ายเมื่อ rate เป็นบวก, short ได้รับ
        payment = notional * rate * (1 if pos["side"] == "long" else -1)
        st["wallet_balance"] -= payment
        st["total_funding"] += payment
        pos["funding_paid"] += payment
        events.append(_event(
            st, "funding", symbol,
            f"funding {rate * 100:+.4f}% → {'จ่าย' if payment > 0 else 'ได้รับ'} "
            f"{abs(payment):.4f} USDT", amount=-payment))
    st["last_funding_slot"] = slot
    return events


# ───────────────────────── TICK ENGINE ─────────────────────────

def tick() -> dict:
    """
    หัวใจของ engine — เรียกทุกครั้งที่ต้องการให้เวลาเดิน:
      1) อัปเดต mark price
      2) เช็ค liquidation (ก่อนอื่นใด — ของจริงก็ตัดก่อน TP/SL)
      3) เช็ค SL แล้ว TP
      4) จ่าย/รับ funding ตามรอบ
    ปลอดภัยถ้าถูกเรียกถี่ ๆ (idempotent ต่อรอบ funding, ใช้ cache ราคา)
    """
    st = load_state()
    fired: list[dict] = []

    for symbol, pos in list(st["positions"].items()):
        try:
            mk = mark_price(symbol)
        except Exception as e:  # เน็ตล่ม — ข้ามรอบนี้ ไม่ตัดสินใจบนข้อมูลเก่า
            _log(f"WARN ดึงราคา {symbol} ไม่ได้: {e}")
            continue

        liq = pos.get("liq_price") or liquidation_price(
            pos["side"], pos["entry_price"], pos["qty"], pos["margin"])
        hit_liq = mk <= liq if pos["side"] == "long" else mk >= liq
        if hit_liq:
            fired.append(_liquidate(st, symbol, pos, mk))
            continue

        if pos.get("sl"):
            hit = mk <= pos["sl"] if pos["side"] == "long" else mk >= pos["sl"]
            if hit:
                save_state(st)
                fired.append(close_position(symbol, 1.0, "แตะ stop loss", "sl"))
                st = load_state()
                continue

        if pos.get("tp"):
            hit = mk >= pos["tp"] if pos["side"] == "long" else mk <= pos["tp"]
            if hit:
                save_state(st)
                fired.append(close_position(symbol, 1.0, "ถึงเป้ากำไร", "tp"))
                st = load_state()
                continue

    _apply_funding(st)
    save_state(st)
    return {"triggered": fired, "count": len(fired)}


# ───────────────────────── STATS ─────────────────────────

def stats() -> dict:
    """สถิติสำหรับ 'สังเกต' ตัวเอง — ตัวเลขที่บอกความจริงมากกว่ากำไรรวม"""
    st = load_state()
    h = [t for t in st["history"] if not t.get("partial")] or st["history"]
    if not h:
        return {"trades": 0, "message": "ยังไม่มีไม้ที่ปิดแล้ว"}

    wins = [t for t in h if t["net_pnl"] > 0]
    losses = [t for t in h if t["net_pnl"] <= 0]
    gross_win = sum(t["net_pnl"] for t in wins)
    gross_loss = abs(sum(t["net_pnl"] for t in losses))
    longs = [t for t in h if t["side"] == "long"]
    shorts = [t for t in h if t["side"] == "short"]

    def hold_hours(t):
        try:
            a = datetime.fromisoformat(t["opened_at"])
            b = datetime.fromisoformat(t["closed_at"])
            return (b - a).total_seconds() / 3600
        except Exception:
            return 0.0

    return {
        "trades": len(h),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate_pct": len(wins) / len(h) * 100,
        "avg_win": gross_win / len(wins) if wins else 0.0,
        "avg_loss": -gross_loss / len(losses) if losses else 0.0,
        "profit_factor": (gross_win / gross_loss) if gross_loss else float("inf"),
        "expectancy": sum(t["net_pnl"] for t in h) / len(h),
        "best": max((t["net_pnl"] for t in h), default=0.0),
        "worst": min((t["net_pnl"] for t in h), default=0.0),
        "avg_roe_pct": sum(t["roe_pct"] for t in h) / len(h),
        "avg_leverage": sum(t["leverage"] for t in h) / len(h),
        "avg_hold_hours": sum(hold_hours(t) for t in h) / len(h),
        "long_win_rate_pct": (len([t for t in longs if t["net_pnl"] > 0]) / len(longs) * 100) if longs else None,
        "short_win_rate_pct": (len([t for t in shorts if t["net_pnl"] > 0]) / len(shorts) * 100) if shorts else None,
        "by_trigger": {
            k: len([t for t in h if t.get("trigger") == k])
            for k in ("manual", "tp", "sl", "liquidation")
        },
        "liquidations": st["liquidations"],
        "total_fees": st["total_fees"],
        "total_funding": st["total_funding"],
        "max_drawdown_pct": st["max_drawdown_pct"],
    }


def history(limit: int = 50) -> list[dict]:
    return load_state()["history"][:limit]


# ───────────────────── ตัวช่วยก่อนกดเปิดไม้ ─────────────────────

def preview(symbol: str, side: str, margin: float, leverage: int,
            tp: float | None = None, sl: float | None = None) -> dict:
    """คำนวณให้ดูก่อนยิงจริง: ได้ของเท่าไร เจ๊งที่ราคาไหน เสี่ยงกี่บาท"""
    price = mark_price(symbol)
    notional = float(margin) * int(leverage)
    qty = notional / price
    fee_in = notional * TAKER_FEE
    fee_out = notional * TAKER_FEE
    liq = liquidation_price(side, price, qty, float(margin))
    out = {
        "mark_price": price,
        "qty": qty,
        "notional": notional,
        "margin": float(margin),
        "leverage": int(leverage),
        "fee_round_trip": fee_in + fee_out,
        "liq_price": liq,
        "liq_move_pct": abs(liq - price) / price * 100,
        "funding_rate_pct": funding_rate(symbol) * 100,
        "funding_per_cycle": notional * funding_rate(symbol) * (1 if side == "long" else -1),
    }
    if sl:
        out["risk_usdt"] = abs(unrealized(side, price, qty, float(sl))) + out["fee_round_trip"]
        out["risk_pct_of_margin"] = out["risk_usdt"] / float(margin) * 100
    if tp:
        out["reward_usdt"] = abs(unrealized(side, price, qty, float(tp))) - out["fee_round_trip"]
    if tp and sl and out.get("risk_usdt"):
        out["rr_ratio"] = out["reward_usdt"] / out["risk_usdt"]
    return out


# ───────────────────── background ticker ─────────────────────

_ticker_thread: threading.Thread | None = None
_ticker_stop = threading.Event()


def start_background_ticker(interval: int = 10) -> None:
    """
    ให้ TP/SL/liquidation ทำงานต่อแม้ปิดเบราว์เซอร์
    (ของจริง exchange ตัดให้ตลอดเวลา — ถ้า engine หลับ การฝึกจะเพี้ยน)
    """
    global _ticker_thread
    if _ticker_thread and _ticker_thread.is_alive():
        return

    def loop():
        _log(f"BACKGROUND ticker เริ่มทำงาน ทุก {interval}s")
        while not _ticker_stop.wait(interval):
            try:
                tick()
            except Exception as e:
                _log(f"ERROR ticker: {e}")

    _ticker_thread = threading.Thread(target=loop, daemon=True, name="futures-ticker")
    _ticker_thread.start()


def stop_background_ticker() -> None:
    _ticker_stop.set()


if __name__ == "__main__":
    # ทดสอบเร็ว ๆ: python futures.py
    acc = account()
    print(f"wallet {acc['wallet_balance']:.2f} | equity {acc['equity']:.2f} "
          f"| ไม้ที่เปิด {len(acc['positions'])}")
    for s in SYMBOLS:
        print(f"  {s['label']:<10} {mark_price(s['symbol']):>12,.2f} "
              f"| funding {funding_rate(s['symbol']) * 100:+.4f}%")
