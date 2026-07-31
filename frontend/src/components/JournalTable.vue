<script setup>
/**
 * แก้ 2 บั๊กจริงที่เจอ:
 *  1) ราคาที่หาไม่เจอ (fetch พลาด/ยังไม่มาถึง) เคย fallback เป็น pos.entry เอง ->
 *     คำนวณ PnL ออกมาเป็น 0.00% ปลอมๆ ดูเหมือนราคานิ่ง ทั้งที่จริงคือ "ไม่มีข้อมูล"
 *     ตอนนี้แยกให้ชัด: ไม่มีราคา -> โชว์ "ราคาไม่มา" ไม่ใช่ตัวเลขปลอม
 *  2) closeTrade() เคยใช้ prompt() ของเบราว์เซอร์ — ใช้ modal ในแอปแทน (บทเรียนจาก
 *     หน้า futures ที่เจอปัญหาเดียวกัน)
 */
import { computed, ref } from 'vue'
import { api } from '../api'
import ConfirmDialog from './ConfirmDialog.vue'

const props = defineProps({ journal: Object })
const emit = defineEmits(['closed'])
const closing = ref(null)
const dialog = ref(null)   // { symbol, followed }
const liquidity = ref({})  // symbol -> { volume_24h, ok, checking }

const openPositions = computed(() =>
  Object.entries(props.journal.positions || {})
    .filter(([, t]) => t)
    .map(([symbol, t]) => ({ symbol, ...t })))

function priceInfo(pos) {
  const price = props.journal.prices?.[pos.symbol]
  const err = props.journal.price_errors?.[pos.symbol]
  if (err) return { state: 'error', text: `ดึงราคาไม่ได้ (${err})` }
  if (price === undefined) return { state: 'missing', text: 'ราคาไม่มา' }
  const pct = (price / pos.entry - 1) * 100
  return { state: 'ok', pct, text: `${pct >= 0 ? '+' : ''}${pct.toFixed(2)}%` }
}

async function checkLiquidity(symbol) {
  liquidity.value = { ...liquidity.value, [symbol]: { checking: true } }
  try {
    const r = await api.liquidity(symbol)
    liquidity.value = { ...liquidity.value, [symbol]: r }
  } catch (e) {
    liquidity.value = { ...liquidity.value, [symbol]: { error: e.message } }
  }
}

function askClose(symbol, followed) { dialog.value = { symbol, followed } }

async function onConfirm(note) {
  const d = dialog.value
  dialog.value = null
  if (!d) return
  closing.value = d.symbol
  try { await api.closeTrade({ symbol: d.symbol, followed_plan: d.followed, note: note || '' }); emit('closed') }
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

        <div style="font-size:13px;margin-top:4px;display:flex;align-items:center;gap:8px;flex-wrap:wrap">
          <span :class="priceInfo(pos).state === 'ok' ? (priceInfo(pos).pct >= 0 ? 'up' : 'down') : 'down'">
            ตอนนี้ {{ priceInfo(pos).text }}
          </span>

          <button v-if="priceInfo(pos).state !== 'ok'" class="link-btn"
                  @click="checkLiquidity(pos.symbol)">
            เช็คว่าตลาดนิ่งจริงไหม
          </button>
        </div>

        <div v-if="liquidity[pos.symbol]" class="liq-note muted">
          <template v-if="liquidity[pos.symbol].checking">กำลังเช็ค…</template>
          <template v-else-if="liquidity[pos.symbol].error">เช็คไม่ได้: {{ liquidity[pos.symbol].error }}</template>
          <template v-else-if="liquidity[pos.symbol].volume_24h == null">
            เอ็กซ์เชนจ์นี้ไม่คืนข้อมูล volume — เช็คเองได้ที่แอป Binance TH โดยตรง
          </template>
          <template v-else-if="!liquidity[pos.symbol].ok">
            ⚠ ปริมาณเทรด 24 ชม. ของ {{ pos.symbol }} = {{ liquidity[pos.symbol].volume_24h.toLocaleString() }}
            — ต่ำ น่าจะเป็นสาเหตุที่ราคานิ่ง (คนเทรดน้อย ไม่ใช่บั๊ก)
          </template>
          <template v-else>
            ปริมาณเทรด 24 ชม. ปกติ ({{ liquidity[pos.symbol].volume_24h.toLocaleString() }}) —
            ราคานิ่งน่าจะเพราะตลาดเงียบจริงช่วงนี้ ไม่ใช่ปัญหาข้อมูล
          </template>
        </div>
      </div>
      <div style="display:flex;gap:8px">
        <button class="btn" :disabled="closing === pos.symbol" @click="askClose(pos.symbol, true)">ปิดตามแผน</button>
        <button class="btn btn--ghost" :disabled="closing === pos.symbol" @click="askClose(pos.symbol, false)">ปิดนอกแผน</button>
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

    <ConfirmDialog
      :open="!!dialog"
      :title="dialog?.followed ? 'ปิดไม้ตามแผน' : 'ปิดไม้นอกแผน'"
      :message="dialog?.followed
        ? 'ปิดที่ stop/target หรือสัญญาณออกตามที่วางแผนไว้'
        : 'ปิดก่อนแผน — บันทึกเหตุผลไว้จะช่วยตอนย้อนดูวินัยทีหลัง'"
      with-input
      input-type="textarea"
      :input-label="dialog?.followed ? 'โน้ตสั้นๆ (ไม่บังคับ)' : 'เกิดอะไรขึ้น? ทำไมปิดนอกแผน'"
      confirm-label="ปิดไม้"
      @confirm="onConfirm"
      @cancel="dialog = null"
    />
  </div>
</template>

<style scoped>
.link-btn {
  border: none; background: none; padding: 0; font: inherit; font-size: 11px;
  color: var(--ink-3); text-decoration: underline; cursor: pointer;
}
.link-btn:hover { color: var(--ink); }
.liq-note { font-size: 11.5px; line-height: 1.6; margin-top: 6px; width: 100%; }
</style>
