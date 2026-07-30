<script setup>
/**
 * เดิมสวิตช์นี้แค่เขียนไฟล์ ไม่มีทางรู้เลยว่ามีใครเฝ้าดูอยู่จริงไหม (ต้องเปิด
 * copilot.py แยกเทอร์มินัลถึงจะทำงาน) — ตอนนี้ auto-trade รันเป็น background
 * thread ใน uvicorn เองแล้ว จึงโชว์สถานะสดได้ตรงนี้เลย: เช็คล่าสุดเมื่อไหร่,
 * regime, และบอทเพิ่งทำอะไรไป ให้เห็นว่า "มีคนเฝ้าดูอยู่จริง" ไม่ใช่สวิตช์ลอยๆ
 */
import { ref, onMounted, onUnmounted } from 'vue'
import { api } from '../api'
import { Bot } from 'lucide-vue-next'

const props = defineProps({ assets: Array })
const states = ref({})     // { symbol: bool }
const status = ref({})     // { symbol: {checked_at, regime, can_trade, action, detail} }
const busy = ref(null)
let timer = null

const ACTION_LABEL = {
  opened: 'เปิดไม้แล้ว', closed: 'ปิดไม้แล้ว', holding: 'ถือไม้อยู่',
  waiting: 'รอสัญญาณ', error: 'ติดปัญหา',
}

async function refreshStatus() {
  try { status.value = await api.getAutoStatus() } catch { /* เงียบไว้ ไม่ให้กระพริบ */ }
}

onMounted(async () => {
  states.value = await api.getAuto()
  await refreshStatus()
  timer = setInterval(refreshStatus, 8000)
})
onUnmounted(() => clearInterval(timer))

async function toggle(symbol) {
  busy.value = symbol
  try { states.value = await api.setAuto(symbol, !states.value[symbol]) }
  finally { busy.value = null; refreshStatus() }
}

const anyOn = () => Object.values(states.value).some(Boolean)

function secsAgo(iso) {
  if (!iso) return null
  return Math.max(0, Math.round((Date.now() - new Date(iso).getTime()) / 1000))
}
function freshness(iso) {
  const s = secsAgo(iso)
  if (s === null) return 'ยังไม่เคยเช็ค'
  if (s < 90) return `เช็คล่าสุด ${s}s ที่แล้ว`
  return `เช็คล่าสุดนานแล้ว (${Math.round(s / 60)} นาทีก่อน) — ตรวจว่า uvicorn ยังรันอยู่ไหม`
}
function isStale(iso) {
  const s = secsAgo(iso)
  return s === null || s > 150   // เกิน ~2.5 รอบ (poll ทุก 60s) แปลว่าน่าจะค้าง
}
</script>

<template>
  <div class="card" style="display:flex;flex-direction:column;gap:10px">
    <div style="display:flex;align-items:center;gap:10px">
      <div style="width:34px;height:34px;border-radius:10px;display:grid;place-items:center"
           :style="anyOn() ? 'background:var(--dark);color:#fff' : 'background:#f0f0ee;color:var(--ink-3)'">
        <Bot :size="16" />
      </div>
      <div>
        <div style="font-weight:500;font-size:13px">Auto-trade — แยกสวิตช์รายเหรียญ</div>
        <div class="muted" style="font-size:11px">
          ทำงานอยู่ในตัว backend เอง (ไม่ต้องรัน copilot.py แยก) — เปิดเฉพาะเหรียญที่มีหลักฐานพอ
          (แนะนำ: BTCTHB)
        </div>
      </div>
    </div>

    <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:8px">
      <div v-for="s in assets" :key="s" class="row"
           :class="{ on: states[s] }">
        <div style="display:flex;align-items:center;justify-content:space-between">
          <div style="font-size:12px">
            <span :class="states[s] ? 'up' : 'faint'">●</span> {{ s }}
          </div>
          <button class="btn" :class="{ 'btn--warn': !states[s] }" :disabled="busy === s"
                  style="padding:5px 12px;font-size:11px" @click="toggle(s)">
            {{ states[s] ? 'ปิด' : 'เปิด' }}
          </button>
        </div>

        <div v-if="states[s]" class="statusline">
          <template v-if="status[s]">
            <span :class="isStale(status[s].checked_at) ? 'down' : 'up'">
              {{ isStale(status[s].checked_at) ? '⚠' : '●' }} {{ freshness(status[s].checked_at) }}
            </span>
            <span v-if="status[s].regime" class="muted">
              · {{ status[s].regime }} · {{ ACTION_LABEL[status[s].action] || status[s].action }}
            </span>
            <div v-if="status[s].detail" class="muted detail">{{ status[s].detail }}</div>
          </template>
          <span v-else class="muted">รอบแรกกำลังเช็ค — ไม่เกิน 60 วิ</span>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.btn--warn { background:#fff; color:var(--ink); border:1px solid var(--line); }
.btn--warn:hover { background:#f5f5f5; }
.row {
  border:1px solid var(--line); border-radius:10px; padding:10px 12px;
  display:flex; flex-direction:column; gap:6px;
}
.row.on { border-color: var(--ink-3); }
.statusline { font-size:10.5px; line-height:1.5; }
.detail { margin-top:2px; }
</style>
