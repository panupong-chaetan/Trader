<script setup>
/**
 * บันไดความเสี่ยง — เส้นเดียวที่ตอบคำถามสำคัญที่สุดของ futures:
 * "ราคาตอนนี้ห่างจากจุดล้างพอร์ตแค่ไหน"
 * วางทุกระดับ (liq / SL / เข้า / mark / TP) บนสเกลเดียวกันตามระยะจริง
 */
import { computed } from 'vue'

const props = defineProps({
  side: String,
  entry: Number,
  mark: Number,
  liq: Number,
  tp: Number,
  sl: Number,
  compact: Boolean,
})

const nums = computed(() =>
  [props.entry, props.mark, props.liq, props.tp, props.sl].filter((n) => n > 0))

const range = computed(() => {
  const lo = Math.min(...nums.value)
  const hi = Math.max(...nums.value)
  const pad = (hi - lo) * 0.08 || hi * 0.01
  return { lo: lo - pad, hi: hi + pad }
})

const pos = (v) => {
  const { lo, hi } = range.value
  if (!v || hi === lo) return null
  return Math.max(0, Math.min(100, ((v - lo) / (hi - lo)) * 100))
}

const fmt = (v) => v?.toLocaleString(undefined, { maximumFractionDigits: 2 })

// โซนกำไร: จากจุดเข้าไปทางเป้า
const profitZone = computed(() => {
  const a = pos(props.entry)
  const b = pos(props.tp || props.mark)
  if (a === null || b === null) return null
  return { left: Math.min(a, b), width: Math.abs(b - a) }
})

const liqDistance = computed(() =>
  props.mark && props.liq ? Math.abs((props.liq - props.mark) / props.mark) * 100 : null)

const danger = computed(() => liqDistance.value !== null && liqDistance.value < 5)

const marks = computed(() => [
  { key: 'liq', label: 'ล้างพอร์ต', value: props.liq, x: pos(props.liq), tone: 'liq' },
  { key: 'sl', label: 'SL', value: props.sl, x: pos(props.sl), tone: 'stop' },
  { key: 'entry', label: 'เข้า', value: props.entry, x: pos(props.entry), tone: 'entry' },
  { key: 'tp', label: 'เป้า', value: props.tp, x: pos(props.tp), tone: 'target' },
].filter((m) => m.x !== null))
</script>

<template>
  <div class="ladder" :class="{ compact }">
    <div class="track">
      <div v-if="profitZone" class="zone"
           :style="{ left: profitZone.left + '%', width: profitZone.width + '%' }" />

      <!-- ระดับต่าง ๆ -->
      <div v-for="m in marks" :key="m.key" class="tick" :class="m.tone"
           :style="{ left: m.x + '%' }">
        <span class="tick-line" />
        <span v-if="!compact" class="tick-label">{{ m.label }}<b>{{ fmt(m.value) }}</b></span>
      </div>

      <!-- ราคาปัจจุบัน -->
      <div v-if="pos(mark) !== null" class="now" :style="{ left: pos(mark) + '%' }">
        <span class="now-dot" />
        <span class="now-label">{{ fmt(mark) }}</span>
      </div>
    </div>

    <div v-if="!compact" class="foot">
      <span :class="danger ? 'down' : 'muted'">
        {{ danger ? '⚠ ' : '' }}ห่างจุดล้างพอร์ต {{ liqDistance?.toFixed(2) }}%
      </span>
      <span class="muted">{{ side === 'long' ? 'ขาขึ้น' : 'ขาลง' }} — ราคาวิ่งผิดทางเท่านี้คือหมดไม้</span>
    </div>
  </div>
</template>

<style scoped>
.ladder { display: flex; flex-direction: column; gap: 22px; padding-top: 4px; }
.ladder.compact { gap: 0; }
.track {
  position: relative; height: 4px; border-radius: 2px;
  background: color-mix(in srgb, var(--line) 80%, transparent);
}
.compact .track { height: 3px; }
.zone {
  position: absolute; inset-block: 0; border-radius: 2px;
  background: color-mix(in srgb, var(--ink) 22%, transparent);
}
.tick { position: absolute; top: -6px; transform: translateX(-50%); }
.tick-line { display: block; width: 1px; height: 16px; background: var(--ink-3); }
.tick.liq .tick-line { width: 2px; height: 20px; margin-top: -2px; background: #dc2626; }
.tick.entry .tick-line { background: var(--ink); height: 18px; margin-top: -1px; }
.tick.target .tick-line { background: #059669; }
.tick.stop .tick-line { background: #dc2626; opacity: .55; }
.tick-label {
  position: absolute; top: 20px; left: 50%; transform: translateX(-50%);
  display: flex; flex-direction: column; align-items: center; gap: 1px;
  font-size: 10px; letter-spacing: .04em; text-transform: uppercase;
  color: var(--ink-3); white-space: nowrap;
}
.tick-label b {
  font-size: 12px; letter-spacing: 0; text-transform: none;
  color: var(--ink); font-variant-numeric: tabular-nums; font-weight: 500;
}
.tick.liq .tick-label b { color: #dc2626; }
.now { position: absolute; top: -8px; transform: translateX(-50%); }
.now-dot {
  display: block; width: 12px; height: 12px; border-radius: 50%;
  background: var(--dark); border: 3px solid var(--paper, #fff); box-sizing: content-box;
  margin-top: 3px;
}
.now-label {
  position: absolute; bottom: 22px; left: 50%; transform: translateX(-50%);
  font-size: 11px; font-weight: 600; font-variant-numeric: tabular-nums;
  background: var(--dark); color: #fff; padding: 2px 7px; border-radius: 6px;
  white-space: nowrap;
}
.compact .now-label { display: none; }
.foot { display: flex; justify-content: space-between; gap: 12px; font-size: 12px; flex-wrap: wrap; }
</style>
