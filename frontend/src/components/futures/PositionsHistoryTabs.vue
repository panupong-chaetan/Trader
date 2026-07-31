<script setup>
/**
 * รวม "ไม้ที่เปิดอยู่" กับ "ไม้ที่ปิดแล้ว" เป็น tab เดียว — เดิมเป็น 2 การ์ดแยกกัน
 * ตอนไม่มีประวัติ การ์ด "ไม้ที่ปิดแล้ว" ว่างเปล่าแต่ยังกินพื้นที่แนวตั้งไปฟรีๆ
 * ไม่แตะ logic ข้างใน PositionsTable/HistoryTable เลย (ทั้งคู่มีเทสต์ครอบอยู่แล้ว)
 * แค่สลับว่าจะโชว์ตัวไหน
 */
import { ref } from 'vue'
import PositionsTable from './PositionsTable.vue'
import HistoryTable from './HistoryTable.vue'

const props = defineProps({ positions: Array, trades: Array, stats: Object })
defineEmits(['changed'])

const tab = ref('open')   // 'open' | 'closed'
</script>

<template>
  <div class="card panel">
    <div class="tabbar">
      <button :class="['tab-btn', tab === 'open' && 'on']" @click="tab = 'open'">
        ไม้ที่เปิดอยู่ <em v-if="positions.length">({{ positions.length }})</em>
      </button>
      <button :class="['tab-btn', tab === 'closed' && 'on']" @click="tab = 'closed'">
        ไม้ที่ปิดแล้ว <em v-if="trades.length">({{ trades.length }})</em>
      </button>
    </div>

    <PositionsTable v-show="tab === 'open'" bare :positions="positions" @changed="$emit('changed')" />
    <HistoryTable v-show="tab === 'closed'" bare :trades="trades" :stats="stats" />
  </div>
</template>

<style scoped>
.panel { padding-bottom: 8px; }
.tabbar { display: flex; gap: 4px; margin-bottom: 4px; }
.tab-btn {
  border: none; background: transparent; color: var(--ink-3); cursor: pointer;
  font: inherit; font-size: 13px; padding: 8px 4px; margin-right: 18px;
  border-bottom: 2px solid transparent;
}
.tab-btn em { font-style: normal; color: var(--ink-3); font-weight: 400; }
.tab-btn.on { color: var(--ink); font-weight: 500; border-bottom-color: var(--ink); }
</style>
