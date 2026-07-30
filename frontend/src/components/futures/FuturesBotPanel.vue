<script setup>
/**
 * ควบคุมบอทอัตโนมัติแยกรายเหรียญ — ใช้ pattern เดียวกับ AutoToggle.vue ฝั่ง spot
 * ให้ผู้ใช้เลือกได้ว่าไว้ใจให้บอทเล่นเหรียญไหนบ้าง ไม่ใช่ all-or-nothing
 */
import { computed } from 'vue'

const props = defineProps({ status: Object, busy: String })
const emit = defineEmits(['toggle'])

const symbols = computed(() => Object.keys(props.status?.symbols || {}))
const onCount = computed(() =>
  symbols.value.filter((s) => props.status.symbols[s].enabled).length)

const ACTION_LABEL = {
  opened: 'เปิดไม้แล้ว', closed: 'ปิดไม้แล้ว', holding: 'ถือไม้อยู่',
  waiting: 'รอสัญญาณ', error: 'ติดปัญหา',
}
const ACTION_TONE = { opened: 'up', closed: 'muted', holding: 'up', waiting: 'muted', error: 'down' }

function secsAgo(iso) {
  if (!iso) return null
  return Math.max(0, Math.round((Date.now() - new Date(iso).getTime()) / 1000))
}
function freshness(iso) {
  const s = secsAgo(iso)
  if (s === null) return 'ยังไม่เคยเช็ค'
  if (s < 90) return `${s}s ที่แล้ว`
  return `ค้าง ${Math.round(s / 60)} นาที`
}
function isStale(iso) {
  const s = secsAgo(iso)
  return s === null || s > 150
}
</script>

<template>
  <div class="card bot">
    <div class="head">
      <div>
        <span class="ttl">บอทอัตโนมัติ</span>
        <p class="muted tiny">
          ใช้สมองเดียวกับบอท spot (MA20/50+regime) · leverage ตายตัว {{ status?.leverage || 5 }}x
          · เสี่ยง {{ status?.risk_pct || 1 }}%/ไม้ · ปิดเองทันทีถ้าสัญญาณดับ
        </p>
      </div>
      <span class="count" :class="{ on: onCount > 0 }">{{ onCount }}/{{ symbols.length }} เปิดอยู่</span>
    </div>

    <p v-if="onCount > 1" class="warn">
      เปิดพร้อมกัน {{ onCount }} เหรียญ = เสี่ยงรวมสูงสุดได้ถึง ~{{ onCount }}% ของพอร์ตต่อรอบ
      ถ้าทุกเหรียญเข้าไม้พร้อมกัน (แต่ละไม้เสี่ยงแยกกัน {{ status?.risk_pct || 1 }}%)
    </p>

    <div class="grid">
      <div v-for="s in symbols" :key="s" class="row" :class="{ on: status.symbols[s].enabled }">
        <div class="row-top">
          <span class="sym">{{ s.replace('/USDT', '') }}</span>
          <button class="toggle" :class="{ on: status.symbols[s].enabled }"
                  :disabled="busy === s" @click="emit('toggle', s)">
            {{ status.symbols[s].enabled ? 'ปิดบอท' : 'เปิดบอท' }}
          </button>
        </div>

        <div v-if="status.symbols[s].enabled" class="status">
          <span :class="isStale(status.symbols[s].checked_at) ? 'down' : 'muted'">
            {{ isStale(status.symbols[s].checked_at) ? '⚠' : '●' }} เช็ค {{ freshness(status.symbols[s].checked_at) }}
          </span>
          <span v-if="status.symbols[s].regime" class="muted"> · {{ status.symbols[s].regime }}</span>
          <div v-if="status.symbols[s].action" class="action" :class="ACTION_TONE[status.symbols[s].action]">
            {{ ACTION_LABEL[status.symbols[s].action] || status.symbols[s].action }}
          </div>
          <div v-if="status.symbols[s].detail" class="detail">{{ status.symbols[s].detail }}</div>
        </div>
        <div v-else class="status muted off">ปิดอยู่ — บอทจะไม่แตะเหรียญนี้เลย</div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.bot { display: flex; flex-direction: column; gap: 14px; }
.head { display: flex; justify-content: space-between; align-items: flex-start; gap: 12px; }
.ttl { font-weight: 500; font-size: 13px; }
.tiny { font-size: 11.5px; margin: 4px 0 0; line-height: 1.55; }
.count {
  flex: 0 0 auto; font-size: 11px; padding: 4px 10px; border-radius: 999px;
  border: 1px solid var(--line); color: var(--ink-3); white-space: nowrap;
}
.count.on { border-color: var(--ink-3); color: var(--ink); font-weight: 500; }
.warn {
  font-size: 11.5px; line-height: 1.55; margin: 0; padding: 8px 10px;
  border-radius: 8px; background: color-mix(in srgb, #dc2626 6%, transparent); color: #dc2626;
}

.grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 8px; }
.row {
  border: 1px solid var(--line); border-radius: 10px; padding: 10px 12px;
  display: flex; flex-direction: column; gap: 8px; transition: border-color .15s ease;
}
.row.on { border-color: var(--ink-3); }
.row-top { display: flex; justify-content: space-between; align-items: center; gap: 8px; }
.sym { font-size: 12.5px; font-weight: 500; }
.toggle {
  border: 1px solid var(--line); background: transparent; color: var(--ink);
  padding: 5px 10px; border-radius: 7px; font: inherit; font-size: 10.5px; cursor: pointer;
  white-space: nowrap;
}
.toggle.on { background: var(--dark); color: #fff; border-color: var(--dark); }
.toggle:disabled { opacity: .5; cursor: not-allowed; }
.status { font-size: 10.5px; line-height: 1.5; }
.status.off { padding-top: 2px; }
.action { font-weight: 500; margin-top: 3px; }
.detail { color: var(--ink-3); margin-top: 2px; }
</style>
