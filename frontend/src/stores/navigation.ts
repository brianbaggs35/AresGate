import { defineStore } from 'pinia'
import { ref } from 'vue'

import { readChoice, saveChoice } from '@/stores/saved-choice'

/** How wide the menu is on a tablet or computer: labelled, or just icons (a rail). */
export type MenuWidth = 'full' | 'rail'

export const MENU_STORAGE_KEY = 'aresgate.menu'
const WIDTHS: readonly MenuWidth[] = ['full', 'rail']

export const useNavigationStore = defineStore('navigation', () => {
  /** What the person chose, or null while the screen's size decides. */
  const width = ref<MenuWidth | null>(readChoice(MENU_STORAGE_KEY, WIDTHS))

  function setWidth(value: MenuWidth) {
    width.value = value
    saveChoice(MENU_STORAGE_KEY, value)
  }

  return { width, setWidth }
})
