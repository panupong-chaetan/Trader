/**
 * ทดสอบบั๊ก "กราฟหายเมื่อสลับ tab เหรียญ" — mock lightweight-charts เพราะ jsdom
 * ไม่มี canvas 2D context จริง แล้วเช็คแค่ตรรกะ reactive: สลับ symbol แล้ว
 * ต้องยิง fapi.candles ด้วย symbol ใหม่ และต้อง setData ด้วยข้อมูลจริงที่ได้กลับมา
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'

const setDataSpy = vi.fn()
const removePriceLineSpy = vi.fn()
const createPriceLineSpy = vi.fn(() => ({}))
const fitContentSpy = vi.fn()
const mockSeries = { setData: setDataSpy, removePriceLine: removePriceLineSpy, createPriceLine: createPriceLineSpy }
const mockChart = {
  addCandlestickSeries: vi.fn(() => mockSeries),
  remove: vi.fn(),
  timeScale: vi.fn(() => ({ fitContent: fitContentSpy })),
}

vi.mock('lightweight-charts', () => ({
  createChart: vi.fn(() => mockChart),
  CandlestickSeries: undefined,   // จำลอง v4 (ไม่มี export นี้จริง)
  LineStyle: { Dashed: 2, Solid: 0 },
}))

import FuturesChart from '../components/futures/FuturesChart.vue'
import { fapi } from '../futuresApi'

describe('FuturesChart — สลับ symbol', () => {
  beforeEach(() => { vi.restoreAllMocks(); fitContentSpy.mockClear(); setDataSpy.mockClear() })

  it('mount ครั้งแรกต้องโหลดแท่งเทียน + fitContent โดยไม่มี error', async () => {
    const candlesSpy = vi.spyOn(fapi, 'candles')
      .mockResolvedValue({ candles: [{ time: 1, open: 1, high: 2, low: 0, close: 1.5 }] })
    const wrapper = mount(FuturesChart, { props: { symbol: 'BTC/USDT', position: null, markPrice: 100 } })
    await new Promise((r) => setTimeout(r, 0))
    expect(candlesSpy).toHaveBeenCalledWith('BTC/USDT', '15m', 300)
    expect(fitContentSpy).toHaveBeenCalled()
    expect(wrapper.text()).not.toContain('โหลดกราฟไม่ได้')
  })

  it('เปลี่ยน prop symbol -> ต้องยิง fapi.candles ด้วย symbol ใหม่, setData, และ fitContent ใหม่ (กันกราฟค้างมุมมองเดิม)', async () => {
    const candlesSpy = vi.spyOn(fapi, 'candles')
      .mockResolvedValueOnce({ candles: [{ time: 1, close: 100 }] })       // BTC
      .mockResolvedValueOnce({ candles: [{ time: 2, close: 2000 }] })      // ETH

    const wrapper = mount(FuturesChart, { props: { symbol: 'BTC/USDT', position: null, markPrice: 100 } })
    await new Promise((r) => setTimeout(r, 0))
    setDataSpy.mockClear(); fitContentSpy.mockClear()

    await wrapper.setProps({ symbol: 'ETH/USDT' })
    await wrapper.vm.$nextTick()
    await new Promise((r) => setTimeout(r, 0))

    expect(candlesSpy).toHaveBeenLastCalledWith('ETH/USDT', '15m', 300)
    expect(setDataSpy).toHaveBeenCalledWith([{ time: 2, close: 2000 }])
    expect(fitContentSpy).toHaveBeenCalled()
    expect(wrapper.text()).not.toContain('โหลดกราฟไม่ได้')
  })

  it('ถ้า fapi.candles error ต้องโชว์ error ไม่ใช่เงียบเป็นกราฟว่าง', async () => {
    vi.spyOn(fapi, 'candles').mockRejectedValue(new Error('เชื่อมต่อ Binance ไม่ได้'))
    const wrapper = mount(FuturesChart, { props: { symbol: 'BTC/USDT', position: null, markPrice: 100 } })
    await new Promise((r) => setTimeout(r, 0))
    expect(wrapper.text()).toContain('เชื่อมต่อ Binance ไม่ได้')
  })

  it('ถ้า API สำเร็จแต่คืน candles ว่างเปล่า -> ต้องโชว์ empty-state ไม่ใช่เงียบเป็นกราฟว่าง', async () => {
    vi.spyOn(fapi, 'candles').mockResolvedValue({ candles: [] })
    const wrapper = mount(FuturesChart, { props: { symbol: 'BTC/USDT', position: null, markPrice: 100 } })
    await new Promise((r) => setTimeout(r, 0))
    expect(wrapper.text()).toContain('ยังไม่มีแท่งเทียนกลับมา')
  })
})
