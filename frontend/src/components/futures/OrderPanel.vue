<script setup>
import { ref, computed, watch } from 'vue'
import { fapi } from '../../futuresApi'
import RiskLadder from './RiskLadder.vue'

const props = defineProps({
  symbol: String,
  markPrice: Number,
  available: Number,
  leverage: Number,
  fundingPct: Number,
  locked: Boolean,   // true = มีไม้ของ symbol นี้เปิดอยู่ -> เปลี่ยน leverage ไม่ได้จนกว่าจะปิดไม้
})
const emit = defineEmits(['submitted', 'leverage'])

const side = ref('long')
const lev = ref(props.leverage || 10)
const margin = ref(200)
const tp = ref('')
const sl = ref('')
const reason = ref('')
const busy = ref(false)
const err = ref('')

const LEV_PRESETS = [1, 3, 5, 10, 20, 50, 125]

watch(() => props.leverage, (v) => { if (v) lev.value = v })
watch(() => props.symbol, () => { tp.value = ''; sl.value = ''; err.value = '' })

// คำนวณฝั่ง client ให้ตัวเลขขยับทันทีทุกครั้งที่พิมพ์ (สูตรเดียวกับ backend)
const calc = computed(() => {
  const price = props.markPrice || 0
  const m = Number(margin.value) || 0
  const L = Number(lev.value) || 1
  const notional = m * L
  const qty = price ? notional / price : 0
  const fee = notional * 0.0005 * 2
  const mmr = 0.004
  const liq = side.value === 'long'
    ? (price * qty - m) / (qty * (1 - mmr) || 1)
    : (price * qty + m) / (qty * (1 + mmr) || 1)
  const liqMove = price ? Math.abs(liq - price) / price * 100 : 0
  const slNum = Number(sl.value) || 0
  const tpNum = Number(tp.value) || 0
  const risk = slNum ? Math.abs((side.value === 'long' ? price - slNum : slNum - price)) * qty + fee : 0
  const reward = tpNum ? Math.abs((side.value === 'long' ? tpNum - price : price - tpNum)) * qty - fee : 0
  return {
    notional, qty, fee, liq, liqMove, risk, reward,
    riskPctOfMargin: m ? (risk / m) * 100 : 0,
    rr: risk > 0 && reward > 0 ? reward / risk : 0,
    funding: notional * ((props.fundingPct || 0) / 100) * (side.value === 'long' ? 1 : -1),
  }
})

const marginPctOfAvail = computed(() =>
  props.available ? (Number(margin.value) / props.available) * 100 : 0)

const tooBig = computed(() => Number(margin.value) > (props.available || 0))
const thin = computed(() => calc.value.liqMove < 3)

// ตัวช่วยตั้ง SL/TP เป็น % จากราคาปัจจุบัน
function setSlPct(p) {
  const price = props.markPrice
  sl.value = (side.value === 'long' ? price * (1 - p / 100) : price * (1 + p / 100)).toFixed(2)
}
function setTpPct(p) {
  const price = props.markPrice
  tp.value = (side.value === 'long' ? price * (1 + p / 100) : price * (1 - p / 100)).toFixed(2)
}
function setMarginPct(p) {
  margin.value = Math.floor((props.available || 0) * (p / 100) * 100) / 100
}

async function changeLev(v) {
  if (props.locked) return   // มีไม้เปิดอยู่ — ปุ่ม/สไลเดอร์ถูกล็อกไว้ใน template แล้ว กันเรียกซ้ำ
  lev.value = v
  try { await fapi.leverage(props.symbol, v); emit('leverage', v) } catch (e) { err.value = e.message }
}

async function submit() {
  err.value = ''
  busy.value = true
  try {
    await fapi.order({
      symbol: props.symbol,
      side: side.value,
      margin: Number(margin.value),
      leverage: Number(lev.value),
      tp: Number(tp.value) || null,
      sl: Number(sl.value) || null,
      reason: reason.value,
    })
    tp.value = ''; sl.value = ''; reason.value = ''
    emit('submitted')
  } catch (e) {
    err.value = e.message
  } finally {
    busy.value = false
  }
}

