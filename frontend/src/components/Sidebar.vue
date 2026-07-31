<script setup>
/**
 * เมนูฝั่งซ้าย — เดิมเป็นแค่ไอคอนลอยๆ ไม่มี URL จริง (กด "futures" แล้ว URL ยังเป็น
 * localhost:5173/ เหมือนเดิม, refresh หน้าแล้วเด้งกลับ spot ทุกที, แชร์ลิงก์ตรงๆ
 * ไปหน้า futures ไม่ได้เลย) ตอนนี้ใช้ vue-router จริง มี URL ต่อหน้า (/spot, /futures)
 * ปุ่มเมนูมีทั้งไอคอน+ชื่อ กดยุบเหลือแค่ไอคอนได้ จำสถานะไว้ข้าม session
 */
import { ref, computed } from 'vue'
import { useRoute } from 'vue-router'
import { Home, TrendingUp, BookOpen, Activity, Bell, PanelLeftClose, PanelLeftOpen } from 'lucide-vue-next'

const route = useRoute()

const items = [
  { icon: Home, label: 'ภาพรวม', to: '/spot' },
  { icon: TrendingUp, label: 'Futures', to: '/futures' },
  { icon: BookOpen, label: 'สมุดเทรด', to: '/spot', hash: '#journal' },
  { icon: Activity, label: 'บอท', to: '/spot', hash: '#bot' },
  { icon: Bell, label: 'แจ้งเตือน', to: '/spot', hash: '#top' },
]

const collapsed = ref(localStorage.getItem('sidebar-collapsed') === '1')
function toggle() {
  collapsed.value = !collapsed.value
  localStorage.setItem('sidebar-collapsed', collapsed.value ? '1' : '0')
}

// ไฮไลต์เฉพาะเมนูหลัก (ภาพรวม/Futures) ตาม path จริง — ปุ่มลัดไป anchor
// (สมุดเทรด/บอท/แจ้งเตือน) ไม่ไฮไลต์เพราะเป็นแค่ทางลัดเลื่อนจอ ไม่ใช่ "หน้า" ของตัวเอง
const isMainRoute = (item) => !item.hash
const isActive = (item) => isMainRoute(item) && route.path === item.to
</script>

<template>
  <aside class="side" :class="{ collapsed }">
    <div class="logo">T</div>

    <nav class="nav-list">
      <router-link v-for="(it, i) in items" :key="i" :to="{ path: it.to, hash: it.hash }"
                   class="nav-item" :class="{ on: isActive(it) }" :title="collapsed ? it.label : ''">
        <component :is="it.icon" :size="17" :stroke-width="1.8" class="nav-icon" />
        <span v-if="!collapsed" class="nav-label">{{ it.label }}</span>
      </router-link>
    </nav>

    <button class="collapse-btn" :title="collapsed ? 'ขยายเมนู' : 'ยุบเมนู'" @click="toggle">
      <component :is="collapsed ? PanelLeftOpen : PanelLeftClose" :size="16" :stroke-width="1.8" />
      <span v-if="!collapsed">ยุบเมนู</span>
    </button>
  </aside>
</template>

<style scoped>
.side {
  width: 190px; display: flex; flex-direction: column; gap: 4px;
  padding: 20px 12px; position: sticky; top: 0; height: 100vh;
  border-right: 1px solid var(--line); background: var(--bg);
  transition: width .18s ease;
}
.side.collapsed { width: 64px; align-items: center; }

.logo {
  width: 36px; height: 36px; border-radius: 10px; background: var(--dark); color: #fff;
  display: grid; place-items: center; font-weight: 700; font-size: 14px; margin-bottom: 12px;
  flex: 0 0 auto;
}
.side.collapsed .logo { margin-left: 0; }

.nav-list { display: flex; flex-direction: column; gap: 2px; width: 100%; flex: 1; }

.nav-item {
  display: flex; align-items: center; gap: 11px; width: 100%;
  padding: 9px 10px; border-radius: 9px; text-decoration: none;
  color: var(--ink-3); font-size: 13px; white-space: nowrap; overflow: hidden;
  transition: background .12s ease, color .12s ease;
}
.side.collapsed .nav-item { width: 40px; height: 40px; padding: 0; justify-content: center; }
.nav-item:hover { background: rgba(0, 0, 0, .04); color: var(--ink); }
.nav-item.on { background: #fff; border: 1px solid var(--line); color: var(--ink); font-weight: 500; }
.side.collapsed .nav-item.on { border-color: var(--line); }
.nav-icon { flex: 0 0 auto; }
.nav-label { overflow: hidden; text-overflow: ellipsis; }

.collapse-btn {
  display: flex; align-items: center; gap: 8px; width: 100%;
  border: 1px solid transparent; background: transparent; color: var(--ink-3);
  padding: 8px 10px; border-radius: 9px; font: inherit; font-size: 12px; cursor: pointer;
  margin-top: auto;
}
.side.collapsed .collapse-btn { width: 40px; height: 40px; padding: 0; justify-content: center; }
.collapse-btn:hover { background: rgba(0, 0, 0, .04); color: var(--ink); }

@media (max-width: 900px) {
  .side { width: 100% !important; height: auto; flex-direction: row; align-items: center;
          padding: 10px 12px; position: static; border-right: 0; border-bottom: 1px solid var(--line); }
  .logo, .collapse-btn { display: none; }
  .nav-list { flex-direction: row; justify-content: center; gap: 6px; }
  .nav-item { width: 40px; height: 40px; padding: 0; justify-content: center; }
  .nav-label { display: none; }
}
</style>
