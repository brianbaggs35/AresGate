<script setup lang="ts">
import { computed } from 'vue'

import type { LogVolume } from '@/api/logs'
import BarChart from '@/charts/BarChart.vue'
import { formatCount } from '@/format'
import { volumeBars } from '@/logs'

/**
 * How many events there were over time, by severity: the picture of the search before the rows
 * of it. A bar can be picked (a click, Enter, or a second tap) to look at just that stretch of
 * time, which the page does by putting it into the search.
 */
const props = defineProps<{
  volume: LogVolume | null
  /** How many events it is of, and whether there were more that it did not count. */
  matched: number
  capped: boolean
  loading?: boolean
}>()
const emit = defineEmits<{ range: [range: { start: string; end: string }] }>()

const bars = computed(() =>
  props.volume ? volumeBars(props.volume) : { categories: [], series: [], ranges: [] },
)
const caption = computed(() => {
  const events = `${formatCount(props.matched)} ${props.matched === 1 ? 'event' : 'events'}`
  return `${props.capped ? `The newest ${events}` : events} found. Pick a bar to look at just that time.`
})

function pick(index: number) {
  const range = bars.value.ranges[index]
  if (range) emit('range', range)
}
</script>

<template>
  <BarChart
    title="Events over time"
    :caption="caption"
    category-label="Time"
    orientation="vertical"
    stacked
    whole
    selectable
    :height="180"
    :categories="bars.categories"
    :series="bars.series"
    :loading="loading"
    empty-title="No events"
    empty-description="Nothing matches this search."
    data-test="log-volume"
    @select="pick"
  />
</template>
