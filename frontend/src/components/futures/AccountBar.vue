<script setup>
const props = defineProps({ account: Object, stats: Object })
const fmt = (v, d = 2) => (v ?? 0).toLocaleString(undefined, { minimumFractionDigits: d, maximumFractionDigits: d })
const sign = (v) => (v > 0 ? 'up' : v < 0 ? 'down' : '')
</script>

<template>
  <div class="bar">
    <div class="cell wide">
      <span class="lbl">มูลค่าพอร์ต (equity)</span>
      <strong class="big mono">{{ fmt(account.equity) }} <em>USDT</em></strong>
      <span class="mono sub" :class="sign(account.total_pnl)">
        {{ account.total_pnl >= 0 ? '+' : '' }}{{ fmt(account.total_pnl) }}
        ({{ account.total_pnl_pct >= 0 ? '+' : '' }}{{ account.total_pnl_pct.toFixed(2) }}%)
        จากทุนตั้งต้น
      </span>
    </div>

    <div class="cell">
      <span class="lbl">กำไรลอยตัว</span>
      <strong class="mono" :class="sign(account.unrealized_pnl)">
        {{ account.unrealized_pnl >= 0 ? '+' : '' }}{{ fmt(account.unrealized_pnl) }}
      </strong>
    </div>

    <div class="cell">
      <span class="lbl">margin ที่ใช้ / ว่าง</span>
      <strong class="mono">{{ fmt(account.margin_used, 0) }} / {{ fmt(account.available_margin, 0) }}</strong>
    </div>

    <div class="cell">
      <span class="lbl">margin ratio</span>
      <strong class="mono" :class="account.margin_ratio_pct > 50 ? 'down' : ''">
        {{ account.margin_ratio_pct.toFixed(2) }}%
      </strong>
    </div>

    <div class="cell">
      <span class="lbl">ค่าธรรมเนียม + funding</span>
      <strong class="mono">−{{ fmt(account.total_fees + Math.max(account.total_funding, 0)) }}</strong>
    </div>

    <div class="cell">
      <span class="lbl">ถูกล้างพอร์ต</span>
      <strong class="mono" :class="account.liquidations ? 'down' : ''">{{ account.liquidations }} ครั้ง</strong>
    </div>

    <div class="cell">
      <span class="lbl">ขาดทุนสูงสุด (DD)</span>
      <strong class="mono">{{ account.max_drawdown_pct.toFixed(2) }}%</strong>
    </div>

    <div class="cell" v-if="stats?.trades">
      <span class="lbl">ชนะ / PF</span>
      <strong class="mono">{{ stats.win_rate_pct.toFixed(0) }}% ·
        {{ Number.isFinite(stats.profit_factor) ? stats.profit_factor.toFixed(2) : '∞' }}</strong>
    </div>
  </div>
</template>

<style scoped>
.bar {
  /* เดิมผสม 1.6fr นำหน้า + repeat(auto-fit, minmax(...)) ในบรรทัดเดียวกัน — สอง
     track-sizing function ต่างชนิดที่ต้อง resolve พร้อมกันแบบนี้ browser คำนวณ
     จำนวนคอลัมน์ auto-fit พลาดได้ง่าย (พังจนเหลือคอลัมน์เดียว ทุกการ์ดเรียงเต็มความ
     กว้างทีละแถว) เปลี่ยนเป็น track เดียวกันหมด แล้วให้การ์งแรกกว้างขึ้นด้วย
     grid-column:span แทน — วิธีมาตรฐานที่ resolve ได้แน่นอนกว่า */
  display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: 1px; background: var(--line); border: 1px solid var(--line);
  border-radius: 14px; overflow: hidden;
}
.cell.wide { grid-column: span 2; }
.cell { background: #fff; padding: 14px 16px; display: flex; flex-direction: column; gap: 4px; }
.lbl { font-size: 10.5px; letter-spacing: .05em; text-transform: uppercase; color: var(--ink-3); }
.cell strong { font-weight: 500; font-size: 14px; }
.mono { font-variant-numeric: tabular-nums; }
.big { font-size: 24px; letter-spacing: -.02em; }
.big em { font-style: normal; font-size: 12px; color: var(--ink-3); font-weight: 400; }
.sub { font-size: 12px; }
@media (max-width: 900px) { .bar { grid-template-columns: 1fr 1fr; } .cell.wide { grid-column: 1 / -1; } }
</style>
