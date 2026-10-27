<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import type { IconProps } from 'vuetify'

import ChartFrame from '@/charts/ChartFrame.vue'
import ChartTooltip from '@/charts/ChartTooltip.vue'
import { stepIndex, useElementWidth } from '@/charts/interaction'
import { placeMarks, readingOf, type Flag } from '@/charts/marks'
import { areaPath, linePath, type Point } from '@/charts/paths'
import { seriesColor } from '@/charts/palette'
import { formatTick, linear, nearest, timeTicks, valueAxis } from '@/charts/scales'
import type { ChartMark, ChartTableData, LegendItem, TooltipRow } from '@/charts/types'
import { formatCompact, formatCount, formatDateTime } from '@/format'

export interface LineSeries {
  id: string
  label: string
  /** One value for each moment, none below zero; null where nothing was measured. */
  values: readonly (number | null)[]
  /** Only for what has a color of its own. Otherwise the next hue in order. */
  color?: string
  icon?: NonNullable<IconProps['icon']>
}

/**
 * How amounts change over time, one line for each series on a shared scale from zero. Moving
 * across it (pointer, finger or the arrow keys) reads every series at that moment. A gap in the
 * data is a gap in the line, never a zero.
 */
const props = withDefaults(
  defineProps<{
    title: string
    caption?: string
    /** The moments, in milliseconds since 1970 and in order. */
    times: readonly number[]
    series: readonly LineSeries[]
    /** A wash of the line's color down to the axis. */
    area?: boolean
    /** How a value reads, on the axis and in the tooltip. */
    format?: (value: number) => string
    /** The height with the time axis. */
    height?: number
    /** Things that happened at a moment, flagged above the chart with a link to each. Flags that
     * would overlap are drawn as one that says how many it stands for. */
    marks?: readonly ChartMark[]
    loading?: boolean
    emptyTitle?: string
    emptyDescription?: string
  }>(),
  {
    caption: undefined,
    area: false,
    format: undefined,
    height: 220,
    marks: () => [],
    loading: false,
    emptyTitle: undefined,
    emptyDescription: undefined,
  },
)

const CHARACTER = 7
const TOP = 12
const BOTTOM = 28
/** How tall a flag is, and the room above the plot for them when there are any. */
const FLAG_HEIGHT = 28
const FLAG_ROW = 30
/** How many incidents a flag that stands for several names in its readout. */
const NAMED = 4
/** The first of these sizes of chart has room to write each line's last value at its end. */
const LABELLED_FROM = 480
const LABELLED_UP_TO = 4
/** How close two end labels may be before they are left off, which is better than nudging them
 * away from their lines. */
const CLOSEST = 14

const plot = ref<HTMLElement | null>(null)
const width = useElementWidth(plot, 640)
const hidden = ref<string[]>([])
const active = ref<number | null>(null)
/** The flag being pointed at or focused, as its place in `flags`. */
const flagged = ref<number | null>(null)
const svg = ref<SVGSVGElement | null>(null)

const valueText = computed(() => props.format ?? formatCount)
const tickText = computed(() => props.format ?? formatCompact)

const colored = computed(() =>
  props.series.map((series, index) => ({ ...series, color: series.color ?? seriesColor(index) })),
)
const shown = computed(() => colored.value.filter(({ id }) => !hidden.value.includes(id)))
const empty = computed(
  () =>
    !props.times.length ||
    !props.series.some(({ values }) => values.some((value) => value !== null)),
)

const legend = computed<LegendItem[]>(() =>
  colored.value.map(({ id, label, color, icon }) => ({ id, label, color, shape: 'line', icon })),
)
const when = (time: number) => formatDateTime(new Date(time).toISOString())
/** What happened at each reading, for the table: the marks that fall between it and the next. */
const happenings = computed(() => {
  const found = props.times.map(() => [] as string[])
  for (const mark of props.marks) found[readingOf(props.times, mark.time)]?.push(mark.label)
  return found.map((labels) => labels.join('; '))
})
const table = computed<ChartTableData>(() => ({
  columns: [
    'Time',
    ...props.series.map(({ label }) => label),
    ...(props.marks.length ? ['Incidents'] : []),
  ],
  rows: props.times.map((time, index) => [
    when(time),
    ...props.series.map(({ values }) => {
      const value = values[index] ?? null
      return value === null ? 'No data' : valueText.value(value)
    }),
    ...(props.marks.length ? [happenings.value[index] || 'None'] : []),
  ]),
}))

