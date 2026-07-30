"""
Backtest ตัวแรก: กลยุทธ์ MA Crossover (Golden Cross)
====================================================
กติกา:
  - MA20 ตัดขึ้นเหนือ MA50  -> ซื้อ (เข้า position เต็มพอร์ต)
  - MA20 ตัดลงใต้ MA50      -> ขายทั้งหมด (ถือเงินสด)
  - คิดค่าธรรมเนียม 0.1% ทุกครั้งที่ซื้อหรือขาย
  - ไม่มี short selling (เล่นฝั่งซื้ออย่างเดียว)

หลักการสำคัญของ backtest ที่ถูกต้อง:
  ตัดสินใจจากข้อมูล "เมื่อวาน" แล้วเข้าเทรดที่ราคา "วันนี้"
  ถ้าใช้ราคาวันเดียวกับที่ตัดสินใจ = lookahead bias (โกงอนาคต)
"""

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

# ----------------------------------------------------------
# ส่วนที่ 1: สร้างข้อมูลจำลอง (แทนข้อมูลจริงชั่วคราว)
# ----------------------------------------------------------
# ราคาจริงมี "ช่วงอารมณ์" (regime): ขาขึ้น, sideways, ขาลง
# เราจำลอง 4 ปี (ประมาณ 1000 แท่งรายวัน) ให้มีครบทุกช่วง
# เพื่อดูว่ากลยุทธ์ทำตัวยังไงในแต่ละสภาพตลาด

def generate_price_data(seed=42):
    rng = np.random.default_rng(seed)
    # (จำนวนวัน, drift ต่อวัน, ความผันผวนต่อวัน)
    regimes = [
        (250, 0.0012, 0.015),   # ปี 1: ขาขึ้นชัดเจน
        (250, 0.0000, 0.010),   # ปี 2: sideways เงียบๆ
        (250, -0.0010, 0.025),  # ปี 3: ขาลง + ผันผวนสูง
        (250, 0.0008, 0.014),   # ปี 4: ฟื้นตัว
    ]
    returns = np.concatenate([
        rng.normal(drift, vol, days) for days, drift, vol in regimes
    ])
    price = 100 * np.exp(np.cumsum(returns))  # เริ่มที่ 100
    dates = pd.date_range("2022-01-01", periods=len(price), freq="D")
    return pd.DataFrame({"close": price}, index=dates)

# ----------------------------------------------------------
# ส่วนที่ 2: Backtest Engine
# ----------------------------------------------------------

def run_backtest(df, fast=20, slow=50, fee_rate=0.001, initial_cash=100_000):
    df = df.copy()
    df["ma_fast"] = df["close"].rolling(fast).mean()
    df["ma_slow"] = df["close"].rolling(slow).mean()

    # สัญญาณ: 1 = ควรถือ, 0 = ควรถือเงินสด
    df["signal"] = (df["ma_fast"] > df["ma_slow"]).astype(int)

    # *** จุดสำคัญที่สุดของไฟล์นี้ ***
    # shift(1) = ใช้สัญญาณของ "เมื่อวาน" มาเทรด "วันนี้"
    # ถ้าลบบรรทัดนี้ออก ผลจะสวยขึ้นทันที... แบบปลอมๆ (lookahead bias)
    df["position"] = df["signal"].shift(1).fillna(0)

    cash = initial_cash
    units = 0.0            # จำนวนหน่วยสินทรัพย์ที่ถือ
    total_fees = 0.0
    trades = []            # เก็บประวัติการเทรดไว้วิเคราะห์
    entry_price = None
    equity_curve = []

    for date, row in df.iterrows():
        price = row["close"]
        want_position = row["position"] == 1
        holding = units > 0

        if want_position and not holding:
            # ซื้อ: ใช้เงินสดทั้งหมด หักค่าธรรมเนียม
            fee = cash * fee_rate
            units = (cash - fee) / price
            total_fees += fee
            cash = 0.0
            entry_price = price
        elif not want_position and holding:
            # ขายทั้งหมด
            gross = units * price
            fee = gross * fee_rate
            cash = gross - fee
            total_fees += fee
            trades.append({
                "entry": entry_price,
                "exit": price,
                "pnl_pct": (price / entry_price - 1) * 100,
            })
            units = 0.0

        equity_curve.append(cash + units * price)

    df["equity"] = equity_curve

    # ถ้าจบข้อมูลแล้วยังถืออยู่ ปิดสถานะเพื่อคิดสถิติ
    if units > 0:
        trades.append({
            "entry": entry_price,
            "exit": df["close"].iloc[-1],
            "pnl_pct": (df["close"].iloc[-1] / entry_price - 1) * 100,
        })

    return df, trades, total_fees