const fmt = (v, d = 2) => (v ?? 0).toLocaleString(undefined, { minimumFractionDigits: d, maximumFractionDigits: d })
</script>

<template>
  <div class="card panel">
    <div class="head">
      <span class="ttl">เปิดไม้</span>
      <span class="muted mono">ว่าง {{ fmt(available) }} USDT</span>
    </div>

    <!-- ฝั่ง -->
    <div class="seg">
      <button :class="['seg-btn', side === 'long' && 'on long']" @click="side = 'long'">
        ซื้อ / Long
      </button>
      <button :class="['seg-btn', side === 'short' && 'on short']" @click="side = 'short'">
        ขาย / Short
      </button>
    </div>

    <!-- leverage -->
    <div class="field">
      <label>
        <span>Leverage</span>
        <b class="mono">{{ lev }}x</b>
      </label>
      <input type="range" min="1" max="125" v-model.number="lev" class="range"
             :disabled="locked" @change="changeLev(lev)" />
      <div class="chips">
        <button v-for="p in LEV_PRESETS" :key="p" :disabled="locked"
                :class="['chip', lev === p && 'on']" @click="changeLev(p)">{{ p }}x</button>
      </div>
      <p v-if="locked" class="lock-note">
        🔒 มีไม้ {{ symbol }} เปิดอยู่ — ปิดไม้ก่อนถึงจะเปลี่ยน leverage ได้
      </p>
    </div>

    <!-- margin -->
    <div class="field">
      <label>
        <span>Margin ที่วาง (USDT)</span>
        <b class="mono">{{ marginPctOfAvail.toFixed(0) }}% ของเงินว่าง</b>
      </label>
      <input class="input mono" type="number" min="0" step="10" v-model="margin" />
      <div class="chips">
        <button v-for="p in [10, 25, 50, 100]" :key="p" class="chip" @click="setMarginPct(p)">
          {{ p }}%
        </button>
      </div>
    </div>

    <!-- TP / SL -->
    <div class="two">
      <div class="field">
        <label><span>Stop loss</span></label>
        <input class="input mono" type="number" step="0.01" v-model="sl" placeholder="ราคา" />
        <div class="chips">
          <button v-for="p in [1, 2, 5]" :key="p" class="chip" @click="setSlPct(p)">−{{ p }}%</button>
        </div>
      </div>
      <div class="field">
        <label><span>เป้ากำไร</span></label>
        <input class="input mono" type="number" step="0.01" v-model="tp" placeholder="ราคา (ไม่บังคับ)" />
        <div class="chips">
          <button v-for="p in [2, 5, 10]" :key="p" class="chip" @click="setTpPct(p)">+{{ p }}%</button>
        </div>
      </div>
    </div>

    <input class="input" v-model="reason" placeholder="เหตุผลเข้าไม้ 1 บรรทัด (ไว้อ่านย้อนหลัง)" />

    <!-- ผลคำนวณก่อนกด -->
    <div class="preview">
      <div class="rows">
        <div><span>ขนาดไม้</span><b class="mono">{{ fmt(calc.notional) }} USDT</b></div>
        <div><span>จำนวน</span><b class="mono">{{ fmt(calc.qty, 6) }}</b></div>
        <div><span>ค่าธรรมเนียมไปกลับ</span><b class="mono">{{ fmt(calc.fee) }}</b></div>
        <div>
          <span>ราคาล้างพอร์ต</span>
          <b class="mono" :class="thin ? 'down' : ''">
            {{ fmt(calc.liq) }} <em>({{ calc.liqMove.toFixed(2) }}%)</em>
          </b>
        </div>
        <div v-if="calc.risk">
          <span>เสี่ยงจริงถ้าโดน SL</span>
          <b class="mono down">−{{ fmt(calc.risk) }} ({{ calc.riskPctOfMargin.toFixed(0) }}% ของ margin)</b>
        </div>
        <div v-if="calc.reward">
          <span>ได้ถ้าถึงเป้า</span>
          <b class="mono up">+{{ fmt(calc.reward) }}</b>
        </div>
        <div v-if="calc.rr"><span>R:R</span><b class="mono">1 : {{ calc.rr.toFixed(2) }}</b></div>
        <div>
          <span>funding รอบหน้า</span>
          <b class="mono">{{ calc.funding >= 0 ? 'จ่าย' : 'ได้รับ' }} {{ fmt(Math.abs(calc.funding), 4) }}</b>
        </div>
      </div>

      <RiskLadder v-if="markPrice" :side="side" :entry="markPrice" :mark="markPrice"
                  :liq="calc.liq" :tp="Number(tp) || null" :sl="Number(sl) || null" />
    </div>

    <p v-if="thin" class="warn">
      {{ lev }}x — ราคาวิ่งผิดทางแค่ {{ calc.liqMove.toFixed(2) }}% ก็หมดไม้
      ที่ leverage ระดับนี้ ความผันผวนปกติของตลาดจะกินไม้ก่อนแผนได้ทำงาน
    </p>
    <p v-else-if="!sl" class="warn soft">
      ไม่ตั้ง stop loss = ปล่อยให้ liquidation เป็น stop loss ของคุณ ซึ่งแพงกว่าเสมอ
    </p>

    <p v-if="err" class="down err">{{ err }}</p>

    <button class="btn submit" :class="side" :disabled="busy || tooBig || !margin" @click="submit">
      {{ busy ? 'กำลังส่งคำสั่ง…' : tooBig ? 'margin เกินเงินที่ว่าง'
        : `${side === 'long' ? 'เปิด Long' : 'เปิด Short'} ${lev}x — เงินปลอม` }}
    </button>
  </div>
