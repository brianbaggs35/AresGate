<script setup lang="ts">
import { nextTick, onMounted, ref, useTemplateRef, watch } from 'vue'

import type { TooltipRow } from '@/charts/types'

/**
 * The readout that follows the pointer (or the keyboard) over a chart: what is under it and each
 * value, the number first. It only repeats what the table view and the chart's own labels say, so
 * it is hidden from screen readers, which are told by the chart. It is centered on the point it
 * reads, and then moved up or down just enough to stay inside the chart's box: at the foot of a
 * column that is nearly empty, half of it would otherwise hang below the chart and be cut off by,
 * or sit under, whatever is beneath.
 */
const props = defineProps<{
  /** Where it points, in pixels from the top left of the chart. */
  x: number
  y: number
  /** Whether it opens to the left of that point rather than the right. */
  flip: boolean
  heading: string
  rows: readonly TooltipRow[]
}>()

const tip = useTemplateRef<HTMLElement>('tip')
/** How far it was moved, in pixels, to stay inside the chart: up is negative. */
const shift = ref(0)

/** Where its centre may be so that all of it is inside a box of this height: its own height is
 * only known once it is drawn. A box too small for it keeps its top in view. */
function keptInside(centre: number, height: number, box: number): number {
  return Math.max(height / 2, Math.min(centre, box - height / 2))
}

function fit() {
  const element = tip.value
  const box = element?.offsetParent?.clientHeight ?? 0
  if (!element || box === 0) {
    shift.value = 0
    return
  }
  shift.value = keptInside(props.y, element.offsetHeight, box) - props.y
}

onMounted(fit)
// What it says changes its height, and where it points changes how much it has to move.
watch(
  () => [props.y, props.rows, props.heading],
  () => void nextTick(fit),
)
</script>

<template>
  <div
    ref="tip"
    class="chart-tooltip"
    :class="{ 'chart-tooltip--flip': flip }"
    :style="{ left: `${x}px`, top: `${y + shift}px` }"
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
