<script setup>
import { computed } from 'vue'
import { TrendingUp, TrendingDown, Minus } from 'lucide-vue-next'
import { splitSymbol } from '../api'
const props = defineProps({ analysis: Object })
const prettySymbol = computed(() => {
  const { base, quote } = splitSymbol(props.analysis.symbol || '')
  return quote ? `${base}/${quote}` : props.analysis.symbol
})
const meta = computed(() => ({
  TREND_UP:   { label: 'TREND UP',   icon: TrendingUp,
    note: 'แนวโน้มใหญ่ชี้ขึ้น — สัญญาณฝั่งซื้อมีน้ำหนัก' },
  TREND_DOWN: { label: 'TREND DOWN', icon: TrendingDown,
    note: 'แนวโน้มใหญ่ชี้ลง — เราเล่นฝั่งซื้ออย่างเดียว: ถือเงินสดคือ position' },
  SIDEWAYS:   { label: 'SIDEWAYS',   icon: Minus,
    note: 'เส้นพันกัน / เทรนด์ไม่ชัด — โซนอันตรายของระบบ MA นั่งทับมือไว้' },
}[props.analysis.regime]))
</script>

<template>
  <div class="card card--dark" style="display:flex;align-items:center;gap:16px;padding:18px 24px">
    <div style="width:40px;height:40px;border-radius:12px;background:rgba(255,255,255,.1);
                display:grid;place-items:center">
      <component :is="meta.icon" :size="18" />
    </div>
    <div style="flex:1">
      <div style="font-size:11px;letter-spacing:.12em;text-transform:uppercase;opacity:.5">
        สภาพตลาด · {{ prettySymbol }} · 1H</div>
      <div><b>{{ meta.label }}</b>
        <span style="opacity:.7;font-size:13px;margin-left:12px">{{ meta.note }}</span></div>
    </div>
    <div class="faint" style="font-size:12px;text-align:right">
      ความชัน MA50 {{ analysis.slope_pct >= 0 ? '+' : '' }}{{ analysis.slope_pct.toFixed(2) }}%<br>
      ระยะห่างเส้น {{ analysis.spread_pct.toFixed(2) }}%
    </div>
  </div>
</template>
