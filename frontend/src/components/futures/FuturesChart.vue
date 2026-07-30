<script setup>
/**
 * กราฟแท่งเทียนจากตลาด futures จริง (ไม่ใช่ spot) + เส้นอ้างอิงของไม้ที่ถืออยู่:
 * เส้นทึบ = ราคาเข้า, เส้นประแดง = ราคาล้างพอร์ต, เส้นประ = SL/TP
 * รองรับ lightweight-charts ทั้ง v4 และ v5
 */
import { ref, onMounted, onUnmounted, watch } from 'vue'
// namespace import: v4 ไม่มี export ชื่อ CandlestickSeries — named import ตัวนี้
// ทำให้ Vite โยน "does not provide an export named" ตั้งแต่โหลดโมดูล (จอขาวทันที)
import * as LWC from 'lightweight-charts'
import { fapi } from '../../futuresApi'
const { createChart, CandlestickSeries, LineStyle } = LWC

const props = defineProps({ symbol: String, position: Object, markPrice: Number })
const el = ref(null)
const tf = ref('15m')
const err = ref('')
const TFS = ['5m', '15m', '1h', '4h', '1d']

let chart = null
let series = null
let timer = null
let lines = []

function build() {
  chart = createChart(el.value, {
    height: 320,
    layout: { background: { color: 'transparent' }, textColor: '#8a8a85', fontSize: 11 },
    grid: { vertLines: { visible: false }, horzLines: { color: 'rgba(0,0,0,.05)' } },
    rightPriceScale: { borderVisible: false },
    timeScale: { borderVisible: false, timeVisible: true },
    crosshair: { mode: 1 },
  })
  const opts = {
    upColor: '#059669', downColor: '#dc2626', borderVisible: false,
    wickUpColor: '#059669', wickDownColor: '#dc2626',
  }
  // v5 ใช้ addSeries(CandlestickSeries, ...) / v4 ใช้ addCandlestickSeries(...)
  series = typeof chart.addSeries === 'function' && CandlestickSeries
    ? chart.addSeries(CandlestickSeries, opts)
    : chart.addCandlestickSeries(opts)
}

async function load() {
  try {
    const { candles } = await fapi.candles(props.symbol, tf.value, 300)
    series?.setData(candles)
    err.value = ''
  } catch (e) { err.value = e.message }
}

function drawLines() {
  lines.forEach((l) => { try { series.removePriceLine(l) } catch {} })
  lines = []
  const p = props.position
  if (!p || !series) return
  const add = (price, color, title, dashed = true) => {
    if (!price) return
    lines.push(series.createPriceLine({
      price, color, lineWidth: dashed ? 1 : 2,
      lineStyle: dashed ? LineStyle?.Dashed ?? 2 : LineStyle?.Solid ?? 0,
      axisLabelVisible: true, title,
    }))
  }
  add(p.entry_price, '#171717', 'เข้า', false)
  add(p.liq_price, '#dc2626', 'ล้างพอร์ต')
  add(p.sl, '#dc2626', 'SL')
  add(p.tp, '#059669', 'เป้า')
}

onMounted(async () => {
  build()
  await load()
  drawLines()
  timer = setInterval(load, 15000)
})
onUnmounted(() => { clearInterval(timer); chart?.remove() })
watch(() => [props.symbol, tf.value], async () => { await load(); drawLines() })
watch(() => props.position, drawLines, { deep: true })
</script>

<template>
  <div class="card chart">
    <div class="head">
      <div>
        <b>{{ symbol }}</b>
        <span class="muted perp">perpetual · ตลาด futures จริง</span>
      </div>
      <div class="tfs">
        <button v-for="t in TFS" :key="t" :class="['chip', tf === t && 'on']" @click="tf = t">{{ t }}</button>
      </div>
    </div>
    <div ref="el" class="canvas" />
    <p v-if="err" class="down msg">โหลดกราฟไม่ได้: {{ err }}</p>
  </div>
</template>

<style scoped>
.chart { display: flex; flex-direction: column; gap: 12px; }
.head { display: flex; justify-content: space-between; align-items: center; gap: 12px; flex-wrap: wrap; }
.head b { font-weight: 500; }
.perp { font-size: 11.5px; margin-left: 8px; }
.tfs { display: flex; gap: 5px; }
.chip {
  border: 1px solid var(--line); background: transparent; color: var(--ink-3);
  padding: 4px 10px; border-radius: 7px; font: inherit; font-size: 11px; cursor: pointer;
}
.chip.on { background: var(--dark); border-color: var(--dark); color: #fff; }
.canvas { width: 100%; }
.msg { font-size: 12px; margin: 0; }
</style>
