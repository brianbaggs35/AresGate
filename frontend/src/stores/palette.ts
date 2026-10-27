import { defineStore } from 'pinia'
import { ref } from 'vue'

/** Whether the command palette is open, so the keyboard shortcut and the app bar's button can
 * both open it. */
export const usePaletteStore = defineStore('palette', () => {
  const open = ref(false)

  function toggle() {
    open.value = !open.value
  }

  return { open, toggle }
})