</template>

<style scoped>
.panel { display: flex; flex-direction: column; gap: 16px; }
.head { display: flex; justify-content: space-between; align-items: baseline; }
.ttl { font-weight: 500; }
.mono { font-variant-numeric: tabular-nums; }

.seg { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
.seg-btn {
  border: 1px solid var(--line); background: transparent; color: var(--ink-3);
  padding: 11px; border-radius: 10px; font: inherit; font-size: 13px; cursor: pointer;
  transition: all .12s ease;
}
.seg-btn:hover { border-color: var(--ink-3); }
.seg-btn.on.long { background: #059669; border-color: #059669; color: #fff; font-weight: 500; }
.seg-btn.on.short { background: #dc2626; border-color: #dc2626; color: #fff; font-weight: 500; }

.field { display: flex; flex-direction: column; gap: 8px; }
.field label { display: flex; justify-content: space-between; align-items: baseline; font-size: 12px; color: var(--ink-3); }
.field label b { color: var(--ink); font-size: 13px; }
.two { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }

.range { width: 100%; accent-color: #171717; }
.range:disabled { opacity: .4; cursor: not-allowed; }
.chips { display: flex; gap: 6px; flex-wrap: wrap; }
.chip:disabled { opacity: .4; cursor: not-allowed; }
.lock-note { font-size: 11px; color: var(--ink-3); margin: 2px 0 0; }
.chip {
  border: 1px solid var(--line); background: transparent; color: var(--ink-3);
  padding: 4px 9px; border-radius: 7px; font: inherit; font-size: 11px; cursor: pointer;
}
.chip:hover { border-color: var(--ink); color: var(--ink); }
.chip.on { background: var(--dark); border-color: var(--dark); color: #fff; }

.preview {
  border: 1px solid var(--line); border-radius: 10px; padding: 14px;
  display: flex; flex-direction: column; gap: 18px;
}
.rows { display: flex; flex-direction: column; gap: 7px; font-size: 12.5px; }
.rows > div { display: flex; justify-content: space-between; gap: 12px; }
.rows span { color: var(--ink-3); }
.rows em { font-style: normal; color: var(--ink-3); font-size: 11px; }

.warn {
  font-size: 12px; line-height: 1.55; margin: 0; padding: 10px 12px;
  border-radius: 10px; border: 1px solid #dc2626; color: #dc2626;
}
.warn.soft { border-color: var(--line); color: var(--ink-3); }
.err { font-size: 12px; margin: 0; }

.submit { width: 100%; padding: 13px; font-weight: 500; }
.submit.long { background: #059669; }
.submit.short { background: #dc2626; }
.submit:disabled { opacity: .5; cursor: not-allowed; }

@media (max-width: 620px) { .two { grid-template-columns: 1fr; } }
</style>
