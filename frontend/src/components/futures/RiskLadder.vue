<script setup>
/**
 * บันไดความเสี่ยง — เส้นเดียวที่ตอบคำถามสำคัญที่สุดของ futures:
 * "ราคาตอนนี้ห่างจากจุดล้างพอร์ตแค่ไหน"
 * วางทุกระดับ (liq / SL / เข้า / ตอนนี้ / TP) บนสเกลเดียวกันตามระยะจริง
 *
 * v2 — แก้ 2 บั๊กจาก v1:
 *  1) ราคาตอนนี้เคยเป็น label ลอย (position:absolute) ที่ไม่มีพื้นที่จองไว้ ->
 *     โผล่ทับเนื้อหาข้างบน (เช่นแถวตัวเลขใน OrderPanel) ย้ายมาเป็นหัวข้อปกติแทน
 *  2) ตอน preview (ยังไม่เปิดไม้จริง) entry กับ mark คือค่าเดียวกันเป๊ะ ->
 *     สอง tick มาซ้อนจุดเดียวกัน ดูรก -> ซ่อน tick "เข้า" อัตโนมัติเมื่อค่าเท่ากับตอนนี้
 */
import { computed } from 'vue'

const props = defineProps({
  side: String,
  entry: Number,
  mark: Number,
  liq: Number,
  tp: Number,
  sl: Number,
})

const nums = computed(() =>
  [props.entry, props.mark, props.liq, props.tp, props.sl].filter((n) => n > 0))

const range = computed(() => {
  const lo = Math.min(...nums.value)
  const hi = Math.max(...nums.value)
  const pad = (hi - lo) * 0.1 || hi * 0.01
  return { lo: lo - pad, hi: hi + pad }
})

const pos = (v) => {
  const { lo, hi } = range.value
  if (!v || hi === lo) return null
  return Math.max(0, Math.min(100, ((v - lo) / (hi - lo)) * 100))
}

// เลี่ยง label หลุดขอบการ์ดเวลาอยู่ริมสเกล — ใกล้ขอบซ้าย/ขวาให้ชิดขอบแทนกึ่งกลาง
const anchor = (x) => (x < 10 ? 'left' : x > 90 ? 'right' : 'center')

const fmt = (v) => v?.toLocaleString(undefined, { maximumFractionDigits: 2 })

// preview (ยังไม่เปิดไม้): entry ที่ส่งเข้ามา = ราคาตลาดตอนนี้เป๊ะ -> ไม่ต้องมีสอง tick ซ้อนกัน
const entrySameAsMark = computed(() =>
  props.entry && props.mark && Math.abs(props.entry - props.mark) / props.mark < 0.0005)

// โซนกำไร: จากจุดเข้าไปทางเป้า (ถ้าไม่มีเป้า ใช้ตอนนี้แทนเพื่อให้เห็นทิศที่กำลังไป)
const profitZone = computed(() => {
  const a = pos(props.entry)
  const b = pos(props.tp || props.mark)
  if (a === null || b === null) return null
  return { left: Math.min(a, b), width: Math.abs(b - a) }
})

const liqDistance = computed(() =>
  props.mark && props.liq ? Math.abs((props.liq - props.mark) / props.mark) * 100 : null)

const danger = computed(() => liqDistance.value !== null && liqDistance.value < 5)

// เทียบราคาตอนนี้กับจุดเข้า — บอกว่ากำลังไปทางที่ได้กำไรหรือขาดทุนของฝั่งที่ถืออยู่
const moveInfo = computed(() => {
  if (entrySameAsMark.value || !props.entry || !props.mark) return null
  const pct = ((props.mark - props.entry) / props.entry) * 100
  const favorable = props.side === 'long' ? pct > 0 : pct < 0
  return { pct, favorable }
})

const marks = computed(() => [
  { key: 'liq', label: 'ล้างพอร์ต', value: props.liq, x: pos(props.liq), tone: 'liq' },
  { key: 'sl', label: 'SL', value: props.sl, x: pos(props.sl), tone: 'stop' },
  ...(entrySameAsMark.value
    ? []
    : [{ key: 'entry', label: 'เข้า', value: props.entry, x: pos(props.entry), tone: 'entry' }]),
  { key: 'tp', label: 'เป้า', value: props.tp, x: pos(props.tp), tone: 'target' },
].filter((m) => m.x !== null))
</script>

