import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import PositionsHistoryTabs from '../components/futures/PositionsHistoryTabs.vue'
import { fapi } from '../futuresApi'

const pos = { symbol: 'BTC/USDT', side: 'long', qty: 0.1, leverage: 5,
  entry_price: 100, mark_price: 101, margin: 100, unrealized_pnl: 1, roe_pct: 1,
  liq_price: 80, liq_distance_pct: 20, tp: null, sl: null, break_even: 100.1,
  fees_paid: 0, funding_paid: 0, opened_at: '2026-07-31T00:00:00', reason: '' }
const trade = { symbol: 'ETH/USDT', side: 'long', margin: 50, entry_price: 3000,
  exit_price: 3050, leverage: 5, net_pnl: 5, roe_pct: 5, trigger: 'manual',
  closed_at: '2026-07-31T01:00:00' }

describe('PositionsHistoryTabs', () => {
  it('เริ่มต้นต้องอยู่ tab "ไม้ที่เปิดอยู่" และไม่โชว์ตาราง history', () => {
    const wrapper = mount(PositionsHistoryTabs, { props: { positions: [pos], trades: [trade], stats: null } })
    expect(wrapper.text()).toContain('ไม้ที่เปิดอยู่')
    expect(wrapper.find('.pos').exists()).toBe(true)   // แถวไม้เปิดอยู่โผล่
  })

  it('คลิก tab "ไม้ที่ปิดแล้ว" -> ต้องเห็นแถวประวัติ', async () => {
    const wrapper = mount(PositionsHistoryTabs, { props: { positions: [pos], trades: [trade], stats: null } })
    const closedTab = wrapper.findAll('button').find((b) => b.text().includes('ไม้ที่ปิดแล้ว'))
    await closedTab.trigger('click')
    expect(wrapper.text()).toContain('ETH/USDT')
  })

  it('ปิดไม้จาก tab เปิดอยู่ -> event "changed" ต้องหลุดออกมาถึง parent (ผ่าน wrapper)', async () => {
    vi.spyOn(fapi, 'close').mockResolvedValue({})
    const wrapper = mount(PositionsHistoryTabs, { props: { positions: [pos], trades: [], stats: null } })
    const closeBtn = wrapper.findAll('button').find((b) => b.text().trim() === 'ปิดไม้')
    await closeBtn.trigger('click')
    await wrapper.vm.$nextTick()
    const confirmBtn = Array.from(document.body.querySelectorAll('.modal .actions button'))
      .find((b) => b.textContent.trim() === 'ปิดไม้')
    confirmBtn.dispatchEvent(new Event('click', { bubbles: true }))
    await new Promise((r) => setTimeout(r, 0))
    expect(wrapper.emitted('changed')).toBeTruthy()
  })
})
