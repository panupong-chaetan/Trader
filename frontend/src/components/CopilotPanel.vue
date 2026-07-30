<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { ShieldCheck, AlertTriangle, CheckCircle2, Circle } from 'lucide-vue-next'

const props = defineProps({ analysis: Object, updatedAt: String })
defineEmits(['open-form'])

// ---- นับถอยหลังแท่ง 1H ถัดไปปิด ----
const countdown = ref('')
let timer
function tick() {
  const now = new Date()
  const next = new Date(now)
  next.setHours(now.getHours() + 1, 0, 0, 0)
  const ms = next - now
  const m = Math.floor(ms / 60000)
  const s = Math.floor((ms % 60000) / 1000)
  countdown.value = `${m}:${String(s).padStart(2, '0')}`
}
onMounted(() => { tick(); timer = setInterval(tick, 1000) })
onUnmounted(() => clearInterval(timer))

// ---- เงื่อนไขที่รอให้เกิด ก่อน regime พลิกเป็น TREND UP ----
// pct = ความคืบหน้า 0-100% (ไม่ใช่แค่ true/false) เห็นแนวโน้มได้แม้ยังไม่ผ่าน
const clamp = (n) => Math.max(0, Math.min(100, n))

const conditions = computed(() => {
  const a = props.analysis
  const gapPts = a.ma_slow - a.ma_fast          // จุดที่ MA20 ยังห่าง MA50 (ยิ่งน้อยยิ่งใกล้)
  const gapPctOfPrice = (gapPts / a.price) * 100 // แปลงเป็น % ของราคา เทียบเป้าได้

  return [
    {
      label: `MA50 หยุดชี้ลง (ตอนนี้ ${a.slope_pct.toFixed(2)}% → ต้อง > -0.05%)`,
      done: a.slope_pct > -0.05,
      // ไล่จาก -1.0% (0%) ถึง -0.05% (100%) — ปรับสเกลตามพฤติกรรมจริงที่เจอ
      pct: clamp((a.slope_pct + 1.0) / (1.0 - 0.05) * 100),
    },
    {
      label: a.bullish
        ? 'MA20 ตัดขึ้นเหนือ MA50 แล้ว'
        : `MA20 ตัดขึ้นเหนือ MA50 (ยังห่าง ${gapPts.toFixed(0)} จุด / ${gapPctOfPrice.toFixed(2)}% ของราคา)`,
      done: a.bullish,
      pct: a.bullish ? 100 : clamp(100 - gapPctOfPrice / 1.5 * 100),  // ห่าง 1.5% ของราคา = 0%
    },
    {
      label: `เส้นถ่างพอ (ตอนนี้ ${a.spread_pct.toFixed(2)}% → ต้อง ≥ 0.25% หลังตัดขึ้น)`,
      done: a.bullish && a.spread_pct >= 0.25,
      pct: a.bullish ? clamp(a.spread_pct / 0.25 * 100) : 0,  // นับได้ก็ต่อเมื่อตัดขึ้นแล้วเท่านั้น
    },
  ]
})
const doneCount = computed(() => conditions.value.filter(c => c.done).length)
const overallPct = computed(() =>
  Math.round(conditions.value.reduce((s, c) => s + c.pct, 0) / 3))
</script>

<template>
  <div class="card" style="display:flex;flex-direction:column;gap:12px">
    <div style="display:flex;align-items:center;justify-content:space-between">
      <div style="display:flex;align-items:center;gap:8px;font-weight:500">
        <ShieldCheck :size="16" /> คำแนะนำตอนนี้
      </div>
      <div class="faint" style="font-size:11px">แท่งถัดไปปิดใน {{ countdown }}</div>
    </div>

    <p v-if="analysis.can_trade" class="muted" style="font-size:13px">
      เงื่อนไขฝั่งซื้อครบ — วาง stop ใต้ก้นล่าสุด/เส้น MA50 · ขนาดไม้คิดจาก risk 1% ·
      จังหวะที่ได้เปรียบคือรอราคาย่อใกล้ MA20 ไม่ไล่ราคาที่ลอยสูง
    </p>
    <p v-else class="muted" style="font-size:13px">
      คำแนะนำที่ดีที่สุดตอนนี้คือ <b style="color:var(--ink)">ไม่เปิดไม้</b> —
      ตั้ง alert ไว้ที่แนวสำคัญแล้วปิดจอ การรอคือ position หนึ่งเหมือนกัน
    </p>

    <!-- สิ่งที่รอให้เกิด -->
    <div v-if="!analysis.can_trade"
         style="border:1px solid var(--line);border-radius:10px;padding:12px 14px">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px">
        <div style="font-size:12px;font-weight:500">
          สิ่งที่รอให้เกิด ({{ doneCount }}/3) ก่อน regime พลิกเป็น TREND UP
        </div>
        <div style="font-size:12px;font-weight:600">{{ overallPct }}%</div>
      </div>
      <div v-for="(c, i) in conditions" :key="i" style="margin-bottom:10px">
        <div style="display:flex;gap:8px;align-items:center;font-size:12px;padding:2px 0"
             :class="c.done ? '' : 'muted'">
          <CheckCircle2 v-if="c.done" :size="14" style="color:var(--up);flex-shrink:0" />
          <Circle v-else :size="14" class="faint" style="flex-shrink:0" />
          {{ c.label }}
        </div>
        <div style="height:4px;background:#eee;border-radius:99px;margin-top:4px;overflow:hidden">
          <div :style="`width:${c.pct}%;height:100%;background:${c.done ? 'var(--up)' : 'var(--ink)'};
                        transition:width .3s`"></div>
        </div>
      </div>
    </div>

    <div style="margin-top:auto;background:#fafafa;border:1px solid var(--line);
                border-radius:10px;padding:14px;font-size:11px" class="muted">
      <b style="color:var(--ink)">ความจริงติดจอ:</b> สถิติจาก backtest 8 ปีบน BTC/USDT — win rate ~46% ·
      แพ้เฉลี่ย ~-6% · ครึ่งหลังแพ้ Buy&amp;Hold → สัญญาณคือแต้มต่อบางๆ ไม่ใช่คำพยากรณ์
      (BTCTHB ยังไม่เคย backtest แยก แต่ราคาผูกกับตลาดโลกเป็นหลัก พฤติกรรมน่าจะใกล้เคียงกัน)
    </div>

    <div class="faint" style="font-size:11px;text-align:right">
      อัปเดตล่าสุด {{ updatedAt || '—' }}
    </div>

    <button class="btn" :class="{ 'btn--warn': !analysis.can_trade }" @click="$emit('open-form')">
      <template v-if="analysis.can_trade">เปิดไม้ (ซื้อ BTC) — ผ่าน checklist ก่อน</template>
      <template v-else>
        <AlertTriangle :size="14" style="vertical-align:-2px;margin-right:6px" />
        เปิดไม้สวนคำแนะนำ (ซื้อ) — ต้องยืนยันเพิ่ม
      </template>
    </button>
  </div>
</template>

<style scoped>
.btn--warn { background: #fff; color: var(--ink); border: 1px solid var(--ink); }
.btn--warn:hover { background: #f5f5f5; }
</style>
