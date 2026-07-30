<script setup>
import { ref, onMounted } from 'vue'
import { api } from '../api'
import { Bot } from 'lucide-vue-next'

const props = defineProps({ assets: Array })
const states = ref({})   // { symbol: bool }
const busy = ref(null)   // symbol ที่กำลังกดอยู่ (กันดับเบิลคลิก)

onMounted(async () => { states.value = await api.getAuto() })

async function toggle(symbol) {
  busy.value = symbol
  try { states.value = await api.setAuto(symbol, !states.value[symbol]) }
  finally { busy.value = null }
}

const anyOn = () => Object.values(states.value).some(Boolean)
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
          เปิดเฉพาะเหรียญที่มีหลักฐานพอ (แนะนำ: BTCTHB) — เหรียญอื่นยังข้อมูลน้อย ควรปิดไว้ก่อน
        </div>
      </div>
    </div>

    <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:8px">
      <div v-for="s in assets" :key="s"
           style="display:flex;align-items:center;justify-content:space-between;
                  border:1px solid var(--line);border-radius:10px;padding:10px 12px">
        <div style="font-size:12px">
          <span :class="states[s] ? 'up' : 'faint'">●</span> {{ s }}
        </div>
        <button class="btn" :class="{ 'btn--warn': !states[s] }" :disabled="busy === s"
                style="padding:5px 12px;font-size:11px" @click="toggle(s)">
          {{ states[s] ? 'ปิด' : 'เปิด' }}
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.btn--warn { background:#fff; color:var(--ink); border:1px solid var(--line); }
.btn--warn:hover { background:#f5f5f5; }
</style>
