<script setup>
import { ref, onMounted, onUnmounted, watch, computed } from 'vue'
import { createChart } from 'lightweight-charts'
import { api, splitSymbol } from '../api'

const props = defineProps({ analysis: Object, symbol: String })
const quote = computed(() => splitSymbol(props.symbol).quote)
const el = ref(null)
const tf = ref('1h')
let chart, candleSeries, maFast, maSlow, timer

function sma(data, n) {
  const out = []
  for (let i = n - 1; i < data.length; i++) {
    let s = 0
    for (let k = i - n + 1; k <= i; k++) s += data[k].close
    out.push({ time: data[i].time, value: s / n })
  }
  return out
}

async function load() {
  const data = await api.candles(props.symbol, tf.value)
  candleSeries.setData(data)
  maFast.setData(sma(data, 20))
  maSlow.setData(sma(data, 50))
}

onMounted(async () => {
  chart = createChart(el.value, {
    height: 300, layout: { background: { color: 'transparent' }, textColor: '#a3a3a3' },
    grid: { vertLines: { visible: false }, horzLines: { visible: false } },
    rightPriceScale: { borderVisible: false }, timeScale: { borderVisible: false },
  })
  candleSeries = chart.addCandlestickSeries({
    upColor: '#171717', downColor: '#ffffff', borderVisible: true,
    borderUpColor: '#171717', borderDownColor: '#171717',
    wickUpColor: '#171717', wickDownColor: '#171717',
  })
  maFast = chart.addLineSeries({ color: '#737373', lineWidth: 1 })
  maSlow = chart.addLineSeries({ color: '#d4d4d4', lineWidth: 1 })
  await load()
  timer = setInterval(load, 60_000)
})
onUnmounted(() => { clearInterval(timer); chart?.remove() })
watch(() => props.symbol, load)

async function setTf(x) { tf.value = x; await load() }
</script>

<template>
  <div class="card">
    <div style="display:flex;justify-content:space-between;align-items:start;margin-bottom:8px">
      <div>
        <div class="muted" style="font-size:13px">{{ symbol }}</div>
        <div class="num-lg">{{ analysis.live_price.toLocaleString(undefined,{maximumFractionDigits:2}) }}
          <span class="faint" style="font-size:16px;font-weight:400">{{ quote }}</span></div>
        <div class="muted" style="font-size:12px">
          MA20 <b style="color:var(--ink)">{{ analysis.ma_fast.toFixed(0) }}</b> ·
          MA50 <b style="color:var(--ink)">{{ analysis.ma_slow.toFixed(0) }}</b>
        </div>
      </div>
      <div style="background:#f0f0ee;border-radius:999px;padding:4px;display:flex;gap:2px">
        <button v-for="x in ['1h','4h','1d']" :key="x" class="pill"
          :class="{ active: tf === x }" @click="setTf(x)">{{ x.toUpperCase() }}</button>
      </div>
    </div>
    <div ref="el" class="dotgrid"></div>
  </div>
</template>
