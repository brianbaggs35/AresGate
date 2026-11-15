<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import { fetchInterfaces } from '@/api/interfaces'
import { useSessionStore } from '@/stores/session'
import { valuesOf, withField } from '@/search'

/**
 * Narrows a searched list by when, by device and by interface, with choices instead of typing.
 * It has no state of its own about the search: it reads the terms (`since:`, `before:`,
 * `device:`, `interface:`) from the text of the search and writes them back into it, so the
 * address of the page, the chips under the box, a saved search and the API all say the same
 * thing, and a search typed by hand shows up in these choices. A time that the choices can't say
 * (an hour of the day, from a bar of a chart) is shown as set in the search, and stays until
 * another choice replaces it. The interface choice is left out while none is named.
 */
const props = defineProps<{ modelValue: string }>()
const emit = defineEmits<{ 'update:modelValue': [text: string] }>()

/** The ways to say "since", in the words the search takes, newest first. */
const PRESETS = [
  { value: '1h', title: 'The last hour' },
  { value: '24h', title: 'The last 24 hours' },
  { value: 'today', title: 'Today' },
  { value: '7d', title: 'The last 7 days' },
  { value: '30d', title: 'The last 30 days' },
] as const
const ANY = 'any'
const CUSTOM = 'custom'
const OTHER = 'other'
const DAY = /^\d{4}-\d{2}-\d{2}$/

const session = useSessionStore()
const names = ref<string[]>([])
const custom = ref(false)

onMounted(async () => {
  try {
    const listing = await session.call(fetchInterfaces)
    names.value = listing.interfaces.map((item) => item.name)
  } catch {
    // Without the interfaces the filter is left out; everything else works as it did.
    names.value = []
  }
})

const since = computed(() => valuesOf(props.modelValue, 'since'))
const before = computed(() => valuesOf(props.modelValue, 'before'))

/** The day after a day written as 2026-11-15, or the day before, in the same words. */
function shifted(day: string, by: number): string {
  const [year, month, date] = day.split('-').map(Number) as [number, number, number]
  return new Date(Date.UTC(year, month - 1, date + by)).toISOString().slice(0, 10)
}

/** Which choice of "when" the search says. */
const range = computed(() => {
  const [from] = since.value
  if (!since.value.length && !before.value.length) return custom.value ? CUSTOM : ANY
  if (since.value.length === 1 && !before.value.length) {
    const preset = PRESETS.find((one) => one.value === from?.toLowerCase())
    if (preset) return preset.value
  }
  const days = [...since.value, ...before.value]
  return days.length <= 2 && days.every((one) => DAY.test(one)) ? CUSTOM : OTHER
})

const choices = computed(() => [
  { value: ANY, title: 'Any time' },
  ...PRESETS,
  { value: CUSTOM, title: 'Choose dates' },
  ...(range.value === OTHER ? [{ value: OTHER, title: 'Set in the search' }] : []),
])

/** The first and last day of a range of dates, the last as it is said to a person: the search
 * ends before the day after it. */
const from = computed(() => (DAY.test(since.value[0] ?? '') ? (since.value[0] as string) : ''))
const until = computed(() =>
  DAY.test(before.value[0] ?? '') ? shifted(before.value[0] as string, -1) : '',
)

const device = computed(() => valuesOf(props.modelValue, 'device')[0] ?? '')
const typed = ref<string | null>(null)

const level = computed(() => valuesOf(props.modelValue, 'interface')[0] ?? null)
/** The interfaces to choose from, and the one the search names even if it is not one of them. */
const levels = computed(() => {
  const named = level.value
  return named && !names.value.some((one) => one.toLowerCase() === named.toLowerCase())
    ? [...names.value, named]
    : names.value
})

function say(text: string) {
  if (text !== props.modelValue) emit('update:modelValue', text)
}

function pickRange(value: string) {
  if (value === OTHER) return
  custom.value = value === CUSTOM
  if (value === CUSTOM) return
  const without = withField(withField(props.modelValue, 'before', null), 'since', null)
  say(value === ANY ? without : withField(without, 'since', value))
}

function pickFrom(day: string | null) {
  custom.value = true
  say(withField(props.modelValue, 'since', day))
}

function pickUntil(day: string | null) {
  custom.value = true
  say(withField(props.modelValue, 'before', day ? shifted(day, 1) : null))
}

function pickDevice() {
  const wanted = typed.value
  typed.value = null
  if (wanted !== null) say(withField(props.modelValue, 'device', wanted))
}

function clearDevice() {
  typed.value = ''
  pickDevice()
}

function pickInterface(value: string | null) {
  say(withField(props.modelValue, 'interface', value))
}
</script>

<template>
  <fieldset class="scope" data-test="scope">
    <legend class="sr-only">Narrow by time, device and interface</legend>
    <v-select
      :model-value="range"
      :items="choices"
      label="When"
      density="comfortable"
      hide-details
      class="scope__field"
      data-test="scope-when"
      @update:model-value="pickRange"
    />
    <template v-if="range === CUSTOM">
      <v-text-field
        :model-value="from"
        type="date"
        label="From"
        density="comfortable"
        hide-details
        class="scope__field scope__date"
        data-test="scope-from"
        @update:model-value="pickFrom"
      />
      <v-text-field
        :model-value="until"
        type="date"
        label="Until"
        density="comfortable"
        hide-details
        class="scope__field scope__date"
        data-test="scope-until"
        @update:model-value="pickUntil"
      />
    </template>
    <v-text-field
      :model-value="typed ?? device"
      label="Device"
      placeholder="Name, maker or hardware address"
      density="comfortable"
      hide-details
      clearable
      autocomplete="off"
      spellcheck="false"
      class="scope__field scope__device"
      data-test="scope-device"
      @update:model-value="typed = $event ?? ''"
      @keydown.enter.prevent="pickDevice"
      @blur="pickDevice"
      @click:clear="clearDevice"
    />
    <v-select
      v-if="levels.length"
      :model-value="level"
      :items="levels"
      label="Interface"
      density="comfortable"
      hide-details
      clearable
      class="scope__field"
      data-test="scope-interface"
      @update:model-value="pickInterface"
    />
  </fieldset>
</template>

<style scoped>
.scope {
  min-width: 0;
  padding: 0;
  margin: 0;
  border: 0;
  display: flex;
  flex-wrap: wrap;
  gap: 0.75rem;
}

.scope__field {
  flex: 1 1 11rem;
  min-width: 0;
}

.scope__date {
  flex-basis: 9rem;
}

.scope__device {
  flex-basis: 14rem;
}
</style>