# ----------------------------------------------------------
# ส่วนที่ 3: Metrics
# ----------------------------------------------------------

def max_drawdown(equity):
    """พอร์ตเคยร่วงจากจุดสูงสุดมากที่สุดกี่ % (ตัววัดความเจ็บปวด)"""
    peak = equity.cummax()
    dd = (equity - peak) / peak
    return dd.min() * 100, dd

def report(name, equity, trades, total_fees, initial_cash):
    final = equity.iloc[-1]
    ret = (final / initial_cash - 1) * 100
    mdd, _ = max_drawdown(equity)
    print(f"\n=== {name} ===")
    print(f"เงินเริ่มต้น : {initial_cash:>12,.0f}")
    print(f"เงินสุดท้าย  : {final:>12,.0f}")
    print(f"ผลตอบแทนรวม : {ret:>11.1f}%")
    print(f"Max Drawdown: {mdd:>11.1f}%")
    if trades is not None:
        wins = [t for t in trades if t["pnl_pct"] > 0]
        print(f"จำนวนเทรด   : {len(trades):>12}")
        if trades:
            print(f"Win Rate    : {len(wins)/len(trades)*100:>11.1f}%")
            print(f"กำไรเฉลี่ย/ไม้ที่ชนะ : {np.mean([t['pnl_pct'] for t in wins]):>6.1f}%" if wins else "")
            losses = [t for t in trades if t["pnl_pct"] <= 0]
            if losses:
                print(f"ขาดทุนเฉลี่ย/ไม้ที่แพ้: {np.mean([t['pnl_pct'] for t in losses]):>6.1f}%")
        print(f"ค่าธรรมเนียมรวม: {total_fees:>10,.0f}")


# ----------------------------------------------------------
# ส่วนที่ 4: รันจริง
# ----------------------------------------------------------

def load_real_data(ticker="BTC-USD", start="2018-01-01", end=None):
    """
    ดึงราคาปิดรายวันจริงจาก Yahoo Finance
    ครั้งแรกจะโหลดจากเน็ตแล้ว cache เป็นไฟล์ csv
    ครั้งถัดไปอ่านจากไฟล์เลย (เร็ว + ผลคงที่ ไม่เปลี่ยนทุกครั้งที่รัน)
    """
    import os
    import yfinance as yf

    cache_file = f"data_{ticker}.csv"
    if os.path.exists(cache_file):
        df = pd.read_csv(cache_file, index_col=0, parse_dates=True)
        print(f"อ่านข้อมูลจาก cache: {cache_file} ({len(df)} วัน)")
        return df

    raw = yf.download(ticker, start=start, end=end, auto_adjust=True)
    if raw.empty:
        raise RuntimeError(f"โหลดข้อมูล {ticker} ไม่สำเร็จ — เช็คเน็ต/ชื่อ ticker")

    # yfinance บางเวอร์ชันคืน column เป็น 2 ชั้น (MultiIndex) — แบนให้เหลือชั้นเดียว
    if isinstance(raw.columns, pd.MultiIndex):
        raw.columns = raw.columns.get_level_values(0)

    df = raw[["Close"]].rename(columns={"Close": "close"}).dropna()
    df.to_csv(cache_file)
    print(f"โหลด {ticker} สำเร็จ: {len(df)} วัน "
          f"({df.index[0].date()} ถึง {df.index[-1].date()}) -> cache แล้ว")
    return df

INITIAL = 100_000
# data = generate_price_data()          # ข้อมูลจำลอง (เก็บไว้สลับกลับมาเทียบได้)
data = load_real_data("BTC-USD")        # ข้อมูลจริง: Bitcoin ตั้งแต่ 2018

# 1) กลยุทธ์ MA Crossover (มีค่าธรรมเนียม)
df, trades, fees = run_backtest(data, fee_rate=0.001, initial_cash=INITIAL)
report("MA Crossover (คิดค่าธรรมเนียม 0.1%)", df["equity"], trades, fees, INITIAL)

