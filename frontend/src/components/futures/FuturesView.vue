<script setup>
/**
 * หน้า Futures — แยกขาดจากหน้า spot เดิม (คนละ state, คนละ API, คนละพอร์ต)
 * เงินปลอมทั้งหมด ราคาจริงทั้งหมด
 */
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { fapi } from '../../futuresApi'
import AccountBar from './AccountBar.vue'
import OrderPanel from './OrderPanel.vue'
import PositionsTable from './PositionsTable.vue'
import HistoryTable from './HistoryTable.vue'
import FuturesChart from './FuturesChart.vue'

const account = ref(null)
const markets = ref([])
const trades = ref([])
const stats = ref(null)
const symbol = ref('BTC/USDT')
const error = ref('')
const loading = ref(true)
let timer = null

const current = computed(() => markets.value.find((m) => m.symbol === symbol.value) || {})
const heldPosition = computed(() =>
  account.value?.positions.find((p) => p.symbol === symbol.value) || null)
const levOf = computed(() => account.value?.leverage?.[symbol.value] || 10)

async function refresh(full = false) {
  try {
    const jobs = [fapi.account(), fapi.market()]
    if (full) jobs.push(fapi.history(60), fapi.stats())
    const [acc, mk, hist, st] = await Promise.all(jobs)
    account.value = acc
    markets.value = mk.markets
    if (full) { trades.value = hist.trades; stats.value = st }
    error.value = ''
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

async function onChanged() { await refresh(true) }

async function resetPort() {
  const v = prompt('ล้างพอร์ต futures แล้วเริ่มใหม่ ด้วยทุนกี่ USDT?', '10000')
  if (!v) return
  await fapi.reset(Number(v))
  await refresh(true)
}

onMounted(async () => {
  await refresh(true)
  timer = setInterval(() => refresh(false), 3000)
})
onUnmounted(() => clearInterval(timer))

const fmt = (v, d = 2) => (v ?? 0).toLocaleString(undefined, { minimumFractionDigits: d, maximumFractionDigits: d })
</script>

<template>
  <div class="wrap">
    <header class="top">
      <div>
        <h1>Futures — สนามซ้อม</h1>
        <p class="muted sub">
          ราคาจริงจากตลาด USDⓈ-M perpetual · เงินปลอม 100% · มี leverage, short,
          funding และการล้างพอร์ตครบเหมือนของจริง
        </p>
      </div>
      <button class="ghost" @click="resetPort">ล้างพอร์ตเริ่มใหม่</button>
    </header>

    <div v-if="error" class="card alert">
      ต่อ backend ไม่ได้ — {{ error }}<br />
      <span class="muted">ตรวจว่า <code>uvicorn main:app --port 8000</code> รันอยู่ และเสียบ
        <code>futures_router</code> ใน main.py แล้ว</span>
    </div>

    <p v-else-if="loading" class="faint">กำลังโหลดพอร์ต…</p>

    <template v-else-if="account">
      <AccountBar :account="account" :stats="stats" />

      <!-- แถบเลือกสินทรัพย์ พร้อม funding -->
      <div class="tabs">
        <button v-for="m in markets" :key="m.symbol"
                :class="['tab', symbol === m.symbol && 'on']" @click="symbol = m.symbol">
          <span class="t-name">{{ m.label }}</span>
          <span class="t-price mono">{{ m.mark_price ? fmt(m.mark_price) : '—' }}</span>
          <span class="t-fund mono" :class="m.funding_rate_pct > 0 ? 'down' : 'up'">
            funding {{ m.funding_rate_pct >= 0 ? '+' : '' }}{{ m.funding_rate_pct?.toFixed(4) }}%
          </span>
          <span v-if="account.positions.some((p) => p.symbol === m.symbol)" class="dot" />
        </button>
      </div>

      <div class="grid">
        <div class="col-main">
          <FuturesChart :symbol="symbol" :position="heldPosition" :mark-price="current.mark_price" />
          <PositionsTable :positions="account.positions" @changed="onChanged" />
          <HistoryTable :trades="trades" :stats="stats" />
        </div>

        <div class="col-side">
          <OrderPanel :symbol="symbol" :mark-price="current.mark_price"
                      :available="account.available_margin" :leverage="levOf"
                      :funding-pct="current.funding_rate_pct"
                      @submitted="onChanged" @leverage="refresh(false)" />

          <div class="card feed">
            <span class="ttl">บันทึกเหตุการณ์</span>
            <div v-if="!account.events.length" class="faint tiny">ยังไม่มีเหตุการณ์</div>
            <div v-for="(e, i) in account.events" :key="i" class="ev" :class="e.kind">
              <span class="ev-time mono">{{ new Date(e.ts).toLocaleTimeString('th-TH') }}</span>
              <span class="ev-msg">{{ e.message }}</span>
            </div>
          </div>

          <div class="card note">
            <span class="ttl">อ่านก่อนซ้อม</span>
            <ul>
              <li><b>Leverage ไม่เพิ่มโอกาสชนะ</b> — เพิ่มแค่ขนาดผลลัพธ์และย่นระยะถึงจุดล้างพอร์ต
                20x คือขาดทุน 5% แล้วหมดไม้</li>
              <li><b>funding เก็บทุก 8 ชม.</b> ถือไม้ทวนกระแสนาน ๆ ต้นทุนกินกำไรเงียบ ๆ</li>
              <li><b>ค่าธรรมเนียมคิดบน notional</b> ไม่ใช่บน margin — 10x เท่ากับจ่ายค่าธรรมเนียม
                10 เท่าของไม้ spot ขนาดเดียวกัน</li>
              <li>TP/SL/liquidation ทำงานฝั่ง backend ทุก 10 วิ ปิดเบราว์เซอร์ก็ยังตัด</li>
            </ul>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>

<style scoped>
.wrap { display: flex; flex-direction: column; gap: 18px; }
.top { display: flex; justify-content: space-between; align-items: flex-start; gap: 16px; flex-wrap: wrap; }
h1 { font-size: 21px; font-weight: 500; margin: 0 0 5px; letter-spacing: -.01em; }
.sub { font-size: 12.5px; margin: 0; max-width: 62ch; line-height: 1.6; }
.ghost {
  border: 1px solid var(--line); background: transparent; color: var(--ink-3);
  padding: 8px 14px; border-radius: 10px; font: inherit; font-size: 12px; cursor: pointer;
}
.ghost:hover { border-color: var(--ink); color: var(--ink); }
.alert { border-color: #dc2626; color: #dc2626; font-size: 13px; line-height: 1.6; }
.alert code { font-size: 11.5px; background: rgba(0,0,0,.05); padding: 1px 5px; border-radius: 4px; }

.tabs { display: flex; gap: 8px; overflow-x: auto; padding-bottom: 2px; }
.tab {
  position: relative; flex: 0 0 auto; text-align: left; cursor: pointer; font: inherit;
  background: #fff; border: 1px solid var(--line); border-radius: 12px;
  padding: 10px 16px; display: flex; flex-direction: column; gap: 2px; min-width: 148px;
  transition: border-color .12s ease;
}
.tab:hover { border-color: var(--ink-3); }
.tab.on { border-color: var(--ink); }
.t-name { font-size: 11px; letter-spacing: .04em; text-transform: uppercase; color: var(--ink-3); }
.t-price { font-size: 15px; font-weight: 500; }
.t-fund { font-size: 10.5px; }
.dot {
  position: absolute; top: 9px; right: 10px; width: 6px; height: 6px;
  border-radius: 50%; background: var(--ink);
}
.mono { font-variant-numeric: tabular-nums; }

.grid { display: grid; grid-template-columns: minmax(0, 1fr) 372px; gap: 18px; align-items: start; }
.col-main, .col-side { display: flex; flex-direction: column; gap: 18px; min-width: 0; }
.ttl { font-weight: 500; font-size: 13px; }

.feed { display: flex; flex-direction: column; gap: 10px; max-height: 300px; overflow-y: auto; }
.ev { display: flex; gap: 10px; font-size: 12px; line-height: 1.5; padding-bottom: 8px; border-bottom: 1px solid var(--line); }
.ev:last-child { border-bottom: 0; padding-bottom: 0; }
.ev-time { color: var(--ink-3); font-size: 10.5px; padding-top: 1px; flex: 0 0 auto; }
.ev.liquidation .ev-msg { color: #dc2626; font-weight: 500; }
.ev.funding .ev-msg { color: var(--ink-3); }
.tiny { font-size: 12px; }

.note { display: flex; flex-direction: column; gap: 10px; }
.note ul { margin: 0; padding-left: 18px; display: flex; flex-direction: column; gap: 8px; }
.note li { font-size: 12px; line-height: 1.6; color: var(--ink-3); }
.note b { color: var(--ink); font-weight: 500; }

@media (max-width: 1080px) { .grid { grid-template-columns: 1fr; } }
</style>
