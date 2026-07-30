<script setup>
import { ref, computed } from 'vue'
import { api } from '../api'

const props = defineProps({ analysis: Object, journal: Object, symbol: String })
const emit = defineEmits(['done'])

const stop = ref(null)
const target = ref(0)
const riskPct = ref(1)
const reason = ref('')
const checks = ref([false, false, false, false])
const busy = ref(false)
const err = ref('')

const checklist = computed(() => [
  props.analysis.can_trade
    ? 'Regime เป็น TREND UP จริง (ดู banner บนสุด)'
    : 'ฉันรู้ว่าระบบไม่แนะนำช่วงนี้ และยอมรับว่านี่คือไม้สวนคำแนะนำ (จะถูกจดไว้)',
  'Stop ผูกกับโครงสร้างราคา ไม่ใช่เลขลอยๆ',
  'Risk ไม่เกิน 1-2% ของพอร์ต',
  'เหตุผลไม่ใช่ "รอมานานแล้ว" หรือ "อยากลอง"',
])
const ready = computed(() =>
  checks.value.every(Boolean) && stop.value > 0 && reason.value.trim().length >= 4)

async function submit() {
  busy.value = true; err.value = ''
  try {
    let finalReason = reason.value.trim()
    if (!props.analysis.can_trade)
      finalReason = `[สวนคำแนะนำ ${props.analysis.regime}] ${finalReason}`
    await api.openTrade({ symbol: props.symbol, stop: +stop.value, target: +target.value || 0,
                          risk_pct: +riskPct.value, reason: finalReason })
    emit('done')
  } catch (e) { err.value = e.message } finally { busy.value = false }
}
</script>

<template>
  <div class="card" :style="!analysis.can_trade ? 'border-color:var(--ink)' : ''">
    <div style="font-weight:500;margin-bottom:4px">เปิดไม้ — เช็คให้ครบก่อนถึงกดได้</div>
    <div v-if="!analysis.can_trade" class="muted" style="font-size:12px;margin-bottom:12px">
      โหมดสวนคำแนะนำ: เปิดได้ แต่ไม้นี้จะถูกแท็ก [สวนคำแนะนำ] ในสมุดถาวร —
      ปลายเดือนสถิติจะเฉลยเองว่าการฝ่าไฟแดงของคุณกำไรหรือเผาเงิน
    </div>
    <div v-else style="margin-bottom:12px"></div>

    <div style="display:grid;grid-template-columns:1fr 1fr;gap:24px" class="form-grid">
      <div style="display:flex;flex-direction:column;gap:10px">
        <input class="input" disabled :value="`จุดเข้า ~ ${analysis.live_price.toLocaleString()} (ราคาตลาด)`" />
        <input class="input" v-model="stop" type="number" placeholder="Stop loss (บังคับ)" />
        <input class="input" v-model="target" type="number" placeholder="เป้ากำไร (0 = ไม่ตั้ง)" />
        <input class="input" v-model="riskPct" type="number" step="0.5" max="2" placeholder="เสี่ยงกี่ % (สูงสุด 2)" />
        <input class="input" v-model="reason" placeholder="เหตุผลเข้าไม้ 1 บรรทัด" />
      </div>
      <div style="display:flex;flex-direction:column;gap:8px">
        <label v-for="(c, i) in checklist" :key="i"
          style="display:flex;gap:12px;align-items:center;border:1px solid var(--line);
                 border-radius:10px;padding:12px 16px;cursor:pointer;font-size:13px">
          <input type="checkbox" v-model="checks[i]" style="accent-color:#171717;width:16px;height:16px" />
          {{ c }}
        </label>
        <div v-if="err" class="down" style="font-size:12px">{{ err }}</div>
        <button class="btn" :disabled="!ready || busy" @click="submit">
          {{ busy ? 'กำลังบันทึก…' : 'ยืนยันเปิดไม้ (เงินปลอม)' }}</button>
      </div>
    </div>
  </div>
</template>

<style scoped>
@media (max-width: 900px) { .form-grid { grid-template-columns: 1fr !important; } }
</style>
