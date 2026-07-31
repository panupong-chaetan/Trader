<script setup>
import Sidebar from './components/Sidebar.vue'
</script>

<template>
  <div style="display:flex" id="top">
    <Sidebar />
    <div style="flex:1;min-width:0">
      <router-view />
    </div>
  </div>
</template>
