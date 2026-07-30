<script setup>
/**
 * แทนที่ prompt()/confirm() ของเบราว์เซอร์ทั้งหมด — dialog แบบเนทีฟเหล่านี้
 * ถูกบล็อกหรือค้างได้ในหลาย context (sandbox iframe, บาง extension) ทำให้
 * โค้ดทั้งฟังก์ชันหยุดรอเงียบๆ โดยไม่มี error ใดๆ ให้เห็น — ดูเหมือนปุ่มกดไม่ได้
 */
import { ref, watch, nextTick } from 'vue'

const props = defineProps({
  open: Boolean,
  title: String,
  message: String,
  tone: { type: String, default: 'default' },   // 'default' | 'danger'
  confirmLabel: { type: String, default: 'ยืนยัน' },
  cancelLabel: { type: String, default: 'ยกเลิก' },
  withInput: Boolean,
  inputLabel: String,
  inputPlaceholder: String,
  inputType: { type: String, default: 'text' },
  inputDefault: [String, Number],
})
const emit = defineEmits(['confirm', 'cancel'])

const value = ref('')
const inputEl = ref(null)

watch(() => props.open, async (v) => {
  if (v) {
    value.value = props.inputDefault ?? ''
    await nextTick()
    inputEl.value?.focus()
  }
})

function ok() {
  emit('confirm', props.withInput ? value.value : true)
}
function cancel() {
  emit('cancel')
}
function onKey(e) {
  if (e.key === 'Escape') cancel()
  if (e.key === 'Enter' && (!props.withInput || props.inputType !== 'textarea')) ok()
}
</script>

<template>
  <Teleport to="body">
    <div v-if="open" class="backdrop" @click.self="cancel" @keydown="onKey">
      <div class="modal" :class="tone" role="dialog" aria-modal="true">
        <h3>{{ title }}</h3>
        <p v-if="message" class="msg">{{ message }}</p>

        <div v-if="withInput" class="field">
          <label v-if="inputLabel">{{ inputLabel }}</label>
          <textarea v-if="inputType === 'textarea'" ref="inputEl" v-model="value"
                    :placeholder="inputPlaceholder" rows="3" @keydown.stop />
          <input v-else ref="inputEl" v-model="value" :type="inputType"
                 :placeholder="inputPlaceholder" @keydown.stop @keydown.enter="ok" />
        </div>

        <div class="actions">
          <button class="btn ghost" @click="cancel">{{ cancelLabel }}</button>
          <button class="btn solid" :class="tone" @click="ok">{{ confirmLabel }}</button>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.backdrop {
  position: fixed; inset: 0; background: rgba(23, 23, 23, 0.35);
  display: grid; place-items: center; z-index: 1000; padding: 20px;
  backdrop-filter: blur(2px);
}
.modal {
  background: #fff; border-radius: 16px; padding: 22px; width: min(420px, 100%);
  display: flex; flex-direction: column; gap: 12px;
  box-shadow: 0 20px 50px rgba(0, 0, 0, 0.18);
}
h3 { font-size: 15px; font-weight: 500; margin: 0; }
.msg { font-size: 13px; color: var(--ink-3); line-height: 1.6; margin: 0; }
.field { display: flex; flex-direction: column; gap: 6px; }
.field label { font-size: 11px; color: var(--ink-3); }
.field input, .field textarea {
  border: 1px solid var(--line); border-radius: 10px; padding: 10px 12px;
  font: inherit; font-size: 13px; resize: vertical;
}
.field input:focus, .field textarea:focus { outline: none; border-color: var(--ink-3); }
.actions { display: flex; justify-content: flex-end; gap: 8px; margin-top: 4px; }
.btn {
  border: 0; cursor: pointer; font: inherit; font-weight: 500; font-size: 13px;
  padding: 9px 16px; border-radius: 10px; transition: opacity .12s ease;
}
.btn.ghost { background: transparent; color: var(--ink-3); }
.btn.ghost:hover { color: var(--ink); }
.btn.solid { background: var(--dark); color: #fff; }
.btn.solid.danger { background: #dc2626; }
.btn.solid:hover { opacity: .88; }
</style>
