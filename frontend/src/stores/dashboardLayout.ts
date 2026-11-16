import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

import { errorMessage } from '@/api/client'
import {
  fetchLayout,
  resetLayout,
  saveLayout,
  type PlaceOut,
  type PresetOut,
} from '@/api/dashboardLayout'
import { DEFAULT_PLACES, placesFrom, type Place } from '@/dashboardLayout'
import { useSessionStore } from '@/stores/session'

/**
 * How the signed-in account has laid out its dashboard. Until it is read, and when it can't be,
 * the dashboard is the default one, so the page never waits for it. A change is shown at once and
 * saved; if saving fails the layout goes back to what it was and the store says why.
 */
export const useDashboardLayoutStore = defineStore('dashboardLayout', () => {
  const session = useSessionStore()

  const places = ref<Place[]>(DEFAULT_PLACES.map((place) => ({ ...place })))
  const preset = ref<string | null>('overview')
  const presets = ref<PresetOut[]>([])
  const error = ref<string | null>(null)
  const saving = ref(false)

  const out = (list: readonly Place[]): PlaceOut[] =>
    list.map(({ id, size, hidden }) => ({ id, size, hidden }))

  async function load() {
    try {
      const layout = await session.call(fetchLayout)
      places.value = placesFrom(layout.widgets)
      preset.value = layout.preset
      presets.value = layout.presets
      error.value = null
    } catch (loadError) {
      error.value = errorMessage(loadError)
    }
  }

  /** Shows the layout and saves it, and takes the old one back if that fails. `from` is the
   * preset it was made from, or null for a layout of the account's own making. */
  async function save(next: readonly Place[], from: string | null = null) {
    const before = { places: places.value, preset: preset.value }
    places.value = next.map((place) => ({ ...place }))
    preset.value = from
    saving.value = true
    try {
      await session.change((token) =>
        saveLayout({ preset: from, widgets: out(places.value) }, token),
      )
      error.value = null
    } catch (saveError) {
      places.value = before.places
      preset.value = before.preset
      error.value = errorMessage(saveError)
    } finally {
      saving.value = false
    }
  }

  /** Starts over from a preset. */
  async function apply(key: string) {
    const found = presets.value.find((item) => item.key === key)
    if (found) await save(placesFrom(found.widgets), found.key)
  }

  /** Puts the first preset back. */
  async function reset() {
    saving.value = true
    try {
      await session.change((token) => resetLayout(token))
      places.value = DEFAULT_PLACES.map((place) => ({ ...place }))
      preset.value = 'overview'
      error.value = null
    } catch (resetError) {
      error.value = errorMessage(resetError)
    } finally {
      saving.value = false
    }
  }

  const shown = computed(() => places.value.filter(({ hidden }) => !hidden))

  return { places, preset, presets, error, saving, shown, load, save, apply, reset }
})
