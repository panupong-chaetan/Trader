<script setup>
import { ref, computed } from 'vue'
import { api } from '../api'

const props = defineProps({ journal: Object })
const emit = defineEmits(['closed'])
const closing = ref(null)

const openPositions = computed(() =>
  Object.entries(props.journal.positions || {})
    .filter(([, t]) => t)
    .map(([symbol, t]) => ({ symbol, ...t })))

async function closeTrade(symbol, followed) {
  const note = prompt(followed ? 'โน้ตสั้นๆ (ถึง stop/target/สัญญาณออก?)' : 'เกิดอะไรขึ้น ทำไมปิดนอกแผน?')
  if (note === null) return
  closing.value = symbol
  try { await api.closeTrade({ symbol, followed_plan: followed, note }); emit('closed') }
  finally { closing.value = null }
}
</script>

<template>
  <div class="card">
    <div style="font-weight:500;margin-bottom:16px">สมุดเทรด</div>

    <div v-for="pos in openPositions" :key="pos.symbol"
      style="border:1px solid var(--line);border-radius:10px;padding:16px;margin-bottom:12px;
             display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:12px">
      <div>
        <div style="font-size:13px"><b>{{ pos.symbol }}</b> เปิดอยู่ · เข้า {{ pos.entry.toLocaleString() }}
          · stop {{ pos.stop.toLocaleString() }}</div>
        <div class="muted" style="font-size:12px">"{{ pos.reason }}"</div>
        <div style="font-size:13px;margin-top:4px"
          :class="(journal.prices?.[pos.symbol] ?? pos.entry) >= pos.entry ? 'up' : 'down'">
          ตอนนี้ {{ (((journal.prices?.[pos.symbol] ?? pos.entry) / pos.entry - 1) * 100).toFixed(2) }}%
        </div>
      </div>
      <div style="display:flex;gap:8px">
        <button class="btn" :disabled="closing === pos.symbol" @click="closeTrade(pos.symbol, true)">ปิดตามแผน</button>
        <button class="btn btn--ghost" :disabled="closing === pos.symbol" @click="closeTrade(pos.symbol, false)">ปิดนอกแผน</button>
      </div>
    </div>

    <table v-if="journal.closed_trades.length">
      <thead><tr><th>เหรียญ</th><th>เวลาเข้า</th><th>เข้า</th><th>ออก</th><th>ผล</th><th>วินัย</th><th>เหตุผล</th></tr></thead>
      <tbody>
        <tr v-for="(t, i) in [...journal.closed_trades].reverse()" :key="i">
          <td>{{ t.symbol || 'BTCTHB' }}</td>
          <td class="muted">{{ t.time_in }}</td>
          <td>{{ t.entry.toLocaleString() }}</td>
          <td>{{ t.exit.toLocaleString() }}</td>
          <td :class="t.pnl_pct >= 0 ? 'up' : 'down'">{{ t.pnl_pct.toFixed(2) }}%</td>
          <td>{{ t.followed_plan ? 'ตามแผน' : 'นอกแผน' }}</td>
          <td class="muted" style="max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">
            {{ t.reason }}</td>
        </tr>
      </tbody>
    </table>
    <div v-else-if="!openPositions.length" class="faint" style="text-align:center;padding:24px">
      ยังไม่มีไม้ — หน้าจอว่างแบบนี้คือหน้าจอของคนที่รอเป็น 😌
    </div>
  </div>
</template>