# 2) กลยุทธ์เดียวกัน แต่ไม่คิดค่าธรรมเนียม (โลกในฝันของมือใหม่)
df_nofee, trades_nf, _ = run_backtest(data, fee_rate=0.0, initial_cash=INITIAL)
report("MA Crossover (โลกในฝัน: ฟรีค่าธรรมเนียม)", df_nofee["equity"], trades_nf, 0, INITIAL)

# 3) Buy & Hold — คู่แข่งที่แท้จริงของทุกกลยุทธ์
bh_units = (INITIAL * (1 - 0.001)) / data["close"].iloc[0]
bh_equity = bh_units * data["close"]
report("Buy & Hold (ซื้อวันแรก ถือยาว)", bh_equity, None, INITIAL * 0.001, INITIAL)

# ----------------------------------------------------------
# ส่วนที่ 5: วาดกราฟ
# ----------------------------------------------------------
fig, axes = plt.subplots(3, 1, figsize=(12, 12), sharex=True)

ax = axes[0]
ax.plot(data.index, data["close"], color="#888", lw=1, label="Price")
ax.plot(df.index, df["ma_fast"], color="#2196F3", lw=1, label="MA20")
ax.plot(df.index, df["ma_slow"], color="#FF9800", lw=1, label="MA50")
ax.set_title("Price + Moving Averages")
ax.legend(); ax.grid(alpha=0.3)

ax = axes[1]
ax.plot(df.index, df["equity"], color="#4CAF50", lw=1.5, label="MA Crossover (with fees)")
ax.plot(bh_equity.index, bh_equity, color="#9C27B0", lw=1.5, label="Buy & Hold")
ax.axhline(INITIAL, color="#f44336", ls="--", lw=0.8, label="Break-even")
ax.set_title("Equity Curve: Strategy vs Buy & Hold")
ax.legend(); ax.grid(alpha=0.3)

ax = axes[2]
_, dd_strat = max_drawdown(df["equity"])
_, dd_bh = max_drawdown(bh_equity)
ax.fill_between(df.index, dd_strat * 100, 0, color="#4CAF50", alpha=0.4, label="Strategy DD")
ax.fill_between(bh_equity.index, dd_bh * 100, 0, color="#9C27B0", alpha=0.3, label="Buy & Hold DD")
ax.set_title("Drawdown (%) — deeper = more painful")
ax.legend(); ax.grid(alpha=0.3)

plt.tight_layout()
plt.savefig("backtest_result.png", dpi=100)
print("\nบันทึกกราฟที่ backtest_result.png แล้ว")

# ----------------------------------------------------------
# การทดลอง: Parameter Sweep — หาคู่ MA ที่ "ดีที่สุด"
# ----------------------------------------------------------
print("\n fast/slow |  ผลตอบแทน |  MaxDD  | เทรด")
print("-" * 45)

pairs = [(5, 15), (10, 30), (20, 50), (30, 80), (50, 100), (50, 200)]
for fast, slow in pairs:
    d, t, _ = run_backtest(data, fast=fast, slow=slow,
                           fee_rate=0.001, initial_cash=INITIAL)
    ret = (d["equity"].iloc[-1] / INITIAL - 1) * 100
    mdd, _ = max_drawdown(d["equity"])
    print(f"  {fast:>3}/{slow:<4} | {ret:>8.1f}% | {mdd:>6.1f}% | {len(t):>4}")

# ----------------------------------------------------------
# บทที่ 2: Out-of-Sample Test — จับโกหกแชมป์จาก parameter sweep
# ----------------------------------------------------------
# วิธีการ:
#   1. แบ่งข้อมูล 4 ปี เป็นสองก้อน: 2 ปีแรก (in-sample) / 2 ปีหลัง (out-of-sample)
#   2. รัน sweep กับก้อนแรกเท่านั้น -> ได้ "แชมป์"
#   3. เอาแชมป์ไปสอบกับก้อนหลังที่มันไม่เคยเห็น
#   4. เทียบผล: สอบผ่านหรือสอบตก?

split_point = len(data) // 2           # แบ่งครึ่ง
train = data.iloc[:split_point]        # in-sample: 2022-2023
test = data.iloc[split_point:]         # out-of-sample: 2024 เป็นต้นไป

