import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import OrderPanel from '../components/futures/OrderPanel.vue'
import { fapi } from '../futuresApi'

describe('OrderPanel — สลับ symbol ต้องไม่ยิง /leverage อัตโนมัติ', () => {
  beforeEach(() => vi.restoreAllMocks())

  it('เปลี่ยน :symbol และ :leverage prop พร้อมกัน (จำลองสลับ tab) -> ต้องไม่เรียก fapi.leverage', async () => {
    const levSpy = vi.spyOn(fapi, 'leverage').mockResolvedValue({})
    const wrapper = mount(OrderPanel, {
      props: { symbol: 'BTC/USDT', markPrice: 100000, available: 9000, leverage: 10, fundingPct: 0.01 },
    })

    // จำลองสลับไป ETH/USDT: symbol เปลี่ยน, leverage prop เปลี่ยนตาม levOf ของหน้าแม่
    await wrapper.setProps({ symbol: 'ETH/USDT', markPrice: 1900, leverage: 10 })
    await wrapper.vm.$nextTick()
    await new Promise((r) => setTimeout(r, 0))

    console.log('fapi.leverage ถูกเรียกกี่ครั้งตอนสลับ tab:', levSpy.mock.calls.length)
    expect(levSpy).not.toHaveBeenCalled()
  })

  it('ลากสไลเดอร์เปลี่ยน leverage เอง -> ต้องเรียก fapi.leverage ด้วย symbol ปัจจุบัน', async () => {
    const levSpy = vi.spyOn(fapi, 'leverage').mockResolvedValue({})
    const wrapper = mount(OrderPanel, {
      props: { symbol: 'ETH/USDT', markPrice: 1900, available: 9000, leverage: 10, fundingPct: 0.01 },
    })
    const btn20x = wrapper.findAll('button').find((b) => b.text().trim() === '20x')
    await btn20x.trigger('click')
    expect(levSpy).toHaveBeenCalledWith('ETH/USDT', 20)
  })

  it('ถ้า backend ตอบ 400 (เช่นมีไม้เปิดอยู่) ต้องโชว์ error ให้เห็น ไม่ใช่เงียบ', async () => {
    vi.spyOn(fapi, 'leverage').mockRejectedValue(new Error('เปลี่ยน leverage ไม่ได้ตอนถือไม้อยู่ — ปิดไม้ก่อน'))
    const wrapper = mount(OrderPanel, {
      props: { symbol: 'BTC/USDT', markPrice: 100000, available: 9000, leverage: 10, fundingPct: 0.01 },
    })
    const btn20x = wrapper.findAll('button').find((b) => b.text().trim() === '20x')
    await btn20x.trigger('click')
    await new Promise((r) => setTimeout(r, 0))
    expect(wrapper.text()).toContain('ปิดไม้ก่อน')
  })
})
