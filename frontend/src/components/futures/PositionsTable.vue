<script setup>
import { ref } from 'vue'
import { fapi } from '../../futuresApi'
import RiskLadder from './RiskLadder.vue'
import ConfirmDialog from './ConfirmDialog.vue'

const props = defineProps({ positions: Array })
const emit = defineEmits(['changed', 'focus-symbol'])

const busy = ref('')
const err = ref('')
const expanded = ref(null)
const dialog = ref(null)   // { kind:'close'|'closeAll', symbol?, portion? }

function askClose(symbol, portion) {
  dialog.value = { kind: 'close', symbol, portion }
}
function askCloseAll() {
  dialog.value = { kind: 'closeAll' }
}
function cancelDialog() {
  dialog.value = null
}

async function onConfirm(inputValue) {
  const d = dialog.value
  dialog.value = null
  if (!d) return
  err.value = ''
  if (d.kind === 'close') {
    busy.value = d.symbol + d.portion
    try {
      await fapi.close(d.symbol, d.portion, inputValue || '')
      emit('changed')
    } catch (e) { err.value = e.message } finally { busy.value = '' }
  } else if (d.kind === 'closeAll') {
    busy.value = 'all'
    try { await fapi.closeAll(); emit('changed') }
    catch (e) { err.value = e.message } finally { busy.value = '' }
  }
}

const fmt = (v, d = 2) => (v ?? 0).toLocaleString(undefined, { minimumFractionDigits: d, maximumFractionDigits: d })
const sign = (v) => (v > 0 ? 'up' : v < 0 ? 'down' : '')
</script>

<template>
  <div class="card">
    <div class="head">
      <span class="ttl">ไม้ที่เปิดอยู่ <em v-if="positions.length">({{ positions.length }})</em></span>
      <button v-if="positions.length > 1" class="mini" :disabled="!!busy" @click="askCloseAll">
        ปิดทั้งหมด</button>
    </div>

    <p v-if="err" class="down msg">{{ err }}</p>

    <div v-if="!positions.length" class="empty faint">
      ยังไม่มีไม้ — การไม่มีไม้คือสถานะที่ถูกต้องเกือบตลอดเวลา
    </div>

    <div v-for="p in positions" :key="p.symbol" class="pos">
      <div class="row" @click="expanded = expanded === p.symbol ? null : p.symbol">
        <div class="c sym">
          <span class="tag" :class="p.side">{{ p.side === 'long' ? 'LONG' : 'SHORT' }}</span>
          <div>
            <b>{{ p.symbol }}</b>
            <span class="muted lev">{{ p.leverage }}x</span>
          </div>
        </div>
        <div class="c"><span class="k">จำนวน</span><span class="mono">{{ fmt(p.qty, 6) }}</span></div>
        <div class="c"><span class="k">เข้า → ตอนนี้</span>
          <span class="mono">{{ fmt(p.entry_price) }} → {{ fmt(p.mark_price) }}</span></div>
        <div class="c"><span class="k">margin</span><span class="mono">{{ fmt(p.margin) }}</span></div>
        <div class="c"><span class="k">PnL ลอยตัว</span>
          <span class="mono" :class="sign(p.unrealized_pnl)">
            {{ p.unrealized_pnl >= 0 ? '+' : '' }}{{ fmt(p.unrealized_pnl) }}
          </span></div>
        <div class="c"><span class="k">ROE</span>
          <span class="mono" :class="sign(p.roe_pct)">
            {{ p.roe_pct >= 0 ? '+' : '' }}{{ p.roe_pct.toFixed(2) }}%
          </span></div>
        <div class="c"><span class="k">ล้างพอร์ตที่</span>
          <span class="mono" :class="p.liq_distance_pct < 5 ? 'down' : ''">
            {{ fmt(p.liq_price) }} <em>({{ p.liq_distance_pct.toFixed(1) }}%)</em>
          </span></div>
        <div class="c acts">
          <button class="mini" :disabled="busy" @click.stop="askClose(p.symbol, 0.5)">ปิดครึ่ง</button>
          <button class="mini solid" :disabled="busy" @click.stop="askClose(p.symbol, 1)">ปิดไม้</button>
        </div>
      </div>

      <div v-if="expanded === p.symbol" class="detail">
        <RiskLadder :side="p.side" :entry="p.entry_price" :mark="p.mark_price"
                    :liq="p.liq_price" :tp="p.tp" :sl="p.sl" />
        <div class="meta">
          <span>คุ้มทุนที่ <b class="mono">{{ fmt(p.break_even) }}</b></span>
          <span>SL <b class="mono">{{ p.sl ? fmt(p.sl) : 'ไม่ตั้ง' }}</b></span>
          <span>เป้า <b class="mono">{{ p.tp ? fmt(p.tp) : 'ไม่ตั้ง' }}</b></span>
          <span>ค่าธรรมเนียมจ่ายแล้ว <b class="mono">{{ fmt(p.fees_paid, 4) }}</b></span>
          <span>funding <b class="mono">{{ fmt(p.funding_paid, 4) }}</b></span>
          <span>เปิดเมื่อ <b class="mono">{{ new Date(p.opened_at).toLocaleString('th-TH') }}</b></span>
        </div>
        <p v-if="p.reason" class="muted reason">เหตุผลที่เข้า: {{ p.reason }}</p>
      </div>
    </div>

    <ConfirmDialog
      :open="!!dialog"
      :title="dialog?.kind === 'closeAll' ? `ปิดทุกไม้ (${positions.length} ไม้)?` : 'ปิดไม้นี้'"
      :message="dialog?.kind === 'closeAll'
        ? 'ปิดทุกไม้ที่ราคาตลาดตอนนี้ทันที — ย้อนกลับไม่ได้'
        : (dialog?.portion === 1 ? 'ปิดทั้งไม้ที่ราคาตลาดตอนนี้' : 'ปิดครึ่งหนึ่งของไม้ที่ราคาตลาดตอนนี้')"
      :tone="dialog?.kind === 'closeAll' ? 'danger' : 'default'"
      :with-input="dialog?.kind === 'close' && dialog?.portion === 1"
      input-label="เหตุผลที่ปิด (ไม่บังคับ — บันทึกไว้อ่านย้อนหลัง)"
      input-placeholder="เช่น ถึงเป้าที่วางแผนไว้ / เปลี่ยนใจเพราะ..."
      input-type="textarea"
      confirm-label="ปิดไม้"
      @confirm="onConfirm"
      @cancel="cancelDialog"
    />
  </div>
