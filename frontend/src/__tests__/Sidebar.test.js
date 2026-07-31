/**
 * เทสต์เมนูใหม่ — ต้องเป็น URL จริง (router-link) ไม่ใช่แค่ JS state ลอยๆ แบบเดิม
 * และปุ่มยุบเมนูต้องทำงานจริง + จำสถานะไว้
 */
import { describe, it, expect, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { createRouter, createWebHistory } from 'vue-router'
import Sidebar from '../components/Sidebar.vue'

const SpotStub = { template: '<div>spot page</div>' }
const FuturesStub = { template: '<div>futures page</div>' }

async function makeRouter(initial = '/spot') {
  const router = createRouter({
    history: createWebHistory(),
    routes: [
      { path: '/spot', component: SpotStub },
      { path: '/futures', component: FuturesStub },
    ],
  })
  router.push(initial)
  await router.isReady()
  return router
}

describe('Sidebar — router จริง', () => {
  beforeEach(() => localStorage.clear())

  it('เมนู Futures ต้องเป็น <a href="/futures"> จริง ไม่ใช่ปุ่มลอยๆ', async () => {
    const router = await makeRouter()
    const wrapper = mount(Sidebar, { global: { plugins: [router] } })
    const futuresLink = wrapper.findAll('a').find((a) => a.attributes('href') === '/futures')
    expect(futuresLink).toBeTruthy()
  })

  it('อยู่หน้า /futures -> เมนู Futures ต้องไฮไลต์ active', async () => {
    const router = await makeRouter('/futures')
    const wrapper = mount(Sidebar, { global: { plugins: [router] } })
    const futuresLink = wrapper.findAll('a').find((a) => a.attributes('href') === '/futures')
    expect(futuresLink.classes()).toContain('on')
  })

  it('คลิกเมนู Futures -> router ต้องเปลี่ยนไปหน้า /futures จริง', async () => {
    const router = await makeRouter('/spot')
    const wrapper = mount(Sidebar, { global: { plugins: [router] } })
    const futuresLink = wrapper.findAll('a').find((a) => a.attributes('href') === '/futures')
    await futuresLink.trigger('click')
    await new Promise((r) => setTimeout(r, 0))
    expect(router.currentRoute.value.path).toBe('/futures')
  })

  it('ปุ่มยุบเมนู -> label หายไป เหลือแค่ไอคอน และจำสถานะไว้ใน localStorage', async () => {
    const router = await makeRouter()
    const wrapper = mount(Sidebar, { global: { plugins: [router] } })
    expect(wrapper.text()).toContain('Futures')   // label โชว์อยู่ตอนแรก

    const collapseBtn = wrapper.findAll('button').find((b) => b.text().includes('ยุบเมนู'))
    await collapseBtn.trigger('click')

    expect(wrapper.find('.side').classes()).toContain('collapsed')
    expect(wrapper.text()).not.toContain('Futures')   // label หายเมื่อยุบ
    expect(localStorage.getItem('sidebar-collapsed')).toBe('1')
  })

  it('เปิดหน้าใหม่ตอน localStorage มี sidebar-collapsed=1 -> ต้องเริ่มแบบยุบไว้แล้ว', async () => {
    localStorage.setItem('sidebar-collapsed', '1')
    const router = await makeRouter()
    const wrapper = mount(Sidebar, { global: { plugins: [router] } })
    expect(wrapper.find('.side').classes()).toContain('collapsed')
  })

  it('เมนูลัด "สมุดเทรด" ต้องลิงก์ไป /spot#journal (ข้ามหน้าได้แม้กำลังอยู่ futures)', async () => {
    const router = await makeRouter('/futures')
    const wrapper = mount(Sidebar, { global: { plugins: [router] } })
    const journalLink = wrapper.findAll('a').find((a) => a.attributes('href') === '/spot#journal')
    expect(journalLink).toBeTruthy()
  })
})
