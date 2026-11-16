import { defineStore } from 'pinia'
import { ref } from 'vue'

import { readChoice, saveChoice } from '@/stores/saved-choice'

/** Whether charts are textured as well as colored. It is always on in forced-colors mode and in
 * print; this is the owner's choice for the screen, remembered in this browser. */
export type Patterns = 'on' | 'off'

export const PATTERNS_STORAGE_KEY = 'aresgate.patterns'
export const PATTERN_CHOICES: readonly Patterns[] = ['on', 'off']

export const usePatternsStore = defineStore('patterns', () => {
  const preference = ref<Patterns>(readChoice(PATTERNS_STORAGE_KEY, PATTERN_CHOICES) ?? 'off')

  function setPreference(value: Patterns) {
    preference.value = value
    saveChoice(PATTERNS_STORAGE_KEY, value)
  }

  return { preference, setPreference }
})
