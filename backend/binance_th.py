"""
binance_th.py — ต่อ Binance TH API ตรงๆ (ไม่ผ่าน ccxt เพราะ ccxt ไม่รองรับ)
================================================================================
อ้างอิงจาก REST Open API v1.0.0 docs: https://www.binance.th/api-docs/en/
Base URL: https://api.binance.th

โครงสร้าง:
  - ฟังก์ชัน public (ไม่ต้อง auth): server_time, ticker_price, klines, ticker_24hr
  - ฟังก์ชัน signed (ต้องมี API key/secret): account_balance
  - place_order(): เขียนไว้ครบตาม docs แต่ "ล็อก" ไว้ด้วย LIVE_TRADING_ENABLED
    จะไม่ทำงานจนกว่าจะตั้งค่า True เอง (ตามเงื่อนไขที่ตกลงกันไว้: 20/20 ไม้ +
    วินัย >=90% + expectancy บวก ในสมุดเทรดก่อน ถึงจะเปิดให้ตัวเองใช้)

การตั้งค่า API key: ใช้ environment variable เท่านั้น ห้าม hardcode ในไฟล์นี้
    Windows (cmd):  set BINANCE_TH_API_KEY=xxxx
                    set BINANCE_TH_API_SECRET=yyyy
"""

import hashlib
import hmac
import json
import os
import time
import urllib.parse
import urllib.request

BASE_URL = "https://api.binance.th"

# ---------------- Symbol ที่ยืนยันแล้วจากการรันจริง (29 ก.ค. 2569) ----------------
# format: ต่อกันตรงๆ ไม่มีขีด/สแลช เหมือน Binance Global (เช่น BTCUSDT)
BTC_THB = "BTCTHB"
USDT_THB = "USDTTHB"
ETH_THB = "ETHTHB"
SOL_THB = "SOLTHB"

# ---------------- กุญแจนิรภัย: เทรดจริงถูกล็อกไว้ default ----------------
# เปลี่ยนเป็น True เองเท่านั้น หลังผ่านเกณฑ์: 20/20 ไม้ + วินัย >=90% + expectancy บวก
# (ดูสถิติได้จาก journal.py เมนู [4] หรือ dashboard)
LIVE_TRADING_ENABLED = False

API_KEY = os.environ.get("BINANCE_TH_API_KEY", "")
API_SECRET = os.environ.get("BINANCE_TH_API_SECRET", "")


# ---------------- HTTP helpers ----------------

def _get(path, params=None, signed=False):
    params = params or {}
    if signed:
        params["timestamp"] = int(time.time() * 1000)
        query = urllib.parse.urlencode(params)
        sig = hmac.new(API_SECRET.encode(), query.encode(), hashlib.sha256).hexdigest()
        query += f"&signature={sig}"
    else:
        query = urllib.parse.urlencode(params)

    url = f"{BASE_URL}{path}" + (f"?{query}" if query else "")
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    if signed:
        req.add_header("X-MBX-APIKEY", API_KEY)
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read().decode())


def _post(path, params, signed=True):
    params["timestamp"] = int(time.time() * 1000)
    query = urllib.parse.urlencode(params)
    sig = hmac.new(API_SECRET.encode(), query.encode(), hashlib.sha256).hexdigest()
    query += f"&signature={sig}"
    url = f"{BASE_URL}{path}"
    req = urllib.request.Request(url, data=query.encode(), method="POST",
                                  headers={"Accept": "application/json",
                                           "X-MBX-APIKEY": API_KEY,
                                           "Content-Type": "application/x-www-form-urlencoded"})
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read().decode())


# ---------------- Public endpoints (ไม่ต้อง auth) ----------------

def server_time():
    return _get("/api/v1/time")

def ticker_price(symbol=None):
    """symbol=None -> คืนราคาทุกคู่ในตลาด ใช้ตอนสำรวจว่าคู่ THB ชื่ออะไรกันแน่"""
    params = {"symbol": symbol} if symbol else {}
    return _get("/api/v1/ticker/price", params)

def klines(symbol, interval="1h", limit=100):
    return _get("/api/v1/klines", {"symbol": symbol, "interval": interval, "limit": limit})

def ticker_24hr(symbol):
    return _get("/api/v1/ticker/24hr", {"symbol": symbol})

