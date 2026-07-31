<script setup>
const props = defineProps({ trades: Array, stats: Object, bare: Boolean })
const fmt = (v, d = 2) => (v ?? 0).toLocaleString(undefined, { minimumFractionDigits: d, maximumFractionDigits: d })
const sign = (v) => (v > 0 ? 'up' : v < 0 ? 'down' : '')
const LABEL = { manual: 'ปิดมือ', tp: 'ถึงเป้า', sl: 'โดน SL', liquidation: 'ล้างพอร์ต' }
const when = (s) => new Date(s).toLocaleString('th-TH', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' })
</script>

<template>
  <div :class="bare ? '' : 'card'">
    <div v-if="!bare || stats?.trades" class="head">
      <span v-if="!bare" class="ttl">ไม้ที่ปิดแล้ว</span>
      <span v-if="stats?.trades" class="muted small">
        {{ stats.trades }} ไม้ · ชนะ {{ stats.win_rate_pct.toFixed(0) }}% ·
        เฉลี่ยชนะ {{ fmt(stats.avg_win) }} / แพ้ {{ fmt(stats.avg_loss) }} ·
        leverage เฉลี่ย {{ stats.avg_leverage.toFixed(1) }}x ·
        ถือเฉลี่ย {{ stats.avg_hold_hours.toFixed(1) }} ชม.
      </span>
    </div>

    <div v-if="!trades.length" class="empty faint">ยังไม่มีประวัติ — ไม้แรกจะมาโชว์ที่นี่</div>

    <table v-else>
      <thead>
        <tr>
          <th>ปิดเมื่อ</th><th>สินทรัพย์</th><th>ฝั่ง</th><th class="r">lev</th>
          <th class="r">เข้า → ออก</th><th class="r">margin</th><th class="r">PnL</th>
          <th class="r">ROE</th><th>จบแบบ</th><th>โน้ต</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="(t, i) in trades" :key="i" :class="t.trigger === 'liquidation' ? 'liq' : ''">
          <td class="muted nowrap">{{ when(t.closed_at) }}</td>
          <td>{{ t.symbol }}</td>
          <td><span class="tag" :class="t.side">{{ t.side === 'long' ? 'L' : 'S' }}</span></td>
          <td class="r mono">{{ t.leverage }}x</td>
          <td class="r mono nowrap">{{ fmt(t.entry_price) }} → {{ fmt(t.exit_price) }}</td>
          <td class="r mono">{{ fmt(t.margin) }}</td>
          <td class="r mono" :class="sign(t.net_pnl)">
            {{ t.net_pnl >= 0 ? '+' : '' }}{{ fmt(t.net_pnl) }}
          </td>
          <td class="r mono" :class="sign(t.roe_pct)">{{ t.roe_pct.toFixed(1) }}%</td>
          <td :class="t.trigger === 'liquidation' ? 'down' : 'muted'">
            {{ LABEL[t.trigger] || t.trigger }}{{ t.partial ? ' (บางส่วน)' : '' }}
          </td>
          <td class="muted clip">{{ t.note || t.reason || '—' }}</td>
        </tr>
      </tbody>
    </table>

    <div v-if="stats?.by_trigger" class="foot muted">
      จบด้วย: ถึงเป้า {{ stats.by_trigger.tp }} · โดน SL {{ stats.by_trigger.sl }} ·
      ปิดมือ {{ stats.by_trigger.manual }} · ล้างพอร์ต {{ stats.by_trigger.liquidation }}
      <span v-if="stats.long_win_rate_pct !== null"> — long ชนะ {{ stats.long_win_rate_pct.toFixed(0) }}%</span>
      <span v-if="stats.short_win_rate_pct !== null"> · short ชนะ {{ stats.short_win_rate_pct.toFixed(0) }}%</span>
    </div>
  </div>
</template>

<style scoped>
.head { display: flex; justify-content: space-between; align-items: baseline; gap: 16px; margin-bottom: 10px; flex-wrap: wrap; }
.ttl { font-weight: 500; }
.small { font-size: 11.5px; }
.empty { text-align: center; padding: 26px; font-size: 13px; }
table { width: 100%; border-collapse: collapse; font-size: 12.5px; }
th {
  text-align: left; font-weight: 400; font-size: 10px; letter-spacing: .05em;
  text-transform: uppercase; color: var(--ink-3); padding: 8px 10px 8px 0;
  border-bottom: 1px solid var(--line);
}
td { padding: 9px 10px 9px 0; border-bottom: 1px solid var(--line); }
tr.liq td { background: color-mix(in srgb, #dc2626 5%, transparent); }
.r { text-align: right; }
.mono { font-variant-numeric: tabular-nums; }
.nowrap { white-space: nowrap; }
.clip { max-width: 200px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.tag { font-size: 9.5px; font-weight: 600; padding: 2px 5px; border-radius: 4px; color: #fff; }
.tag.long { background: #059669; }
.tag.short { background: #dc2626; }
.foot { font-size: 11.5px; padding-top: 12px; }
</style>