const axis = computed(() =>
  valueAxis(Math.max(0, ...shown.value.flatMap(({ values }) => values.map((value) => value ?? 0)))),
)

/** The last reading of each line, which is where its dot and label go. */
const ends = computed(() =>
  shown.value.flatMap(({ id, color, values }) => {
    let index = values.length - 1
    while (index >= 0 && values[index] === null) index--
    return index < 0 ? [] : [{ id, color, index, value: values[index] as number }]
  }),
)
const labelled = computed(() => {
  if (width.value < LABELLED_FROM || ends.value.length > LABELLED_UP_TO) return false
  const heights = ends.value.map(({ value }) => y.value(value)).sort((a, b) => a - b)
  return heights.every(
    (height, index) => index === 0 || height - (heights[index - 1] as number) >= CLOSEST,
  )
})

const left = computed(
  () => Math.max(...axis.value.ticks.map((tick) => tickText.value(tick).length)) * CHARACTER + 12,
)
const right = computed(() =>
  labelled.value
    ? Math.max(...ends.value.map(({ value }) => valueText.value(value).length)) * CHARACTER + 24
    : 32,
)
const length = computed(() => Math.max(40, width.value - left.value - right.value))
/** Where the plot starts: lower when the flags need room above it. Every mark has a flag, so this
 * does not wait for their places, which depend on the plot's width. */
const top = computed(() => TOP + (empty.value || !props.marks.length ? 0 : FLAG_ROW))
const rise = computed(() => props.height - top.value - BOTTOM)

const first = computed(() => props.times[0] as number)
const last = computed(() => props.times[props.times.length - 1] as number)
const x = computed(() => linear([first.value, last.value], [0, length.value]))
const y = computed(() => linear([0, axis.value.top], [rise.value, 0]))

const xTicks = computed(() =>
  timeTicks(first.value, last.value, Math.max(2, Math.floor(length.value / 90))).map((time) => ({
    x: x.value(time),
    text: formatTick(time, last.value - first.value),
  })),
)

const flags = computed<Flag[]>(() =>
  empty.value ? [] : placeMarks(props.marks, [first.value, last.value], x.value),
)
const flagWords = (flag: Flag) => {
  const [chief] = flag.marks
  return flag.marks.length === 1
    ? chief.label
    : `${flag.marks.length} incidents close together, the most serious first: ${chief.label}`
}
/** The readout of the flag being pointed at: its own, or a list of those it stands for. */
const flagReadout = computed(() => {
  const flag = flags.value[flagged.value as number] as Flag
  const [chief] = flag.marks
  if (flag.marks.length === 1) return { heading: chief.heading, rows: chief.rows }
  const named = flag.marks.slice(0, NAMED).map(({ rows: [row], color }) => ({
    ...row,
    color,
    shape: 'square' as const,
  }))
  const more = flag.marks.length - NAMED
  return {
    heading: `${flag.marks.length} incidents around ${when(chief.time)}`,
    rows: more > 0 ? [...named, { label: `and ${more} more`, value: '' }] : named,
  }
})

// A flag that goes away, because the incidents changed, is not pointed at any more.
watch(flags, () => {
  flagged.value = null
})

const lines = computed(() =>
  shown.value.map(({ id, color, values }) => {
    const points: Point[] = props.times.map((time, index) => {
      const value = values[index] ?? null
      return [x.value(time), value === null ? null : y.value(value)]
    })
    return {
      id,
      color,
      line: linePath(points),
      area: props.area ? areaPath(points, rise.value) : '',
    }
  }),
)

