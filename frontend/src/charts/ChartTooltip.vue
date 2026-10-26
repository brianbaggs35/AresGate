<script setup lang="ts">
import type { TooltipRow } from '@/charts/types'

/**
 * The readout that follows the pointer (or the keyboard) over a chart: what is under it and each
 * value, the number first. It only repeats what the table view and the chart's own labels say, so
 * it is hidden from screen readers, which are told by the chart.
 */
defineProps<{
  /** Where it points, in pixels from the top left of the chart. */
  x: number
  y: number
  /** Whether it opens to the left of that point rather than the right. */
  flip: boolean
  heading: string
  rows: readonly TooltipRow[]
}>()
</script>

<template>
  <div
    class="chart-tooltip"
    :class="{ 'chart-tooltip--flip': flip }"
    :style="{ left: `${x}px`, top: `${y}px` }"
    aria-hidden="true"
    data-test="chart-tooltip"
  >
    <p class="chart-tooltip__heading text-label-medium text-medium-emphasis">{{ heading }}</p>
    <p
      v-for="row in rows"
      :key="row.label"
      class="chart-tooltip__row"
      data-test="chart-tooltip-row"
    >
      <span
        v-if="row.color"
        class="chart-tooltip__key"
        :class="`chart-tooltip__key--${row.shape ?? 'line'}`"
        :style="{ '--key': row.color }"
      />
      <span class="chart-tooltip__value text-body-large" data-test="chart-tooltip-value">{{
        row.value
      }}</span>
      <span class="text-body-medium text-medium-emphasis">{{ row.label }}</span>
    </p>
  </div>
</template>

<style scoped>
.chart-tooltip {
  position: absolute;
  z-index: 2;
  min-width: 8rem;
  max-width: min(18rem, 80vw);
  padding: 0.5rem 0.75rem;
  border: thin solid rgb(var(--v-border-color), var(--v-border-opacity));
  border-radius: 8px;
  background: rgb(var(--v-theme-surface));
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.16);
  pointer-events: none;
  transform: translate(12px, -50%);
}

.chart-tooltip--flip {
  transform: translate(calc(-100% - 12px), -50%);
}

.chart-tooltip p {
  margin: 0;
}

.chart-tooltip__row {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.chart-tooltip__value {
  font-weight: 600;
  font-variant-numeric: tabular-nums;
}

.chart-tooltip__key {
  flex: none;
  background: var(--key);
}

.chart-tooltip__key--line {
  width: 12px;
  height: 3px;
  border-radius: 2px;
}

.chart-tooltip__key--square {
  width: 8px;
  height: 8px;
  border-radius: 2px;
}
</style>
