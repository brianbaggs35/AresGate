<script setup lang="ts">
import { computed, ref } from 'vue'
import type { IconProps } from 'vuetify'

import { layoutBars } from '@/charts/bars'
import ChartFrame from '@/charts/ChartFrame.vue'
import ChartTooltip from '@/charts/ChartTooltip.vue'
import { stepIndex, useElementWidth } from '@/charts/interaction'
import { seriesColor } from '@/charts/palette'
import { linear, valueAxis } from '@/charts/scales'
import type { ChartTableData, LegendItem, TooltipRow } from '@/charts/types'
import { formatCompact, formatCount } from '@/format'

export interface BarSeries {
  id: string
  label: string
  /** One value for each category, none below zero. */
  values: readonly number[]
  /** Only for what has a color of its own, such as a severity. Otherwise the next hue in order. */
  color?: string
  icon?: NonNullable<IconProps['icon']>
}

/**
 * Bars for comparing amounts across categories: horizontal for a ranking such as the busiest
 * hosts, vertical for amounts over a few steps of time. Several series are side by side or, when
 * `stacked`, one on top of the other. Hover, touch or the arrow keys read a category's values.
 */
const props = withDefaults(
  defineProps<{
    title: string
    caption?: string
    categories: readonly string[]
    /** What the first column of the table is called. */
    categoryLabel?: string
    series: readonly BarSeries[]
    orientation?: 'horizontal' | 'vertical'
    stacked?: boolean
    /** How a value reads, on the axis and in the tooltip. */
    format?: (value: number) => string
    /** The height of a vertical chart, with its labels. */
    height?: number
    loading?: boolean
    emptyTitle?: string
    emptyDescription?: string
  }>(),
  {
    caption: undefined,
    categoryLabel: 'Category',
    orientation: 'horizontal',
    stacked: false,
    format: undefined,
    height: 220,
    loading: false,
    emptyTitle: undefined,
    emptyDescription: undefined,
  },
)

/** About how wide a character of the 12px labels is. */
const CHARACTER = 7
const ROW = 36
const TOP = 16
const BOTTOM = 28

const plot = ref<HTMLElement | null>(null)
const width = useElementWidth(plot, 480)
const hidden = ref<string[]>([])
const active = ref<number | null>(null)

const vertical = computed(() => props.orientation === 'vertical')
const valueText = computed(() => props.format ?? formatCount)
const tickText = computed(() => props.format ?? formatCompact)

/** Each series with the color it keeps whatever is turned off. */
const colored = computed(() =>
  props.series.map((series, index) => ({ ...series, color: series.color ?? seriesColor(index) })),
)
const shown = computed(() => colored.value.filter(({ id }) => !hidden.value.includes(id)))
const empty = computed(
  () =>
    !props.categories.length ||
    !props.series.some(({ values }) => values.some((value) => value > 0)),
)

const legend = computed<LegendItem[]>(() =>
  colored.value.map(({ id, label, color, icon }) => ({ id, label, color, shape: 'square', icon })),
)
const table = computed<ChartTableData>(() => {
  const total = props.stacked && props.series.length > 1
  return {
    columns: [
      props.categoryLabel,
      ...props.series.map(({ label }) => label),
      ...(total ? ['Total'] : []),
    ],
    rows: props.categories.map((category, index) => [
      category,
      ...props.series.map(({ values }) => valueText.value(values[index] ?? 0)),
      ...(total
        ? [valueText.value(props.series.reduce((sum, { values }) => sum + (values[index] ?? 0), 0))]
        : []),
    ]),
  }
})

/** What each category adds up to among the series shown: the stack's height, or its tallest bar. */
const totals = computed(() =>
  props.categories.map((_, index) => {
    const values = shown.value.map(({ values }) => values[index] ?? 0)
    return props.stacked ? values.reduce((sum, value) => sum + value, 0) : Math.max(0, ...values)
  }),
)
const largest = computed(() => Math.max(0, ...totals.value))

