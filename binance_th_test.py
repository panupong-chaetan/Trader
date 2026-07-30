"""
binance_th_test.py — สคริปต์สำรวจ ก่อนต่อเข้าระบบจริง
========================================================
เป้าหมาย: หาว่า symbol ของคู่ THB เขียนแบบไหนกันแน่ (BTCTHB? BTC_THB?)
เพราะ docs ไม่ได้ยกตัวอย่างคู่ THB ตรงๆ — เช็คก่อนเชื่อ ไม่เดา

รัน:  python binance_th_test.py
"""

import binance_th as th

print("=== 1) เช็คว่าต่อ API ได้ไหม ===")
try:
    t = th.server_time()
    print("เชื่อมต่อสำเร็จ:", t)
except Exception as e:
    print("ต่อไม่ได้:", e)
    print("(เช็คเน็ต/URL — ถ้าพังตรงนี้ ยังไปต่อไม่ได้)")
    raise SystemExit

print("\n=== 2) ดึงราคาทุกคู่ในตลาด หา symbol ที่มีคำว่า THB ===")
all_prices = th.ticker_price()  # ไม่ใส่ symbol = คืนทั้งตลาด
thb_pairs = [p for p in all_prices if "THB" in p.get("symbol", "")]
if thb_pairs:
    print(f"เจอ {len(thb_pairs)} คู่ที่มี THB:")
    for p in thb_pairs[:20]:
        print(f"  {p['symbol']:15} ราคา {p['price']}")
else:
    print("ไม่เจอคู่ THB เลย — โครงสร้าง symbol อาจเขียนคนละแบบ ลองดู field อื่นในตัวอย่างข้างล่าง")
    print("ตัวอย่าง 5 คู่แรกในตลาด (ดู pattern การตั้งชื่อ):")
    for p in all_prices[:5]:
        print(" ", p)

print("\n=== 3) เช็คว่า BTC/USDT เขียนแบบไหนบนนี้ (เทียบกับที่รู้จักแล้ว) ===")
usdt_pairs = [p for p in all_prices if p.get("symbol", "").endswith("USDT")][:5]
for p in usdt_pairs:
    print(f"  {p['symbol']:15} ราคา {p['price']}")

print("\n=== เสร็จแล้ว — เอา symbol ที่เจอ (เช่น 'BTCTHB') ไปใช้ต่อได้เลย ===")