</template>

<style scoped>
.head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
.ttl { font-weight: 500; }
.ttl em { font-style: normal; color: var(--ink-3); font-weight: 400; }
.empty { text-align: center; padding: 28px 8px; font-size: 13px; }
.msg { font-size: 12px; margin: 0 0 8px; }
.pos { border-top: 1px solid var(--line); }
.row {
  display: grid; grid-template-columns: 1.4fr .9fr 1.5fr .8fr 1fr .8fr 1.3fr auto;
  gap: 12px; align-items: center; padding: 12px 0; cursor: pointer;
}
.c { display: flex; flex-direction: column; gap: 3px; min-width: 0; font-size: 13px; }
.k { font-size: 10px; letter-spacing: .04em; text-transform: uppercase; color: var(--ink-3); }
.mono { font-variant-numeric: tabular-nums; }
.mono em { font-style: normal; font-size: 11px; color: var(--ink-3); }
.sym { flex-direction: row; align-items: center; gap: 10px; }
.sym b { font-weight: 500; }
.lev { font-size: 11px; margin-left: 6px; }
.tag {
  font-size: 9.5px; font-weight: 600; letter-spacing: .06em; padding: 3px 6px;
  border-radius: 5px; color: #fff;
}
.tag.long { background: #059669; }
.tag.short { background: #dc2626; }
.acts { flex-direction: row; gap: 6px; }
.mini {
  border: 1px solid var(--line); background: transparent; color: var(--ink);
  padding: 6px 10px; border-radius: 8px; font: inherit; font-size: 11.5px; cursor: pointer;
}
.mini:hover { border-color: var(--ink); }
.mini.solid { background: var(--dark); color: #fff; border-color: var(--dark); }
.mini:disabled { opacity: .45; cursor: not-allowed; }
.detail {
  padding: 6px 2px 18px; display: flex; flex-direction: column; gap: 20px;
}
.meta { display: flex; flex-wrap: wrap; gap: 6px 22px; font-size: 12px; color: var(--ink-3); }
.meta b { color: var(--ink); font-weight: 500; }
.reason { font-size: 12px; margin: 0; }
@media (max-width: 1100px) {
  .row { grid-template-columns: 1fr 1fr 1fr; }
  .acts { grid-column: 1 / -1; }
}
</style>
