import { defineStore } from 'pinia'
import { ref } from 'vue'

import { readChoice, saveChoice } from '@/stores/saved-choice'

/** How the incidents are laid out: a card each, or a row each in a table that can be sorted. */
export type IncidentLayout = 'cards' | 'table'

export const LAYOUT_STORAGE_KEY = 'aresgate.incident-layout'
export const LAYOUTS: readonly IncidentLayout[] = ['cards', 'table']

/** Whether the table gathers the incidents about one address under that address. */
export type IncidentGrouping = 'none' | 'address'

export const GROUPING_STORAGE_KEY = 'aresgate.incident-grouping'
export const GROUPINGS: readonly IncidentGrouping[] = ['none', 'address']

export const useIncidentLayoutStore = defineStore('incident-layout', () => {
  const layout = ref<IncidentLayout>(readChoice(LAYOUT_STORAGE_KEY, LAYOUTS) ?? 'cards')
  const grouping = ref<IncidentGrouping>(readChoice(GROUPING_STORAGE_KEY, GROUPINGS) ?? 'none')

  function setLayout(value: IncidentLayout) {
    layout.value = value
    saveChoice(LAYOUT_STORAGE_KEY, value)
  }

  function setGrouping(value: IncidentGrouping) {
    grouping.value = value
    saveChoice(GROUPING_STORAGE_KEY, value)
  }

  return { layout, grouping, setLayout, setGrouping }
})
