<script setup>
/**
 * หน้า Futures — แยกขาดจากหน้า spot เดิม (คนละ state, คนละ API, คนละพอร์ต)
 * เงินปลอมทั้งหมด ราคาจริงทั้งหมด
 */
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { fapi } from '../../futuresApi'
import AccountBar from './AccountBar.vue'
import OrderPanel from './OrderPanel.vue'
import PositionsHistoryTabs from './PositionsHistoryTabs.vue'
import FuturesChart from './FuturesChart.vue'
import ConfirmDialog from './ConfirmDialog.vue'
import FuturesBotPanel from './FuturesBotPanel.vue'

const account = ref(null)
const markets = ref([])
const trades = ref([])
const stats = ref(null)
const symbol = ref('BTC/USDT')
const error = ref('')
const loading = ref(true)
const showReset = ref(false)
const botStatus = ref(null)
const botBusy = ref('')
let timer = null
let botTimer = null

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

async function refreshBotStatus() {
  try { botStatus.value = await fapi.botStatus() } catch { /* เงียบไว้ ไม่รบกวนจอหลัก */ }
}

async function toggleBot(sym) {
  botBusy.value = sym
  try {
    const nowEnabled = !botStatus.value?.symbols?.[sym]?.enabled
    await fapi.setBotEnabled(sym, nowEnabled)
    await refreshBotStatus()
  } finally { botBusy.value = '' }
}

async function onChanged() { await refresh(true) }

function openReset() { showReset.value = true }
async function confirmReset(value) {
  showReset.value = false
  const n = Number(value)
  if (!n || n <= 0) return
  await fapi.reset(n)
  await refresh(true)
}

onMounted(async () => {
  await refresh(true)
  await refreshBotStatus()
  timer = setInterval(() => refresh(false), 3000)
  botTimer = setInterval(refreshBotStatus, 8000)
})
onUnmounted(() => { clearInterval(timer); clearInterval(botTimer) })

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
      <button class="ghost" @click="openReset">ล้างพอร์ตเริ่มใหม่</button>
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

          <!-- รวม "เปิดอยู่"/"ปิดแล้ว" เป็น tab เดียว — เดิมตอนไม่มีประวัติ การ์ด
               ไม้ที่ปิดแล้วจะว่างเปล่าแต่ยังกินพื้นที่แนวตั้งไปฟรีๆ -->
          <PositionsHistoryTabs :positions="account.positions" :trades="trades" :stats="stats"
                                @changed="onChanged" />

          <!-- บอทอัตโนมัติ + บันทึกเหตุการณ์ — เต็มความกว้าง เรียงต่อกัน
               (ไม่ใช่ 2 คอลัมน์เคียงกันแบบเดิม) -->
          <FuturesBotPanel v-if="botStatus" :status="botStatus" :busy="botBusy" @toggle="toggleBot" />

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

        <!-- คอลัมน์ขวา: เหลือแค่ OrderPanel ตัวเดียว ทำ sticky ให้เห็นตลอดตอนเลื่อนจอ -->
        <div class="col-side">
          <OrderPanel :symbol="symbol" :mark-price="current.mark_price"
                      :available="account.available_margin" :leverage="levOf"
                      :funding-pct="current.funding_rate_pct" :locked="!!heldPosition"
                      @submitted="onChanged" @leverage="refresh(false)" />
        </div>
      </div>
    </template>

    <ConfirmDialog
      :open="showReset"
      title="ล้างพอร์ตเริ่มใหม่"
      message="ไม้ที่เปิดอยู่ทั้งหมดจะถูกล้างไปด้วย ย้อนกลับไม่ได้ (แต่ log เหตุการณ์เก่ายังอยู่)"
      tone="danger"
      with-input
      input-label="ทุนเริ่มต้นใหม่ (USDT)"
      input-type="number"
      :input-default="10000"
      confirm-label="ล้างพอร์ต"
      @confirm="confirmReset"
      @cancel="showReset = false"
    />
  </div>
</template>

<style scoped>
.wrap {
  /* เพจนี้เคยพึ่ง max-width จาก wrapper ใน App.vue เก่า (ก่อนย้ายไป router) —
     ตอน refactor เป็น <router-view/> wrapper นั้นหายไปด้วย แต่ .wrap ไม่เคยมี
     max-width ของตัวเองเลย เลยยืดเต็มจอไม่มีเพดานบนจอกว้างๆ ต้องประกาศเองตรงนี้
     เสมอ ห้ามพึ่งพา wrapper จากภายนอกอีก (กว้างกว่า spot เพราะเป็น layout
     2 คอลัมน์ที่มีข้อมูลแน่นกว่า ต้องการพื้นที่มากกว่าหน้า spot) */
  max-width: 1440px; margin: 0 auto; padding: 24px 20px;
  display: flex; flex-direction: column; gap: 18px;
}
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
.col-side { position: sticky; top: 18px; }
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

@media (max-width: 1080px) { .grid { grid-template-columns: 1fr; } .col-side { position: static; } }
</style>
