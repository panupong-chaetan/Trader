<script setup>
const props = defineProps({ journal: Object, stats: Object, bot: Object })
const fmt = (n) => n.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })
</script>

<template>
  <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:16px" class="cards">
    <div class="card">
      <div class="muted" style="font-size:13px">พอร์ตจำลอง — คุณ</div>
      <div class="num-lg">{{ fmt(journal.equity) }} <span class="faint" style="font-size:14px;font-weight:400">THB</span></div>
      <div class="muted" style="font-size:12px;margin-top:4px">
        {{ stats?.trades || 0 }} ไม้ ·
        วินัย {{ stats?.trades ? stats.discipline.toFixed(0) + '%' : '—' }} ·
        expectancy {{ stats?.trades ? stats.expectancy.toFixed(2) + '%' : '—' }}
      </div>
    </div>
    <div class="card">
      <div class="muted" style="font-size:13px">พอร์ตจำลอง — บอท (1H)</div>
      <template v-if="bot.running || bot.equity">
        <div class="num-lg">{{ fmt(bot.equity) }} <span class="faint" style="font-size:14px;font-weight:400">USDT</span></div>
        <div class="muted" style="font-size:12px;margin-top:4px">
          <span :class="bot.running ? 'up' : 'down'">●</span>
          {{ bot.running ? 'กำลังรัน' : 'หยุดอยู่' }} ·
          {{ bot.holding ? 'ถือ BTC' : 'ถือเงินสด' }} · {{ bot.trades }} ไม้
        </div>
      </template>
      <div v-else class="faint" style="margin-top:8px">ยังไม่พบ state บอท</div>
    </div>
    <div class="card card--dark">
      <div style="opacity:.5;font-size:13px">เกณฑ์ผ่านด่านเงินจริง</div>
      <div style="font-size:20px;font-weight:600;margin-top:4px">
        {{ stats?.trades || 0 }} / 20 ไม้</div>
      <div style="opacity:.5;font-size:12px;margin-top:4px">
        + วินัย ≥90% + expectancy บวก</div>
    </div>
  </div>
</template>

<style scoped>
@media (max-width: 900px) { .cards { grid-template-columns: 1fr !important; } }
</style>