// The room round the bars: the labels of the categories and of the values.
const labelWidth = computed(() => {
  const longest = Math.max(0, ...props.categories.map(({ length }) => length))
  return Math.min(longest * CHARACTER + 8, width.value * 0.4)
})
const axis = computed(() => valueAxis(largest.value))
const labelled = computed(() => props.stacked || shown.value.length === 1)
const left = computed(() => {
  if (!vertical.value) return labelWidth.value + 8
  return Math.max(...axis.value.ticks.map((tick) => tickText.value(tick).length)) * CHARACTER + 12
})
const right = computed(() => {
  if (vertical.value || !labelled.value) return 4
  return Math.max(...totals.value.map((total) => valueText.value(total).length)) * CHARACTER + 16
})
const length = computed(() =>
  vertical.value
    ? props.height - TOP - BOTTOM
    : Math.max(40, width.value - left.value - right.value),
)
const band = computed(() =>
  vertical.value ? (width.value - left.value - right.value) / props.categories.length : ROW,
)
const drawnHeight = computed(() => (vertical.value ? props.height : props.categories.length * ROW))
const scale = computed(() =>
  linear([0, vertical.value ? axis.value.top : largest.value], [0, length.value]),
)

const layout = computed(() =>
  layoutBars({
    orientation: props.orientation,
    stacked: props.stacked,
    values: shown.value.map(({ values }) => values),
    categories: props.categories.length,
    length: length.value,
    band: band.value,
    max: vertical.value ? axis.value.top : largest.value,
  }),
)
const shapes = computed(() =>
  layout.value.shapes.map((shape) => ({
    ...shape,
    color: (shown.value[shape.series] as { color: string }).color,
  })),
)
const labels = computed(() =>
  layout.value.labels.map((label) => ({ ...label, text: valueText.value(label.value) })),
)

/** Names that don't fit are cut short, and only every so many of a crowded axis are named. */
const categoryNames = computed(() => {
  if (!vertical.value) {
    const fits = Math.max(1, Math.floor((labelWidth.value - 8) / CHARACTER))
    return props.categories.map((name) =>
      name.length > fits ? `${name.slice(0, fits - 1)}…` : name,
    )
  }
  const longest = Math.max(0, ...props.categories.map(({ length }) => length))
  const every = Math.max(1, Math.ceil((longest * CHARACTER + 8) / band.value))
  return props.categories.map((name, index) => (index % every === 0 ? name : ''))
})

// Where a category's readout points: at the end of its bar, or the top of its column.
const anchor = computed(() => {
  const index = active.value as number
  const reach = Math.max(
    totals.value[index] === 0 ? 0 : 4,
    scale.value(totals.value[index] as number),
  )
  return vertical.value
    ? { x: left.value + (index + 0.5) * band.value, y: TOP + length.value - reach }
    : { x: left.value + reach, y: (index + 0.5) * ROW }
})

const rows = computed<TooltipRow[]>(() => {
  const index = active.value as number
  const found: TooltipRow[] = shown.value.map(({ label, color, values }) => ({
    label,
    value: valueText.value(values[index] ?? 0),
    color,
    shape: 'square',
  }))
  if (props.stacked && shown.value.length > 1) {
    found.push({ label: 'Total', value: valueText.value(totals.value[index] as number) })
  }
  return found
})
const readout = computed(() =>
  active.value === null
    ? ''
    : `${props.categories[active.value] as string}: ${rows.value.map(({ value, label }) => `${value} ${label}`).join(', ')}`,
)

function onKey(event: KeyboardEvent) {
  const next = stepIndex(event.key, active.value, props.categories.length)
  if (next === undefined) return
  event.preventDefault()
  active.value = next
}

/** A finger stays on what it touched until it touches something else; a pointer leaves with it. */
function leave(event: PointerEvent) {
  if (event.pointerType !== 'touch') active.value = null
}
</script>