pairs = [(5, 15), (10, 30), (20, 50), (30, 80), (50, 100), (50, 200)]

def evaluate(df_data, fast, slow):
    d, t, _ = run_backtest(df_data, fast=fast, slow=slow,
                           fee_rate=0.001, initial_cash=INITIAL)
    ret = (d["equity"].iloc[-1] / INITIAL - 1) * 100
    mdd, _ = max_drawdown(d["equity"])
    return ret, mdd, len(t)

print(f"\nข้อมูลทั้งหมด {len(data)} วัน -> train {len(train)} วัน / test {len(test)} วัน")
print("\n[รอบคัดเลือก] sweep เฉพาะข้อมูลก้อนแรก (in-sample)")
print(" fast/slow |  return  |  MaxDD")
print("-" * 35)

results = []
for fast, slow in pairs:
    ret, mdd, n = evaluate(train, fast, slow)
    results.append((ret, fast, slow))
    print(f"  {fast:>3}/{slow:<4} | {ret:>7.1f}% | {mdd:>6.1f}%")

# หาแชมป์จากรอบคัดเลือก
best_ret, best_fast, best_slow = max(results)
print(f"\nแชมป์ in-sample คือ {best_fast}/{best_slow} (ผลตอบแทน {best_ret:.1f}%)")

# สอบจริงกับข้อมูลที่ไม่เคยเห็น
oos_ret, oos_mdd, oos_n = evaluate(test, best_fast, best_slow)
print(f"\n[สอบจริง] เอา {best_fast}/{best_slow} ไปเทรดข้อมูลก้อนหลัง (out-of-sample)")
print(f"ผลตอบแทน : {oos_ret:>7.1f}%")
print(f"MaxDD    : {oos_mdd:>7.1f}%")
print(f"จำนวนเทรด: {oos_n}")

# แถม: แล้วคู่อื่นๆ ทำได้แค่ไหนในก้อนหลัง? (ดูว่าแชมป์ยังเป็นแชมป์ไหม)
print("\n[เฉลยหลังสอบ] ทุกคู่เจอข้อมูลก้อนหลัง:")
print(" fast/slow |  return  |  MaxDD")
print("-" * 35)
for fast, slow in pairs:
    ret, mdd, n = evaluate(test, fast, slow)
    marker = "  <-- แชมป์จากรอบแรก" if (fast, slow) == (best_fast, best_slow) else ""
    print(f"  {fast:>3}/{slow:<4} | {ret:>7.1f}% | {mdd:>6.1f}%{marker}")

# ----------------------------------------------------------
# บทที่ 3: Stop Loss — circuit breaker ของพอร์ต
# ----------------------------------------------------------
# เพิ่มกติกา: ถ้าราคาร่วงจากราคาซื้อเกิน stop_pct -> ขายทันที
# แล้วทดสอบหลายระดับ stop เทียบกับ "ไม่มี stop" ว่าอะไรเปลี่ยนไป

def run_backtest_with_stop(df, fast=20, slow=50, stop_pct=None,
                           fee_rate=0.001, initial_cash=100_000):
    df = df.copy()
    df["ma_fast"] = df["close"].rolling(fast).mean()
    df["ma_slow"] = df["close"].rolling(slow).mean()
    df["signal"] = (df["ma_fast"] > df["ma_slow"]).astype(int)
    df["position"] = df["signal"].shift(1).fillna(0)

    cash, units, total_fees = initial_cash, 0.0, 0.0
    trades, equity_curve = [], []
    entry_price = None
    stopped_out = False   # โดน stop ไปแล้ว รอสัญญาณรอบใหม่ค่อยกลับเข้า

    for date, row in df.iterrows():
        price = row["close"]
        want = row["position"] == 1
        holding = units > 0

        # เช็ค stop loss ก่อนทุกอย่าง (ขณะถืออยู่)
        if holding and stop_pct is not None:
            if price <= entry_price * (1 - stop_pct):
                gross = units * price
                fee = gross * fee_rate
                cash = gross - fee
                total_fees += fee
                trades.append({"pnl_pct": (price/entry_price - 1) * 100,
                               "exit_reason": "STOP"})
                units = 0.0
                stopped_out = True   # ห้ามกลับเข้าจนกว่าสัญญาณจะดับแล้วติดใหม่
                holding = False

        # สัญญาณดับ -> รีเซ็ตให้กลับเข้าได้เมื่อสัญญาณติดรอบหน้า
        if not want:
            stopped_out = False

        if want and not holding and not stopped_out:
            fee = cash * fee_rate
            units = (cash - fee) / price
            total_fees += fee
            cash = 0.0
            entry_price = price
        elif not want and holding:
            gross = units * price
            fee = gross * fee_rate
            cash = gross - fee
            total_fees += fee
            trades.append({"pnl_pct": (price/entry_price - 1) * 100,
                           "exit_reason": "MA"})
            units = 0.0

        equity_curve.append(cash + units * price)

    df["equity"] = equity_curve
    return df, trades, total_fees

