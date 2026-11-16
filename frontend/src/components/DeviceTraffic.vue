<script setup lang="ts">
import { computed } from 'vue'

import { fetchAddressTrends } from '@/api/trends'
import TimeSeriesChart from '@/charts/TimeSeriesChart.vue'
import { useTrend } from '@/trends'

/**
 * The connections to a device and from it, in each hour of the last week, as two lines: the page
 * lists them, and this is how they have gone, so a device that started talking yesterday is seen
 * to have started.
 */
const props = defineProps<{ address: string }>()

const HOURS = 24 * 7

const { trend, loading } = useTrend(
  () => props.address,
  () => fetchAddressTrends([props.address], 'hour', HOURS),
)

const item = computed(() => trend.value?.items[props.address] ?? null)
const times = computed(() => (trend.value?.times ?? []).map(Date.parse))
const series = computed(() =>
  item.value
    ? [
        { id: 'incoming', label: 'Connections in', values: item.value.incoming },
        { id: 'outgoing', label: 'Connections out', values: item.value.outgoing },
      ]
    : [],
)
</script>

<template>
  <section
    v-if="trend || loading"
    class="section"
    aria-labelledby="traffic-title"
    data-test="device-traffic"
  >
    <h2 id="traffic-title" class="text-title-large">Connections over the week</h2>
    <v-card class="pa-4 pa-sm-5">
      <TimeSeriesChart
        title="Connections in and out"
        caption="Events the device was in, per hour, last 7 days."
        :times="times"
        :series="series"
        :loading="loading"
        empty-title="No connections"
        empty-description="Nothing was reported to or from it in the last week."
        data-test="device-traffic-chart"
      />
    </v-card>
  </section>
</template>
