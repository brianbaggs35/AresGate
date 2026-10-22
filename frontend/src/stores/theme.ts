import { defineStore } from 'pinia'
import { ref } from 'vue'

export type ThemePreference = 'light' | 'dark' | 'system'

export const THEME_STORAGE_KEY = 'aresgate.theme'
const PREFERENCES: ReadonlySet<unknown> = new Set<ThemePreference>(['light', 'dark', 'system'])

function isPreference(value: unknown): value is ThemePreference {
  return PREFERENCES.has(value)
}

function readStored(): ThemePreference {
  try {
    const stored = localStorage.getItem(THEME_STORAGE_KEY)
    return isPreference(stored) ? stored : 'system'
  } catch {
    return 'system'
  }
}

export const useThemeStore = defineStore('theme', () => {
  const preference = ref<ThemePreference>(readStored())

  function setPreference(value: ThemePreference) {
    preference.value = value
    try {
      localStorage.setItem(THEME_STORAGE_KEY, value)
    } catch {
      // Storage can be unavailable (private mode); the choice still applies for this visit.
    }
  }

  return { preference, setPreference }
})
