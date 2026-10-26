<script setup lang="ts">
import { computed, ref } from 'vue'

import ChartFrame from '@/charts/ChartFrame.vue'
import ChartTooltip from '@/charts/ChartTooltip.vue'
import { useElementWidth } from '@/charts/interaction'
import { STEPS, stepColor } from '@/charts/palette'
import { sequentialStep } from '@/charts/scales'
import type { ChartTableData, TooltipRow } from '@/charts/types'
import { formatCount } from '@/format'

/**
 * How much of something happens at each place on a grid, such as alerts by hour of the day and
 * day of the week: one cell for each, lighter for less and darker for more, on a scale of five
 * steps of one hue. A cell with nothing is a different, flat gray, so "none" never looks like
 * "a little". On a narrow screen the grid scrolls sideways rather than make the cells too small
 * to touch.
 */
const props = withDefaults(
  defineProps<{
    title: string
    caption?: string
    rows: readonly string[]
    /** What the first column of the table is called. */
    rowLabel?: string
    columns: readonly string[]
    /** One list for each row, with a number for each column, none below zero. */
    values: readonly (readonly number[])[]
    /** What is counted, in plural, for the tooltip: "alerts". */
    unit: string
    format?: (value: number) => string
    loading?: boolean
    emptyTitle?: string
    emptyDescription?: string
  }>(),
  {
    caption: undefined,
    rowLabel: 'Row',
    format: formatCount,
    loading: false,
    emptyTitle: undefined,
    emptyDescription: undefined,
  },
)

const CHARACTER = 7
const CELL_HEIGHT = 28
/** The narrowest a cell gets: still a target a fingertip can pick. */
const CELL_MINIMUM = 24
const HEADER = 24

const plot = ref<HTMLElement | null>(null)
const scroller = ref<HTMLElement | null>(null)
const width = useElementWidth(plot, 640)
const active = ref<readonly [row: number, column: number] | null>(null)

const value = (row: number, column: number) => props.values[row]?.[column] ?? 0
const largest = computed(() => Math.max(0, ...props.values.flat()))
const empty = computed(() => !props.rows.length || !props.columns.length || largest.value === 0)

const labelWidth = computed(
  () => Math.max(0, ...props.rows.map(({ length }) => length)) * CHARACTER + 12,
)
const cell = computed(() =>
  Math.max(CELL_MINIMUM, (width.value - labelWidth.value) / props.columns.length),
)
const every = computed(() => {
  const longest = Math.max(0, ...props.columns.map(({ length }) => length))
  return Math.max(1, Math.ceil((longest * CHARACTER + 8) / cell.value))
})

const cells = computed(() =>
  props.rows.flatMap((_, row) =>
    props.columns.map((__, column) => {
      const step = sequentialStep(value(row, column), largest.value, STEPS)
      return { row, column, fill: step === null ? 'var(--chart-empty)' : stepColor(step) }
    }),
  ),
)

const table = computed<ChartTableData>(() => ({
  columns: [props.rowLabel, ...props.columns],
  rows: props.rows.map((row, index) => [
    row,
    ...props.columns.map((_, column) => props.format(value(index, column))),
  ]),
}))
/** The five steps of the scale, from the lightest to the darkest. */
const steps = Array.from({ length: STEPS }, (_, index) => stepColor(index + 1))

const heading = computed(() => {
  const [row, column] = active.value as readonly [number, number]
  return `${props.rows[row] as string} · ${props.columns[column] as string}`
})
const rowsShown = computed<TooltipRow[]>(() => {
  const [row, column] = active.value as readonly [number, number]
  return [{ label: props.unit, value: props.format(value(row, column)) }]
})
const anchor = computed(() => {
  const [row, column] = active.value as readonly [number, number]
  return {
    x: labelWidth.value + (column + 0.5) * cell.value - (scroller.value as HTMLElement).scrollLeft,
    y: HEADER + (row + 0.5) * CELL_HEIGHT,
  }
})
const readout = computed(() =>
  active.value === null ? '' : `${heading.value}: ${rowsShown.value[0]?.value} ${props.unit}`,
)

