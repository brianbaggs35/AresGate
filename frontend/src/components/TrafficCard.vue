<script setup lang="ts">
import { computed, ref } from 'vue'

import type { InterfaceTraffic } from '@/api/dashboard'
import TimeSeriesChart from '@/charts/TimeSeriesChart.vue'
import type { ChartMark } from '@/charts/types'
import { formatBitrate } from '@/format'

/**
 * How fast data went through one of the firewall's interfaces, received and sent. The busiest
 * interface is shown first; with more than one, a menu picks another. Incidents that began in
 * the window are flagged above it (`marks`), so a spike can be read against what was going on.
 */
const props = withDefaults(
  defineProps<{
    /** When each reading starts, in milliseconds since 1970. */
    times: readonly number[]
    traffic: readonly InterfaceTraffic[]
    marks?: readonly ChartMark[]
    loading?: boolean
  }>(),
  { marks: () => [], loading: false },
)

const chosen = ref<string | null>(null)
const names = computed(() => props.traffic.map(({ interface: name }) => name))
/** The one chosen, or the busiest while that one is not among those the dashboard has now. */
const current = computed(
  () => props.traffic.find(({ interface: name }) => name === chosen.value) ?? props.traffic[0],
)
const series = computed(() =>
  current.value
    ? [
        { id: 'received', label: 'Received', values: current.value.received },
        { id: 'sent', label: 'Sent', values: current.value.sent },
      ]
    : [],
)
</script>

<template>
  <v-card class="pa-5 pa-sm-6" data-test="traffic-card">
    <v-select
      v-if="names.length > 1"
      :model-value="current?.interface"
      :items="names"
      label="Interface"
      variant="outlined"
      density="compact"
      hide-details
      class="traffic-card__interface"
      data-test="traffic-interface"
      @update:model-value="chosen = $event"
    />
    <TimeSeriesChart
      title="Network traffic"
      :caption="
        current
          ? `Speed through ${current.interface}, from the firewall's byte counters.`
          : undefined
      "
      :times="times"
      :series="series"
      :format="formatBitrate"
      :marks="marks"
      :loading="loading"
      empty-title="No traffic recorded yet"
      empty-description="Once OPNsense is connected, the bytes through each of its interfaces are read every minute and charted here."
      data-test="traffic-chart"
    />
  </v-card>
</template>

<style scoped>
.traffic-card__interface {
  max-width: 14rem;
  margin-bottom: 1rem;
}
</style>