<template>
  <ChartFrame
    v-model:hidden="hidden"
    :title="title"
    :caption="caption"
    :legend="legend"
    :table="table"
    :empty="empty"
    :empty-title="emptyTitle"
    :empty-description="emptyDescription"
    :loading="loading"
  >
    <div ref="plot" class="bar-chart" data-test="bar-chart">
      <svg
        class="chart-svg"
        role="img"
        tabindex="0"
        :width="width"
        :height="drawnHeight"
        :aria-label="`${title}. Use the arrow keys to read each one, or show it as a table.`"
        @keydown="onKey"
        @blur="active = null"
        @pointerleave="leave"
      >
        <template v-if="vertical">
          <g v-for="tick in axis.ticks" :key="tick">
            <line
              class="chart-grid"
              :x1="left"
              :x2="width"
              :y1="TOP + length - scale(tick)"
              :y2="TOP + length - scale(tick)"
            />
            <text
              class="chart-text"
              :x="left - 8"
              :y="TOP + length - scale(tick)"
              text-anchor="end"
              dominant-baseline="central"
            >
              {{ tickText(tick) }}
            </text>
          </g>
        </template>
        <line v-else class="chart-axis" :x1="left" :x2="left" y1="0" :y2="drawnHeight" />

        <g :transform="vertical ? `translate(${left},${TOP})` : `translate(${left},0)`">
          <rect
            v-if="active !== null"
            class="bar-chart__band"
            :x="vertical ? active * band : 0"
            :y="vertical ? 0 : active * band"
            :width="vertical ? band : length + right"
            :height="vertical ? length : band"
            rx="4"
          />
          <path
            v-for="shape in shapes"
            :key="`${shape.series}/${shape.category}`"
            :d="shape.path"
            :fill="shape.color"
            :class="{ 'bar-chart__mark--dim': active !== null && active !== shape.category }"
            class="bar-chart__mark"
            data-test="bar"
          />
          <text
            v-for="label in labels"
            :key="label.category"
            class="chart-value"
            :x="vertical ? label.center : label.tip + 6"
            :y="vertical ? length - label.tip - 6 : label.center"
            :text-anchor="vertical ? 'middle' : 'start'"
            :dominant-baseline="vertical ? 'auto' : 'central'"
            :display="vertical && band < 36 ? 'none' : undefined"
            data-test="bar-value"
          >
            {{ label.text }}
          </text>
        </g>

        <text
          v-for="(name, index) in categoryNames"
          :key="index"
          class="chart-text"
          :x="vertical ? left + (index + 0.5) * band : 0"
          :y="vertical ? TOP + length + 18 : (index + 0.5) * ROW"
          :text-anchor="vertical ? 'middle' : 'start'"
          dominant-baseline="central"
          data-test="bar-category"
        >
          {{ name }}
        </text>

        <!-- Each category's whole slot answers the pointer, far bigger than the bar. -->
        <rect
          v-for="(_, index) in categories"
          :key="index"
          :x="vertical ? left + index * band : 0"
          :y="vertical ? 0 : index * band"
          :width="vertical ? band : width"
          :height="vertical ? drawnHeight : band"
          fill="transparent"
          data-test="bar-slot"
          @pointerdown="active = index"
          @pointerenter="active = index"
        />
      </svg>
      <ChartTooltip
        v-if="active !== null"
        :x="anchor.x"
        :y="anchor.y"
        :flip="anchor.x > width / 2"
        :heading="categories[active] as string"
        :rows="rows"
      />
      <div class="chart-readout" role="status">{{ readout }}</div>
    </div>
  </ChartFrame>
</template>

<style scoped>
.bar-chart {
  position: relative;
}

.bar-chart__band {
  fill: rgba(var(--v-theme-on-surface), var(--v-hover-opacity));
}

.bar-chart__mark {
  transition: opacity 0.15s;
}

/* The category being read stands out by the others stepping back. */
.bar-chart__mark--dim {
  opacity: 0.5;
}
</style>
