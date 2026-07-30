<script setup>
/**
 * Sidebar — เพิ่มเมนู Futures เป็นหน้าแยก
 * เมนูที่เป็น "หน้า" (view) จะ emit nav; เมนูที่เป็นจุดในหน้าเดิมยังใช้ anchor
 */
import { Home, BookOpen, Activity, TrendingUp, Bell } from 'lucide-vue-next'

const props = defineProps({ view: { type: String, default: 'spot' } })
const emit = defineEmits(['nav'])

const items = [
  { icon: Home, label: 'ภาพรวม', view: 'spot' },
  { icon: TrendingUp, label: 'Futures (เงินปลอม)', view: 'futures' },
  { icon: BookOpen, label: 'สมุดเทรด', href: '#journal', onlyIn: 'spot' },
  { icon: Activity, label: 'บอท', href: '#bot', onlyIn: 'spot' },
  { icon: Bell, label: 'แจ้งเตือน', href: '#top' },
]

function go(it) {
  if (it.view) emit('nav', it.view)
  else if (it.href) {
    if (it.onlyIn && props.view !== it.onlyIn) emit('nav', it.onlyIn)
    requestAnimationFrame(() => {
      document.querySelector(it.href)?.scrollIntoView({ behavior: 'smooth' })
    })
  }
}

const isActive = (it) => it.view && props.view === it.view
</script>

<template>
  <aside class="side">
    <div class="logo">T</div>
    <button v-for="(it, i) in items" :key="i" :title="it.label"
            :class="['nav', isActive(it) && 'on']" @click="go(it)">
      <component :is="it.icon" :size="17" :stroke-width="1.8" />
    </button>
  </aside>
</template>

<style scoped>
.side {
  width: 64px; display: flex; flex-direction: column; align-items: center; gap: 8px;
  padding: 24px 0; position: sticky; top: 0; height: 100vh;
}
.logo {
  width: 36px; height: 36px; border-radius: 10px; background: var(--dark); color: #fff;
  display: grid; place-items: center; font-weight: 700; font-size: 14px; margin-bottom: 16px;
}
.nav {
  width: 40px; height: 40px; display: grid; place-items: center; border-radius: 10px;
  color: var(--ink-3); background: transparent; border: 1px solid transparent;
  cursor: pointer; transition: background .12s ease, color .12s ease;
}
.nav:hover { background: rgba(255, 255, 255, .6); color: var(--ink); }
.nav.on { background: #fff; border-color: var(--line); color: var(--ink); }
@media (max-width: 900px) {
  .side {
    width: 100%; height: auto; flex-direction: row; justify-content: center;
    padding: 12px 0; gap: 6px;
  }
  .logo { display: none; }
}
</style>
