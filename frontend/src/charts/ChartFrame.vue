<script setup lang="ts">
import { ChartColumn, Table2 } from '@lucide/vue'
import { computed, ref, useId } from 'vue'

import ChartLegend from '@/charts/ChartLegend.vue'
import ChartTable from '@/charts/ChartTable.vue'
import type { ChartTableData, LegendItem } from '@/charts/types'
import EmptyState from '@/components/EmptyState.vue'

/**
 * What every chart sits in: its title and what it shows, the legend when there is more than one
 * series, and a switch between the chart and the same numbers as a table. The chart itself goes
 * in the slot. While fresh data loads the chart stays, dimmed, rather than being replaced.
 */
const props = defineProps<{
  title: string
  /** What the chart shows and over what time. */
  caption?: string
  legend: readonly LegendItem[]
  table: ChartTableData
  /** The ids of the series turned off in the legend. */
  hidden: readonly string[]
  /** Nothing to draw: the message below takes the chart's place. */
  empty?: boolean
  emptyTitle?: string
  emptyDescription?: string
  loading?: boolean
}>()
const emit = defineEmits<{ 'update:hidden': [ids: string[]] }>()

const asTable = ref(false)
const titleId = useId()
const showTable = computed(() => asTable.value && !props.empty)
</script>

<template>
  <figure
    class="chart-frame"
    :aria-labelledby="titleId"
    :aria-busy="loading ? 'true' : undefined"
    data-test="chart"
  >
    <div class="chart-frame__head">
      <div class="chart-frame__titles">
        <p :id="titleId" class="text-title-medium" data-test="chart-title">{{ title }}</p>
        <p v-if="caption" class="text-body-medium text-medium-emphasis" data-test="chart-caption">
          {{ caption }}
        </p>
      </div>
      <v-btn
        v-if="!empty"
        variant="text"
        size="small"
        :prepend-icon="showTable ? ChartColumn : Table2"
        data-test="chart-view"
        @click="asTable = !asTable"
      >
        {{ showTable ? 'Show chart' : 'Show as table' }}
      </v-btn>
    </div>

    <ChartLegend
      v-if="legend.length > 1 && !showTable && !empty"
      :items="legend"
      :hidden="hidden"
      class="chart-frame__legend"
      @update:hidden="emit('update:hidden', $event)"
    />

    <EmptyState
      v-if="empty"
      :title="emptyTitle ?? 'Nothing to show yet'"
      :description="emptyDescription"
      data-test="chart-empty"
    />
    <ChartTable v-else-if="showTable" :table="table" :label="title" />
    <div v-else class="chart-frame__plot" :class="{ 'chart-frame__plot--loading': loading }">
      <slot />
    </div>
  </figure>
</template>

<style scoped>
.chart-frame {
  margin: 0;
}

.chart-frame__head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 0.5rem 1rem;
  margin-bottom: 0.5rem;
}

.chart-frame__titles {
  min-width: 0;
}

.chart-frame__titles p {
  margin: 0;
}

.chart-frame__legend {
  margin-bottom: 0.5rem;
}

.chart-frame__plot {
  position: relative;
  transition: opacity 0.2s;
}

/* Fresh data is on its way: the chart holds its place, dimmed, so nothing jumps. */
.chart-frame__plot--loading {
  opacity: 0.5;
}
</style>
