<script setup>
import { ref, onMounted, onUnmounted, watch } from 'vue'
import { api } from './api'
import Sidebar from './components/Sidebar.vue'
import RegimeBanner from './components/RegimeBanner.vue'
import PriceChart from './components/PriceChart.vue'
import CopilotPanel from './components/CopilotPanel.vue'
import TradeForm from './components/TradeForm.vue'
import JournalTable from './components/JournalTable.vue'
import AutoToggle from './components/AutoToggle.vue'
import AssetTabs from './components/AssetTabs.vue'
import PortfolioCards from './components/PortfolioCards.vue'
import FuturesView from './components/futures/FuturesView.vue'

const view = ref('spot')          // 'spot' | 'futures'
const assetList = ref(['BTCTHB'])
const symbol = ref('BTCTHB')
const analysis = ref(null)
const journal = ref(null)
const stats = ref(null)
const bot = ref(null)
const showForm = ref(false)
const error = ref('')
const updatedAt = ref('')
let prevCanTrade = null

function browserNotify(a) {
  if (!('Notification' in window)) return
  if (prevCanTrade === false && a.can_trade === true && Notification.permission === 'granted') {
    new Notification('⚡ สัญญาณฝั่งซื้อครบ', {
      body: `BTC ${a.live_price.toLocaleString()} — เปิด dashboard ดูก่อนตัดสินใจ`,
    })
  }
  prevCanTrade = a.can_trade
}

async function refresh() {
  if (view.value !== 'spot') return
  try {
    ;[analysis.value, journal.value, stats.value, bot.value] = await Promise.all([
      api.analysis(symbol.value), api.journal(), api.stats(), api.bot(),
    ])
    error.value = ''
    updatedAt.value = new Date().toLocaleTimeString('th-TH')
    browserNotify(analysis.value)
  } catch (e) { error.value = 'ต่อ backend ไม่ได้ — เช็คว่า uvicorn รันอยู่ที่ :8000' }
}

let timer
onMounted(async () => {
  if ('Notification' in window && Notification.permission === 'default')
    Notification.requestPermission()
  try {
    assetList.value = (await api.assets()).watchlist.map(a => a.symbol)
    if (assetList.value.length) symbol.value = assetList.value[0]
  } catch {}
  refresh(); timer = setInterval(refresh, 30_000)
})

watch(symbol, refresh)
watch(view, (v) => { if (v === 'spot') refresh() })
onUnmounted(() => clearInterval(timer))
</script>

<template>
  <div style="display:flex" id="top">
    <Sidebar :view="view" @nav="view = $event" />
    <div v-if="view === 'spot'" style="flex:1;max-width:1100px;margin:0 auto;padding:24px 16px;
                display:flex;flex-direction:column;gap:16px">
      <header style="display:flex;justify-content:space-between;align-items:center">
        <div>
          <div class="faint" style="font-size:13px">Trading Copilot</div>
          <h1 style="font-size:20px;letter-spacing:-0.02em">สวัสดีครับ, Panupong</h1>
        </div>
        <div style="display:flex;align-items:center;gap:12px">
          <AssetTabs :assets="assetList" v-model="symbol" />
          <div class="faint" style="font-size:12px">1H · อัปเดตทุก 30s</div>
        </div>
      </header>

      <div v-if="error" class="card" style="border-color:var(--down);color:var(--down)">{{ error }}</div>

      <RegimeBanner v-if="analysis" :analysis="analysis" />

      <div style="display:grid;grid-template-columns:2fr 1fr;gap:16px" class="grid-main">
        <PriceChart v-if="analysis" :analysis="analysis" :symbol="symbol" />
        <CopilotPanel v-if="analysis" :analysis="analysis" :updated-at="updatedAt"
          @open-form="showForm = !showForm" />
      </div>

      <TradeForm v-if="showForm && analysis" :analysis="analysis" :journal="journal" :symbol="symbol"
        @done="showForm = false; refresh()" />

      <div id="bot">
        <PortfolioCards v-if="journal && bot" :journal="journal" :stats="stats" :bot="bot" />
      </div>

      <AutoToggle :assets="assetList" />

      <div id="journal">
        <JournalTable v-if="journal" :journal="journal" @closed="refresh" />
      </div>
    </div>

    <div v-else-if="view === 'futures'" style="flex:1;max-width:1280px;margin:0 auto;padding:24px 16px">
      <FuturesView />
    </div>
  </div>
</template>

<style scoped>
@media (max-width: 900px) { .grid-main { grid-template-columns: 1fr !important; } }
</style>