const rows = computed<TooltipRow[]>(() =>
  shown.value.map(({ label, color, values }) => {
    const value = values[active.value as number] ?? null
    return {
      label,
      value: value === null ? 'No data' : valueText.value(value),
      color,
      shape: 'line',
    }
  }),
)
/** Each series' dot at the moment being read, and the height the tooltip points at. */
const dots = computed(() =>
  shown.value.flatMap(({ id, color, values }) => {
    const value = values[active.value as number] ?? null
    return value === null ? [] : [{ id, color, y: y.value(value) }]
  }),
)
const anchor = computed(() => {
  const heights = dots.value.map((dot) => dot.y)
  return {
    x: left.value + x.value(props.times[active.value as number] as number),
    y:
      top.value +
      (heights.length ? (Math.min(...heights) + Math.max(...heights)) / 2 : rise.value / 2),
  }
})
const readout = computed(() => {
  if (active.value === null) return ''
  const values = rows.value.map(({ value, label }) => `${value} ${label}`).join(', ')
  return `${when(props.times[active.value] as number)}: ${values}`
})

/** The moment under the pointer. */
function point(event: PointerEvent) {
  const box = (svg.value as SVGSVGElement).getBoundingClientRect()
  const along = (event.clientX - box.left - left.value) / length.value
  active.value = nearest(props.times, first.value + along * (last.value - first.value))
}

