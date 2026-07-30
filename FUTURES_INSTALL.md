# Futures (เงินปลอม) — เมนูแยกใน dashboard

พอร์ต futures แยกขาดจาก spot เดิม: คนละไฟล์ state, คนละ API prefix, คนละคอมโพเนนต์
ของเดิมไม่ต้องแก้ logic แม้แต่บรรทัดเดียว มีแค่ 3 จุดที่ต้อง "เสียบสาย"

---

## 1. Backend — วาง 3 ไฟล์ในโฟลเดอร์ `Trader` (ที่มี `copilot.py` / `main.py`)

```
futures.py        ← engine (leverage, long/short, liquidation, funding, TP/SL)
futures_api.py    ← APIRouter /api/futures/*
futures_cli.py    ← เทรดจาก terminal ด้วยพอร์ตเดียวกัน (ไม่บังคับ)
```

### แก้ `main.py` — เพิ่ม 2 บรรทัด

ใต้บรรทัด `from copilot import ...` เพิ่ม:

```python
from futures_api import router as futures_router
```

หลังบรรทัดที่สร้าง `app = FastAPI(...)` และ `add_middleware(...)` เพิ่ม:

```python
app.include_router(futures_router)
```

จบ. restart uvicorn แล้วเช็คว่า <http://localhost:8000/docs> มี `/api/futures/...` ขึ้นมา

> ไฟล์ที่ engine จะสร้างเอง: `futures_state.json` (พอร์ต) และ `futures_trades.log` (บันทึกทุกเหตุการณ์)

---

## 2. Frontend — วางไฟล์

```
src/futuresApi.js
src/components/Sidebar.vue                 ← ทับตัวเดิม (เพิ่มเมนู Futures)
src/components/futures/FuturesView.vue
src/components/futures/AccountBar.vue
src/components/futures/OrderPanel.vue
src/components/futures/PositionsTable.vue
src/components/futures/HistoryTable.vue
src/components/futures/FuturesChart.vue
src/components/futures/RiskLadder.vue
```

### แก้ `src/App.vue` — 4 จุดเล็ก ๆ

**(1)** ใน `<script setup>` เพิ่ม:

```js
import FuturesView from './components/futures/FuturesView.vue'
const view = ref('spot')          // 'spot' | 'futures'
```

**(2)** ให้ `refresh()` ของ spot หยุดยิงตอนอยู่หน้า futures (ประหยัด rate limit):

```js
async function refresh() {
  if (view.value !== 'spot') return
  // ...โค้ดเดิม
}
```

**(3)** ส่ง prop + รับ event ที่ Sidebar:

```html
<Sidebar :view="view" @nav="view = $event" />
```

**(4)** ครอบเนื้อหาเดิมของ `<main>` ด้วยเงื่อนไข แล้วเพิ่มหน้า futures:

```html
<main>
  <template v-if="view === 'spot'">
    <!-- ...ทุกอย่างที่มีอยู่เดิมใน main ยกมาไว้ในนี้ ไม่ต้องแก้อะไร... -->
  </template>

  <FuturesView v-else-if="view === 'futures'" />
</main>
```

### dependency

ใช้ของที่มีอยู่แล้วทั้งหมด (`lucide-vue-next`, `lightweight-charts`).
ถ้ายังไม่มี:

```bash
npm i lightweight-charts lucide-vue-next
```

`FuturesChart.vue` รองรับ lightweight-charts ทั้ง v4 และ v5

---

## 3. เทรดจาก terminal (พอร์ตเดียวกับเว็บ)

```bash
python futures_cli.py watch                       # จอเฝ้าราคา + ไม้ที่ถือ
python futures_cli.py long BTC/USDT 200 10 --sl 95000 --tp 110000
python futures_cli.py short ETH/USDT 100 5
python futures_cli.py close BTC/USDT 0.5          # ปิดครึ่ง
python futures_cli.py stats
python futures_cli.py reset 10000
```

---

## สิ่งที่จำลองไว้ (และไม่ได้จำลอง)

| จำลองแล้ว | ยังไม่จำลอง |
|---|---|
| leverage 1–125x, initial margin | order book / slippage / partial fill |
| long + short | limit order รอคิว (ทุกคำสั่งเป็น market/taker) |
| liquidation จาก maintenance margin จริง | cross margin แบบรวมพอร์ตจริง |
| funding rate จริง เก็บ/จ่ายทุก 8 ชม. | ADL, insurance fund |
| fee taker 0.05% / maker 0.02% บน notional | tier maintenance ครบทุกเหรียญ (ใช้ตารางย่อ) |
| TP / SL / ปิดบางส่วน / ถัวเฉลี่ยราคาเข้า | |

TP/SL/liquidation ทำงานใน background thread ฝั่ง backend ทุก 10 วินาที —
ปิดเบราว์เซอร์แล้วไม้ยังถูกตัดตามแผน เหมือนของจริง

## ตัวเลขที่ควรจับตาระหว่างซ้อม

- **ล้างพอร์ตกี่ครั้ง** — สำคัญกว่ากำไรรวม เพราะ 1 ครั้งลบผลงานหลายไม้
- **leverage เฉลี่ย** เทียบกับ **win rate** — ถ้า leverage สูงขึ้นแล้ว win rate ตก คือกำลังเทรดด้วยความกลัว
- **ค่าธรรมเนียม + funding รวม** — ต้นทุนที่ไม่มีใครนับ แต่กินกำไรจริง
- **จบด้วย SL vs ล้างพอร์ต** — สัดส่วนนี้บอกว่าคุณคุมความเสี่ยงเองหรือให้ตลาดคุมให้