function onKey(event: KeyboardEvent) {
  const [row, column] = active.value ?? [-1, -1]
  const last = [props.rows.length - 1, props.columns.length - 1] as const
  const moves: Record<string, readonly [number, number] | null> = {
    ArrowRight: [Math.max(0, row), Math.min(last[1], column + 1)],
    ArrowLeft: [Math.max(0, row), Math.max(0, column - 1)],
    ArrowDown: [Math.min(last[0], row + 1), Math.max(0, column)],
    ArrowUp: [Math.max(0, row - 1), Math.max(0, column)],
    Home: [Math.max(0, row), 0],
    End: [Math.max(0, row), last[1]],
    Escape: null,
  }
  if (!(event.key in moves)) return
  event.preventDefault()
  active.value = moves[event.key] ?? null
}

/** A finger stays on what it touched until it touches something else; a pointer leaves with it. */
function leave(event: PointerEvent) {
  if (event.pointerType !== 'touch') active.value = null
}
</script>

<template>
  <ChartFrame
    :title="title"
    :caption="caption"
    :legend="[]"
    :table="table"
    :hidden="[]"
    :empty="empty"
    :empty-title="emptyTitle"
    :empty-description="emptyDescription"
    :loading="loading"
  >
    <div ref="plot" class="heatmap" data-test="heatmap">
      <div ref="scroller" class="heatmap__scroll">
        <svg
          class="chart-svg"
          role="img"
          tabindex="0"
          :width="labelWidth + columns.length * cell"
          :height="HEADER + rows.length * CELL_HEIGHT"
          :aria-label="`${title}. Use the arrow keys to read each cell, or show it as a table.`"
          @keydown="onKey"
          @blur="active = null"
          @pointerleave="leave"
        >
          <text
            v-for="(name, column) in columns"
            :key="column"
            class="chart-text"
            :x="labelWidth + (column + 0.5) * cell"
            :y="12"
            text-anchor="middle"
            dominant-baseline="central"
            :display="column % every === 0 ? undefined : 'none'"
            data-test="heatmap-column"
          >
            {{ name }}
          </text>
          <text
            v-for="(name, row) in rows"
            :key="row"
            class="chart-text"
            x="0"
            :y="HEADER + (row + 0.5) * CELL_HEIGHT"
            dominant-baseline="central"
            data-test="heatmap-row"
          >
            {{ name }}
          </text>
          <rect
            v-for="shape in cells"
            :key="`${shape.row}/${shape.column}`"
            class="heatmap__cell"
            :class="{
              'heatmap__cell--active': active?.[0] === shape.row && active[1] === shape.column,
            }"
            :x="labelWidth + shape.column * cell + 1"
            :y="HEADER + shape.row * CELL_HEIGHT + 1"
            :width="cell - 2"
            :height="CELL_HEIGHT - 2"
            rx="4"
            :fill="shape.fill"
            data-test="heatmap-cell"
            @pointerdown="active = [shape.row, shape.column]"
            @pointerenter="active = [shape.row, shape.column]"
          />
        </svg>
      </div>
      <ChartTooltip
        v-if="active"
        :x="anchor.x"
        :y="anchor.y"
        :flip="anchor.x > width / 2"
        :heading="heading"
        :rows="rowsShown"
      />
      <div class="heatmap__scale text-body-medium" data-test="heatmap-scale">
        <span class="text-medium-emphasis">None</span>
        <span class="heatmap__swatch" :style="{ background: 'var(--chart-empty)' }" />
        <span
          v-for="(color, index) in steps"
          :key="index"
          class="heatmap__swatch"
          :style="{ background: color }"
        />
        <span class="text-medium-emphasis">{{ format(largest) }}</span>
      </div>
      <div class="chart-readout" role="status">{{ readout }}</div>
    </div>
  </ChartFrame>
</template>

<style scoped>
.heatmap {
  position: relative;
}

.heatmap__scroll {
  position: relative;
  overflow-x: auto;
  padding-bottom: 2px;
}

.heatmap__cell--active {
  stroke: rgb(var(--v-theme-on-surface));
  stroke-width: 2;
}

.heatmap__scale {
  display: flex;
  align-items: center;
  gap: 4px;
  margin-top: 0.75rem;
}

.heatmap__scale > :first-child {
  margin-right: 0.25rem;
}

.heatmap__scale > :last-child {
  margin-left: 0.25rem;
}

.heatmap__swatch {
  width: 16px;
  height: 12px;
  border-radius: 3px;
}
</style>
