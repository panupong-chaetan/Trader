import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import PositionsTable from '../components/futures/PositionsTable.vue'
import * as fapiModule from '../futuresApi'

const samplePosition = {
  symbol: 'BTC/USDT', side: 'long', qty: 0.015425, leverage: 10,
  entry_price: 64828.6, mark_price: 64747.72, margin: 100,
  unrealized_pnl: -1.25, roe_pct: -1.25, liq_price: 58580.06,
  liq_distance_pct: 9.5, tp: 71311.07, sl: 63519.19, break_even: 64893.43,
  fees_paid: 0.5, funding_paid: 0.0901, opened_at: '2026-07-30T19:45:46', reason: '',
}

describe('ปิดไม้', () => {
  it('คลิก "ปิดไม้" -> modal เปิด -> คลิกยืนยัน -> ต้องยิง fapi.close จริง', async () => {
    const closeSpy = vi.spyOn(fapiModule.fapi, 'close').mockResolvedValue({ net_pnl: 1, roe_pct: 1 })

    const wrapper = mount(PositionsTable, { props: { positions: [samplePosition] } })

    // หาปุ่ม "ปิดไม้" ตัวที่แถวไม้จริง (ไม่ใช่ปุ่ม "ปิดทั้งหมด")
    const buttons = wrapper.findAll('button')
    const closeBtn = buttons.find(b => b.text().trim() === 'ปิดไม้')
    console.log('พบปุ่ม "ปิดไม้":', !!closeBtn)
    expect(closeBtn).toBeTruthy()

    await closeBtn.trigger('click')
    await wrapper.vm.$nextTick()

    // เช็คว่า dialog เปิดจริงไหม (ผ่าน Teleport ไป body)
    const modalTitle = document.body.querySelector('.modal h3')
    console.log('modal เปิดไหม:', !!modalTitle, modalTitle?.textContent)
    expect(modalTitle).toBeTruthy()

    // คลิกปุ่มยืนยันใน modal
    const confirmBtn = Array.from(document.body.querySelectorAll('.modal .actions button'))
      .find(b => b.textContent.trim() === 'ปิดไม้')
    console.log('พบปุ่มยืนยันใน modal:', !!confirmBtn)
    expect(confirmBtn).toBeTruthy()

    confirmBtn.dispatchEvent(new Event('click', { bubbles: true }))
    await wrapper.vm.$nextTick()
    await new Promise(r => setTimeout(r, 0))   // รอ microtask ของ async onConfirm

    console.log('fapi.close ถูกเรียกไหม:', closeSpy.mock.calls.length, closeSpy.mock.calls)
    expect(closeSpy).toHaveBeenCalledTimes(1)
    expect(closeSpy).toHaveBeenCalledWith('BTC/USDT', 1, '')
  })
})