print("\n[บทที่ 3] MA 20/50 + Stop Loss ระดับต่างๆ (ข้อมูลเต็ม 4 ปี)")
print(" stop  |  return  |  MaxDD  | เทรด | โดนstop | แพ้เฉลี่ย")
print("-" * 60)

for stop in [None, 0.15, 0.10, 0.05, 0.02]:
    d, t, _ = run_backtest_with_stop(data, fast=20, slow=50, stop_pct=stop,
                                     fee_rate=0.001, initial_cash=INITIAL)
    ret = (d["equity"].iloc[-1] / INITIAL - 1) * 100
    mdd, _ = max_drawdown(d["equity"])
    stops = sum(1 for x in t if x["exit_reason"] == "STOP")
    losses = [x["pnl_pct"] for x in t if x["pnl_pct"] <= 0]
    avg_loss = np.mean(losses) if losses else 0
    label = "ไม่มี" if stop is None else f"{stop*100:.0f}%"
    print(f" {label:>5} | {ret:>7.1f}% | {mdd:>6.1f}% | {len(t):>4} | {stops:>6} | {avg_loss:>6.1f}%")

# ----------------------------------------------------------
# บทที่ 3.5: จับ Stop Loss ไปสอบ OOS — 944% ของจริงหรือภาพลวง?
# ----------------------------------------------------------
# รันกลยุทธ์ MA 20/50 + stop แต่ละระดับ กับข้อมูลสองก้อนแยกกัน:
#   ครึ่งแรก (train) = ช่วงที่เราเห็นแล้วตอนจูนค่า
#   ครึ่งหลัง (test) = ข้อสอบที่ไม่เคยเห็น
# ถ้า stop ระดับไหน "ดีจริง" มันควรเด่นทั้งสองครึ่ง ไม่ใช่ครึ่งเดียว

def eval_stop(df_data, stop):
    d, t, _ = run_backtest_with_stop(df_data, fast=20, slow=50, stop_pct=stop,
                                     fee_rate=0.001, initial_cash=INITIAL)
    ret = (d["equity"].iloc[-1] / INITIAL - 1) * 100
    mdd, _ = max_drawdown(d["equity"])
    return ret, mdd

print("\n[บทที่ 3.5] Stop Loss สอบสองสนาม (MA 20/50)")
print("          |   ครึ่งแรก (train)   |   ครึ่งหลัง (test)")
print("  stop    |   return |   MaxDD   |   return |   MaxDD")
print("-" * 58)

for stop in [None, 0.15, 0.10, 0.05, 0.02]:
    tr_ret, tr_mdd = eval_stop(train, stop)
    te_ret, te_mdd = eval_stop(test, stop)
    label = "ไม่มี" if stop is None else f"{stop*100:.0f}%"
    print(f"  {label:>5}   | {tr_ret:>7.1f}% | {tr_mdd:>7.1f}%  | {te_ret:>7.1f}% | {te_mdd:>7.1f}%")

# เทียบกับคู่แข่งตลอดกาล: Buy & Hold ของแต่ละครึ่ง
for name, chunk in [("ครึ่งแรก", train), ("ครึ่งหลัง", test)]:
    bh = (chunk["close"].iloc[-1] / chunk["close"].iloc[0] - 1) * 100
    bh_mdd, _ = max_drawdown(chunk["close"])
    print(f"\nBuy & Hold {name}: {bh:+.1f}%  (MaxDD {bh_mdd:.1f}%)")