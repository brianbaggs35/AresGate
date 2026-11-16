<script setup lang="ts">
import { RotateCcw } from '@lucide/vue'
import { computed, ref, watch } from 'vue'
import { useRouter, type RouteLocationRaw } from 'vue-router'
import type { IconProps } from 'vuetify'

import ChartFrame from '@/charts/ChartFrame.vue'
import ChartTooltip from '@/charts/ChartTooltip.vue'
import { stepIndex, useElementWidth } from '@/charts/interaction'
import { placeMarks, readingOf, type Flag } from '@/charts/marks'
import { areaPath, linePath, type Point } from '@/charts/paths'
import { seriesColor } from '@/charts/palette'
import { dashClass, textureOf } from '@/charts/patterns'
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
    /** Where a moment leads, or null for one that leads nowhere: a click on the plot, or Enter,
     * opens it, and the tooltip says it can be. Without it the plot is not a link. */
    to?: (time: number) => RouteLocationRaw | null
    /** Dragging across the plot (or Shift and the arrow keys, then Enter) picks a span, which is
     * told to whoever listens (`zoom`). The page narrows its range to it and gives the chart the
     * narrower numbers; `zoomed` says that it has, and shows the button that puts it back. */
    zoomable?: boolean
    zoomed?: boolean
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
    to: undefined,
    zoomable: false,
    zoomed: false,
    loading: false,
    emptyTitle: undefined,
    emptyDescription: undefined,
  },
)

const emit = defineEmits<{ zoom: [from: number, to: number]; reset: [] }>()

const router = useRouter()
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
  props.series.map((series, index) => ({
    ...series,
    color: series.color ?? seriesColor(index),
    texture: textureOf(index),
  })),
)
const shown = computed(() => colored.value.filter(({ id }) => !hidden.value.includes(id)))
const empty = computed(
  () =>
    !props.times.length ||
    !props.series.some(({ values }) => values.some((value) => value !== null)),
)

