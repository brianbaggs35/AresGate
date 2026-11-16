import { defineStore } from 'pinia'
import { ref } from 'vue'

import { readChoice, saveChoice } from '@/stores/saved-choice'

/** How much of a list fits on the screen: roomy, or close together for someone who reads many. */
export type Density = 'comfortable' | 'compact'

export const DENSITY_STORAGE_KEY = 'aresgate.density'
export const DENSITIES: readonly Density[] = ['comfortable', 'compact']

export const useDensityStore = defineStore('density', () => {
  const preference = ref<Density>(readChoice(DENSITY_STORAGE_KEY, DENSITIES) ?? 'comfortable')

  function setPreference(value: Density) {
    preference.value = value
    saveChoice(DENSITY_STORAGE_KEY, value)
  }

  return { preference, setPreference }
})