<template>
  <div class="ladder">
    <!-- ราคาตอนนี้ — อยู่ในโฟลว์ปกติ ไม่ใช่ label ลอยแบบเดิม จึงไม่ไปทับเนื้อหาข้างบน -->
    <div class="now-line">
      <span class="now-lbl">{{ entrySameAsMark ? 'ราคาตอนนี้ (จุดที่จะเข้า)' : 'ราคาตอนนี้' }}</span>
      <strong class="now-val">{{ fmt(mark) }}</strong>
      <span v-if="moveInfo" class="now-move" :class="moveInfo.favorable ? 'up' : 'down'">
        {{ moveInfo.pct >= 0 ? '+' : '' }}{{ moveInfo.pct.toFixed(2) }}%
        {{ moveInfo.favorable ? 'ทางที่ได้กำไร' : 'ทางที่ขาดทุน' }}
      </span>
    </div>

    <div class="track">
      <div v-if="profitZone" class="zone"
           :style="{ left: profitZone.left + '%', width: profitZone.width + '%' }" />

      <div v-for="m in marks" :key="m.key" class="tick" :class="[m.tone, anchor(m.x)]"
           :style="{ left: m.x + '%' }">
        <span class="tick-line" />
        <span class="tick-label">{{ m.label }}<b>{{ fmt(m.value) }}</b></span>
      </div>

      <div v-if="pos(mark) !== null" class="now-dot" :style="{ left: pos(mark) + '%' }" />
    </div>

    <div class="foot">
      <span :class="danger ? 'down' : 'muted'">
        {{ danger ? '⚠ ' : '' }}ห่างจุดล้างพอร์ต {{ liqDistance?.toFixed(2) }}%
      </span>
      <span class="muted">{{ side === 'long' ? 'ขาขึ้น' : 'ขาลง' }} — ราคาวิ่งผิดทางเท่านี้คือหมดไม้</span>
    </div>
  </div>
</template>

<style scoped>
.ladder { display: flex; flex-direction: column; gap: 14px; }

.now-line { display: flex; align-items: baseline; gap: 8px; flex-wrap: wrap; }
.now-lbl { font-size: 11px; color: var(--ink-3); }
.now-val { font-size: 16px; font-weight: 600; font-variant-numeric: tabular-nums; }
.now-move { font-size: 11px; font-weight: 500; font-variant-numeric: tabular-nums; }

.track {
  position: relative; height: 4px; border-radius: 2px; margin-top: 30px;
  /* tick-label (ด้านล่าง) เป็น position:absolute ยื่นลงมาถึง ~46px จากขอบบนของ track
     (top:-6px ของ .tick + top:20px ของ .tick-label + ความสูงเนื้อหา ~32px)
     ต้องจองพื้นที่ไว้จริงด้วย margin-bottom ไม่งั้น .foot ที่ตามมาจะซ้อนทับ label —
     อย่าลดค่านี้โดยไม่คำนวณใหม่ */
  margin-bottom: 48px;
  background: color-mix(in srgb, var(--line) 80%, transparent);
}
.zone {
  position: absolute; inset-block: 0; border-radius: 2px;
  background: color-mix(in srgb, var(--ink) 22%, transparent);
}

.tick { position: absolute; top: -6px; transform: translateX(-50%); }
.tick.left { transform: translateX(0); }
.tick.right { transform: translateX(-100%); }
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
.tick.left .tick-label { left: 0; transform: translateX(0); align-items: flex-start; }
.tick.right .tick-label { left: auto; right: 0; transform: translateX(0); align-items: flex-end; }
.tick-label b {
  font-size: 12px; letter-spacing: 0; text-transform: none;
  color: var(--ink); font-variant-numeric: tabular-nums; font-weight: 500;
}
.tick.liq .tick-label b { color: #dc2626; }

/* จุดราคาปัจจุบันบนแถบ — ไม่มี label ติดตัว (ราคาอยู่ในหัวข้อด้านบนแล้ว) กันซ้อนกับ tick */
.now-dot {
  position: absolute; top: 50%; transform: translate(-50%, -50%);
  width: 10px; height: 10px; border-radius: 50%;
  background: var(--dark); border: 2px solid var(--paper, #fff); box-sizing: content-box;
}

.foot { display: flex; justify-content: space-between; gap: 12px; font-size: 12px; flex-wrap: wrap; padding-top: 4px; }
</style>