const legend = computed<LegendItem[]>(() =>
  colored.value.map(({ id, label, color, icon, texture }) => ({
    id,
    label,
    color,
    shape: 'line',
    icon,
    texture,
  })),
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
  textures: [
    null,
    ...colored.value.map(({ texture }) => texture),
    ...(props.marks.length ? [null] : []),
  ],
  textureShape: 'line',
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
const last = computed(() => props.times.at(-1) as number)
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
  shown.value.map(({ id, color, texture, values }) => {
    const points: Point[] = props.times.map((time, index) => {
      const value = values[index] ?? null
      return [x.value(time), value === null ? null : y.value(value)]
    })
    return {
      id,
      color,
      texture,
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
  if (selection.value) {
    const [lo, hi] = selection.value
    return `Zoom from ${when(props.times[lo] as number)} to ${when(props.times[hi] as number)}. Press Enter to zoom in, or Escape to cancel.`
  }
  if (active.value === null) return ''
  const values = rows.value.map(({ value, label }) => `${value} ${label}`).join(', ')
  return `${when(props.times[active.value] as number)}: ${values}`
})

/** The reading under a pointer. */
function readingAt(event: PointerEvent) {
  const box = (svg.value as SVGSVGElement).getBoundingClientRect()
  const along = (event.clientX - box.left - left.value) / length.value
  return nearest(props.times, first.value + along * (last.value - first.value))
}

/** The readings a drag or Shift and the arrow keys has picked, from the first to the last. */
const selection = ref<readonly [number, number] | null>(null)
/** Where Shift and the arrow keys started from. */
const anchored = ref<number | null>(null)
/** A press that has not been let go: where it began, whether it has become a drag, and whether it
 * counts as a click (a finger reads a moment with its first tap and opens it with the next). */
let pressed: { index: number; dragged: boolean; armed: boolean } | null = null

/** Where a moment leads, if anywhere. */
const destination = (index: number) => props.to?.(props.times[index] as number) ?? null
const hint = computed(() => {
  if (selection.value) return 'Enter to zoom in'
  if (active.value !== null && destination(active.value) !== null) return 'Click to open'
  return props.zoomable ? 'Drag to zoom in' : undefined
})

function open(index: number) {
  const place = destination(index)
  if (place !== null) void router.push(place)
}

function zoomIn() {
  const [lo, hi] = selection.value as readonly [number, number]
  selection.value = null
  anchored.value = null
  emit('zoom', props.times[lo] as number, props.times[hi] as number)
}

function press(event: PointerEvent) {
  const index = readingAt(event)
  pressed = {
    index,
    dragged: false,
    armed: event.pointerType !== 'touch' || active.value === index,
  }
  active.value = index
  // Keeps the drag going when it leaves the plot, so it ends where the pointer is let go.
  ;(event.currentTarget as Element).setPointerCapture(event.pointerId)
}

function move(event: PointerEvent) {
  const index = readingAt(event)
  active.value = index
  if (!pressed || !props.zoomable || index === pressed.index) return
  pressed.dragged = true
  selection.value = [Math.min(pressed.index, index), Math.max(pressed.index, index)]
}

function release() {
  const done = pressed
  pressed = null
  if (!done) return
  if (done.dragged) {
    if (selection.value) zoomIn()
  } else if (done.armed) {
    open(done.index)
  }
}

/** A press that was taken away (a scroll began, say) picks nothing. */
function cancel() {
  pressed = null
  selection.value = null
}

/** Shift with an arrow key stretches a selection from where it began, a moment at a time. */
function stretch(event: KeyboardEvent) {
  event.preventDefault()
  const step = event.key === 'ArrowRight' ? 1 : -1
  const from = anchored.value ?? active.value ?? (step > 0 ? 0 : props.times.length - 1)
  const next = Math.min(props.times.length - 1, Math.max(0, (active.value ?? from) + step))
  anchored.value = from
  active.value = next
  selection.value = [Math.min(from, next), Math.max(from, next)]
}

/** Enter zooms to a selection, or opens what the moment it is on leads to. Whether it did. */
function confirm(event: KeyboardEvent): boolean {
  if (selection.value) {
    event.preventDefault()
    if (selection.value[0] !== selection.value[1]) zoomIn()
    return true
  }
  if (active.value !== null && destination(active.value) !== null) {
    event.preventDefault()
    open(active.value)
    return true
  }
  return false
}

function onKey(event: KeyboardEvent) {
  if (props.zoomable && event.shiftKey && ['ArrowLeft', 'ArrowRight'].includes(event.key)) {
    stretch(event)
    return
  }
  if (event.key === 'Enter' && confirm(event)) return
  if (event.key === 'Escape' && selection.value) {
    event.preventDefault()
    selection.value = null
    anchored.value = null
    return
  }
  const next = stepIndex(event.key, active.value, props.times.length)
  if (next === undefined) return
  event.preventDefault()
  anchored.value = null
  selection.value = null
  active.value = next
}

function lose() {
  active.value = null
  selection.value = null
  anchored.value = null
}

/** A finger stays on what it touched until it touches something else; a pointer leaves with it. */
function leave(event: PointerEvent) {
  if (event.pointerType !== 'touch' && !pressed) active.value = null
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
    :empty-title="zoomed ? 'Nothing in this stretch' : emptyTitle"
    :empty-description="zoomed ? 'Reset the zoom to see all of it.' : emptyDescription"
    :loading="loading"
  >
    <template #actions>
      <v-btn
        v-if="zoomed"
        variant="text"
        size="small"
        :prepend-icon="RotateCcw"
        data-test="chart-zoom-reset"
        @click="emit('reset')"
      >
        Reset zoom
      </v-btn>
    </template>
    <div ref="plot" class="time-series" data-test="time-series">
      <svg
        ref="svg"
        class="chart-svg"
        role="img"
        tabindex="0"
        :width="width"
        :height="height"
        :aria-label="`${title}. Use the left and right arrow keys to read each moment${zoomable ? ', hold Shift to pick a span to zoom in on' : ''}${to ? ', Enter to open it' : ''}, or show it as a table.`"
        @keydown="onKey"
        @blur="lose"
        @pointermove="move"
        @pointerdown="press"
        @pointerup="release"
        @pointercancel="cancel"
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
          <rect
            v-if="selection"
            class="time-series__selection"
            :x="x(times[selection[0]] as number)"
            :y="0"
            :width="
              Math.max(2, x(times[selection[1]] as number) - x(times[selection[0]] as number))
            "
            :height="rise"
            data-test="chart-selection"
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
              :class="dashClass(line.texture)"
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
        :hint="hint"
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

/* The span that a drag or Shift and the arrow keys has picked. */
.time-series__selection {
  fill: rgb(var(--v-theme-primary));
  fill-opacity: 0.14;
  stroke: rgb(var(--v-theme-primary));
  stroke-width: 1;
  pointer-events: none;
}

/* A dot is ringed in the card's own color, so it stands clear of whatever it sits on. */
.time-series__dot {
  stroke: rgb(var(--v-theme-surface));
  stroke-width: 2;
}
</style>
