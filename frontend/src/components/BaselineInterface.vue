<script setup lang="ts">
import { computed } from 'vue'

import type { BaselineHour, BaselineSeries } from '@/api/baselines'
import BarChart from '@/charts/BarChart.vue'
import { formatBytes, formatCount, formatDateTime } from '@/format'

/**
 * What is usual for one interface in one direction: the traffic in each hour of the day (UTC) the
 * weeks of counters taught, as bars, with the hours lately that carried far more than that.
 */
const props = defineProps<{ series: BaselineSeries }>()

const DIRECTIONS = { received: 'Received', sent: 'Sent' } as const

const title = computed(() => {
  const place = props.series.name ?? props.series.interface ?? 'An interface'
  return `${place}: ${DIRECTIONS[props.series.direction].toLowerCase()}`
})
const categories = computed(() =>
  props.series.hours.map((hour) => hour.hour.toString().padStart(2, '0')),
)
const bars = computed(() => [
  {
    id: 'usual',
    label: 'Usual',
    values: props.series.hours.map((hour) => hour.median),
  },
])
const caption = computed(
  () =>
    `The middle of what passed in each hour of the day, UTC, learned from up to ${formatCount(props.series.samples)} hours.`,
)
const busiest = computed(() =>
  props.series.hours.reduce(
    (most, hour) => (hour.median > most.median ? hour : most),
    props.series.hours[0] as BaselineHour,
  ),
)
const quietest = computed(() =>
  props.series.hours.reduce(
    (least, hour) => (hour.median < least.median ? hour : least),
    props.series.hours[0] as BaselineHour,
  ),
)
const hour = (value: number) => `${value.toString().padStart(2, '0')}:00`
</script>

<template>
  <v-card class="pa-4 pa-sm-5 baseline" data-test="baseline-interface">
    <BarChart
      :title="title"
      :caption="caption"
      category-label="Hour (UTC)"
      orientation="vertical"
      :height="200"
      :categories="categories"
      :series="bars"
      :format="formatBytes"
      data-test="baseline-chart"
    />
    <p class="text-body-medium text-medium-emphasis mt-3" data-test="baseline-extremes">
      Busiest at {{ hour(busiest.hour) }} with {{ formatBytes(busiest.median) }}, quietest at
      {{ hour(quietest.hour) }} with {{ formatBytes(quietest.median) }}.
    </p>
    <section v-if="series.deviations.length" class="mt-3" aria-label="Hours far above usual">
      <h3 class="text-title-small">Far above usual lately</h3>
      <ul class="baseline__list" data-test="baseline-deviations">
        <li v-for="item in series.deviations" :key="item.at" class="text-body-medium">
          <time :datetime="item.at">{{ formatDateTime(item.at) }}</time>:
          {{ formatBytes(item.observed) }} against {{ formatBytes(item.usual) }} usual.
        </li>
      </ul>
    </section>
    <p v-else class="text-body-medium text-medium-emphasis" data-test="baseline-calm">
      Nothing was far above usual in the last month.
    </p>
  </v-card>
</template>

<style scoped>
.baseline__list {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
  margin: 0.25rem 0 0;
  padding-inline-start: 1.25rem;
}
</style>
