import { defineStore } from 'pinia'
import { ref } from 'vue'

import { readChoice, saveChoice } from '@/stores/saved-choice'

export type ThemePreference = 'light' | 'dark' | 'system'

export const THEME_STORAGE_KEY = 'aresgate.theme'
const PREFERENCES: readonly ThemePreference[] = ['light', 'dark', 'system']

export const useThemeStore = defineStore('theme', () => {
  const preference = ref<ThemePreference>(readChoice(THEME_STORAGE_KEY, PREFERENCES) ?? 'system')

  function setPreference(value: ThemePreference) {
    preference.value = value
    saveChoice(THEME_STORAGE_KEY, value)
  }

  return { preference, setPreference }
})
