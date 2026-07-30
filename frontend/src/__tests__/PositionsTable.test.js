/**
 * เทสต์กันบั๊กซ้ำ: "ปิดไม้ไม่ได้"
 * ============================================================
 * สาเหตุจริงที่เจอ (31/7/69): `const busy = ref('')` ผูกกับ `:disabled="busy"`
 * ตรงๆ โดยไม่แปลงเป็น boolean — empty string ไม่ใช่ false แต่ Vue ก็ยังเซ็ต
 * attribute `disabled=""` ลงจริงเพราะเป็น boolean attribute (แค่มี attribute
 * ก็ disabled แล้วไม่ว่าค่าจะเป็นอะไร) ปุ่มเลย disabled ตั้งแต่โหลดหน้า ทั้งที่
 * ไม่มีอะไร busy อยู่เลย มองจากโค้ดเฉยๆ ไม่เห็นบั๊ก ต้อง mount จริงถึงจับได้
 *
 * เทสต์นี้เช็คจนถึงจุดที่ยิง network call จริง ไม่ใช่แค่เช็คว่า handler ผูกอยู่
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import PositionsTable from '../components/futures/PositionsTable.vue'
import { fapi } from '../futuresApi'

const pos = (overrides = {}) => ({
  symbol: 'BTC/USDT', side: 'long', qty: 0.015425, leverage: 10,
  entry_price: 64828.6, mark_price: 64747.72, margin: 100,
  unrealized_pnl: -1.25, roe_pct: -1.25, liq_price: 58580.06,
  liq_distance_pct: 9.5, tp: 71311.07, sl: 63519.19, break_even: 64893.43,
  fees_paid: 0.5, funding_paid: 0.0901, opened_at: '2026-07-30T19:45:46', reason: '',
  ...overrides,
})

function clickAndConfirm(wrapper, buttonText, confirmText) {
  const btn = wrapper.findAll('button').find((b) => b.text().trim() === buttonText)
  return btn.trigger('click').then(async () => {
    await wrapper.vm.$nextTick()
    const confirmBtn = Array.from(document.body.querySelectorAll('.modal .actions button'))
      .find((b) => b.textContent.trim() === confirmText)
    confirmBtn.dispatchEvent(new Event('click', { bubbles: true }))
    await wrapper.vm.$nextTick()
    await new Promise((r) => setTimeout(r, 0))
  })
}

describe('PositionsTable — ปิดไม้', () => {
  beforeEach(() => vi.restoreAllMocks())

  it('ปุ่ม "ปิดไม้" ต้องไม่ถูก disabled ตั้งแต่แรกโหลด', () => {
    const wrapper = mount(PositionsTable, { props: { positions: [pos()] } })
    const btn = wrapper.findAll('button').find((b) => b.text().trim() === 'ปิดไม้')
    expect(btn.attributes('disabled')).toBeUndefined()
  })

  it('ปิดทั้งไม้: คลิก -> modal -> ยืนยัน -> ยิง fapi.close(symbol, 1, note)', async () => {
    const spy = vi.spyOn(fapi, 'close').mockResolvedValue({})
    const wrapper = mount(PositionsTable, { props: { positions: [pos()] } })
    await clickAndConfirm(wrapper, 'ปิดไม้', 'ปิดไม้')
    expect(spy).toHaveBeenCalledWith('BTC/USDT', 1, '')
  })

  it('ปิดครึ่ง: คลิก -> modal (ไม่มีช่องกรอกเหตุผล) -> ยืนยัน -> ยิง fapi.close(symbol, 0.5, ...)', async () => {
    const spy = vi.spyOn(fapi, 'close').mockResolvedValue({})
    const wrapper = mount(PositionsTable, { props: { positions: [pos()] } })
    await clickAndConfirm(wrapper, 'ปิดครึ่ง', 'ปิดไม้')
    expect(spy).toHaveBeenCalledWith('BTC/USDT', 0.5, '')
  })

  it('ปิดทั้งหมด: โผล่เฉพาะตอนมีมากกว่า 1 ไม้ + ยิง fapi.closeAll()', async () => {
    const spy = vi.spyOn(fapi, 'closeAll').mockResolvedValue({ closed: [], failed: [] })
    const wrapper = mount(PositionsTable, {
      props: { positions: [pos(), pos({ symbol: 'ETH/USDT' })] },
    })
    await clickAndConfirm(wrapper, 'ปิดทั้งหมด', 'ปิดไม้')
    expect(spy).toHaveBeenCalledTimes(1)
  })

  it('emit "changed" หลังปิดสำเร็จ เพื่อให้หน้าหลัก refresh พอร์ต', async () => {
    vi.spyOn(fapi, 'close').mockResolvedValue({})
    const wrapper = mount(PositionsTable, { props: { positions: [pos()] } })
    await clickAndConfirm(wrapper, 'ปิดไม้', 'ปิดไม้')
    expect(wrapper.emitted('changed')).toBeTruthy()
  })

  it('ถ้า API error ต้องโชว์ error ไม่ใช่เงียบหาย', async () => {
    vi.spyOn(fapi, 'close').mockRejectedValue(new Error('margin ไม่พอ'))
    const wrapper = mount(PositionsTable, { props: { positions: [pos()] } })
    await clickAndConfirm(wrapper, 'ปิดไม้', 'ปิดไม้')
    expect(wrapper.text()).toContain('margin ไม่พอ')
  })
})
