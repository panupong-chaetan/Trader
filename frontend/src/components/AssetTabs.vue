<script setup>
defineProps({ assets: Array, modelValue: String })
defineEmits(['update:modelValue'])
</script>

<template>
  <div style="display:inline-flex;gap:2px;background:#f0f0ee;border-radius:10px;padding:3px;flex-wrap:wrap">
    <button v-for="s in assets" :key="s" class="pill" style="border-radius:8px;white-space:nowrap"
      :class="{ active: modelValue === s }"
      @click="$emit('update:modelValue', s)">{{ s }}</button>
  </div>
</template>