def symbol_type(symbol=None):
    """คืนว่า symbol เป็น GLOBAL หรือ SITE"""
    params = {"symbol": symbol} if symbol else {}
    return _get("/api/v1/symbolType", params)


# ---------------- Signed endpoints (ต้องมี API key) ----------------

def account_balance():
    """เช็คยอดเงินจริง — read-only ปลอดภัย ใช้ได้เลยไม่ต้องรอด่านไหน"""
    if not API_KEY or not API_SECRET:
        raise RuntimeError("ยังไม่ได้ตั้ง BINANCE_TH_API_KEY / BINANCE_TH_API_SECRET")
    return _get("/api/v1/accountV2", {}, signed=True)


def place_order(symbol, side, order_type, quantity, price=None, time_in_force="GTC"):
    """ส่งคำสั่งซื้อขายจริง — ล็อกไว้จนกว่า LIVE_TRADING_ENABLED = True
    ห้ามแก้บรรทัดนี้เพื่อ "ลองดูก่อน" — เขียนไว้เตือนตัวเองในอนาคตตรงๆ"""
    if not LIVE_TRADING_ENABLED:
        raise RuntimeError(
            "LIVE_TRADING_ENABLED = False — ยังไม่อนุญาตให้เทรดจริง\n"
            "เช็คก่อนว่า: สมุดเทรดครบ 20/20 ไม้ + วินัย >=90% + expectancy บวก\n"
            "ผ่านครบแล้วค่อยเปลี่ยนค่านี้เป็น True เองที่บรรทัดบนของไฟล์"
        )
    if not API_KEY or not API_SECRET:
        raise RuntimeError("ยังไม่ได้ตั้ง BINANCE_TH_API_KEY / BINANCE_TH_API_SECRET")

    params = {"symbol": symbol, "side": side, "type": order_type, "quantity": quantity}
    if order_type in ("LIMIT", "STOP_LOSS_LIMIT", "TAKE_PROFIT_LIMIT"):
        params["price"] = price
        params["timeInForce"] = time_in_force
    return _post("/api/v1/order", params)


# ---------------- Adapter: ให้หน้าตาเหมือน ccxt (fetch_ohlcv/fetch_ticker) ----------------
# เพื่อให้ copilot.py / backend/main.py เรียกใช้ผ่าน ex_for(symbol).xxx() ได้แบบเดียวกับ
# ตอนใช้ ccxt.binance() ทุกประการ ไม่ต้องแก้โค้ดฝั่งเรียกใช้เลย

class BinanceTHExchange:
    """หน้ากากให้ binance_th.py ดูเหมือน ccxt exchange object"""

    def fetch_ohlcv(self, symbol, timeframe="1h", limit=100):
        raw = klines(symbol, interval=timeframe, limit=limit)
        # raw: [openTime, open, high, low, close, volume, ...] ตาม docs
        return [[int(row[0]), float(row[1]), float(row[2]),
                 float(row[3]), float(row[4]), float(row[5])] for row in raw]

    def fetch_ticker(self, symbol):
        p = ticker_price(symbol)
        return {"last": float(p["price"])}

    def fetch_24h_volume(self, symbol):
        """ปริมาณเทรด 24 ชม. เป็นสกุลอ้างอิง (เช่น THB) — ใช้เป็นตัวกรองสภาพคล่องก่อน
        auto-trade คู่เหรียญไหน ป้องกันคู่ที่นิ่งเพราะไม่มีคนเทรดจริงมากกว่าเพราะไม่มีสัญญาณ

        หมายเหตุ: ยังไม่เคยยิงจริงกับ endpoint นี้จาก sandbox (ไม่มี network ออกไป
        Binance TH ได้) เดาชื่อ field ตามรูปแบบมาตรฐานของ Binance-style API — ถ้าไม่มี
        field ที่คาดไว้จะคืน None แทนที่จะเดามั่ว เพื่อไม่ให้ตัวกรองพังแบบเงียบๆ"""
        try:
            data = ticker_24hr(symbol)
            for key in ("quoteVolume", "quote_volume", "volume24h", "amount"):
                if key in data:
                    return float(data[key])
        except Exception:
            pass
        return None


if __name__ == "__main__":
    print("server_time:", server_time())
