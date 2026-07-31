import { createRouter, createWebHistory } from 'vue-router'
import SpotView from './components/SpotView.vue'
import FuturesView from './components/futures/FuturesView.vue'

const routes = [
  { path: '/', redirect: '/spot' },
  { path: '/spot', name: 'spot', component: SpotView },
  { path: '/futures', name: 'futures', component: FuturesView },
]

export default createRouter({
  history: createWebHistory(),
  routes,
  // เมนูฝั่งซ้ายบางปุ่มลิงก์ไปยัง section ในหน้า spot (#journal, #bot) — ให้ router
  // เลื่อนจอไปที่ anchor นั้นให้เองหลัง route เปลี่ยน แม้จะสลับมาจากหน้า futures
  scrollBehavior(to) {
    if (to.hash) return { el: to.hash, behavior: 'smooth' }
    return { top: 0 }
  },
})