function onKey(event: KeyboardEvent) {
  const next = stepIndex(event.key, active.value, props.times.length)
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
    <div ref="plot" class="time-series" data-test="time-series">
      <svg
        ref="svg"
        class="chart-svg"
        role="img"
        tabindex="0"
        :width="width"
        :height="height"
        :aria-label="`${title}. Use the left and right arrow keys to read each moment, or show it as a table.`"
        @keydown="onKey"
        @blur="active = null"
        @pointermove="point"
        @pointerdown="point"
        @pointerleave="leave"
      >
        <g v-for="tick in axis.ticks" :key="tick">
          <line
            :class="tick === 0 ? 'chart-axis' : 'chart-grid'"
            :x1="left"
            :x2="left + length"
            :y1="top + y(tick)"
            :y2="top + y(tick)"
          />
          <text
            class="chart-text"
            :x="left - 8"
            :y="top + y(tick)"
            text-anchor="end"
            dominant-baseline="central"
          >
            {{ tickText(tick) }}
          </text>
        </g>
        <text
          v-for="tick in xTicks"
          :key="tick.x"
          class="chart-text"
          :x="left + tick.x"
          :y="top + rise + 18"
          text-anchor="middle"
          data-test="time-tick"
        >
          {{ tick.text }}
        </text>

        <g :transform="`translate(${left},${top})`">
          <line
            v-for="flag in flags"
            :key="flag.marks[0].id"
            class="time-series__flag-line"
            :x1="flag.x"
            :x2="flag.x"
            :y1="FLAG_HEIGHT - top"
            :y2="rise"
            :stroke="flag.marks[0].color"
            data-test="chart-flag-line"
          />
          <line
            v-if="active !== null"
            class="chart-axis"
            :x1="x(times[active] as number)"
            :x2="x(times[active] as number)"
            y1="0"
            :y2="rise"
            data-test="crosshair"
          />
          <g v-for="line in lines" :key="line.id">
            <path v-if="area" :d="line.area" :fill="line.color" fill-opacity="0.1" />
            <path
              :d="line.line"
              :stroke="line.color"
              fill="none"
              stroke-width="2"
              stroke-linejoin="round"
              stroke-linecap="round"
              data-test="line"
            />
          </g>
          <template v-if="active === null">
            <circle
              v-for="end in ends"
              :key="end.id"
              class="time-series__dot"
              :cx="x(times[end.index] as number)"
              :cy="y(end.value)"
              r="5"
              :fill="end.color"
              data-test="end-dot"
            />
            <text
              v-for="end in labelled ? ends : []"
              :key="end.id"
              class="chart-value"
              :x="x(times[end.index] as number) + 12"
              :y="y(end.value)"
              dominant-baseline="central"
              data-test="end-value"
            >
              {{ valueText(end.value) }}
            </text>
          </template>
          <circle
            v-for="dot in active === null ? [] : dots"
            :key="dot.id"
            class="time-series__dot"
            :cx="x(times[active as number] as number)"
            :cy="dot.y"
            r="5"
            :fill="dot.color"
            data-test="dot"
          />
        </g>
      </svg>
      <ul
        v-if="flags.length"
        class="time-series__flags"
        :style="{ left: `${left}px`, width: `${length}px` }"
        aria-label="Incidents in this time"
        data-test="chart-flags"
      >
        <li
          v-for="(flag, index) in flags"
          :key="flag.marks[0].id"
          class="time-series__flag"
          :style="{ left: `${flag.x}px`, '--flag': flag.marks[0].color }"
        >
          <router-link
            :to="flag.marks[0].to"
            class="time-series__flag-link"
            :aria-label="flagWords(flag)"
            data-test="chart-flag"
            @pointerenter="flagged = index"
            @pointerleave="flagged = null"
            @focus="flagged = index"
            @blur="flagged = null"
          >
            <component :is="flag.marks[0].icon" :size="14" aria-hidden="true" />
            <span
              v-if="flag.marks.length > 1"
              class="time-series__count"
              data-test="chart-flag-count"
              >{{ flag.marks.length }}</span
            >
          </router-link>
        </li>
      </ul>
      <ChartTooltip
        v-if="flagged !== null"
        :x="left + (flags[flagged] as Flag).x"
        :y="FLAG_HEIGHT / 2"
        :flip="left + (flags[flagged] as Flag).x > width / 2"
        :heading="flagReadout.heading"
        :rows="flagReadout.rows"
      />
      <ChartTooltip
        v-if="active !== null"
        :x="anchor.x"
        :y="anchor.y"
        :flip="anchor.x > width / 2"
        :heading="when(times[active] as number)"
        :rows="rows"
      />
      <output class="chart-readout">{{ readout }}</output>
    </div>
  </ChartFrame>
</template>

<style scoped>
.time-series {
  position: relative;
}

/* A flag per incident sits above the plot, on a dashed line down to the moment it began. It is
   a link, so the keyboard and a screen reader reach it, and the area that answers a finger is
   larger than the flag. */
.time-series__flags {
  position: absolute;
  top: 0;
  height: 28px;
  margin: 0;
  padding: 0;
  list-style: none;
  pointer-events: none;
}

.time-series__flag {
  position: absolute;
  top: 0;
  transform: translateX(-50%);
  pointer-events: auto;
}

.time-series__flag-link {
  position: relative;
  display: grid;
  place-items: center;
  min-width: 28px;
  height: 28px;
  padding: 0 4px;
  gap: 2px;
  grid-auto-flow: column;
  border: 2px solid var(--flag);
  border-radius: 14px;
  background: rgb(var(--v-theme-surface));
  color: var(--flag);
  text-decoration: none;
}

.time-series__flag-link::after {
  content: '';
  position: absolute;
  inset: -8px;
}

.time-series__flag-link:hover {
  background: color-mix(in srgb, var(--flag) 14%, rgb(var(--v-theme-surface)));
}

.time-series__flag-link:focus-visible {
  outline: 2px solid rgb(var(--v-theme-primary));
  outline-offset: 2px;
}

.time-series__count {
  color: rgb(var(--v-theme-on-surface));
  font-size: 0.75rem;
  font-weight: 600;
  line-height: 1;
}

.time-series__flag-line {
  stroke-dasharray: 3 4;
  stroke-opacity: 0.6;
}

/* A dot is ringed in the card's own color, so it stands clear of whatever it sits on. */
.time-series__dot {
  stroke: rgb(var(--v-theme-surface));
  stroke-width: 2;
}
</style>
