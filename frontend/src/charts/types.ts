import type { RouteLocationRaw } from 'vue-router'
import type { IconProps } from 'vuetify'

/** One entry of a chart's legend: what a color stands for. */
export interface LegendItem {
  id: string
  label: string
  /** A CSS color, usually one of the chart variables (see `seriesColor`). */
  color: string
  /** The mark the series is drawn with: a short line for lines, a square for bars and areas. */
  shape: 'line' | 'square'
  /** Shown beside the label for what must never rest on color alone, such as a severity. */
  icon?: NonNullable<IconProps['icon']>
}

/** A chart's numbers as a table, which is how anyone who can't use the chart reads them. */
export interface ChartTableData {
  columns: readonly string[]
  rows: readonly (readonly (string | number)[])[]
}

/** One line of a tooltip: the value first, then what it is the value of. */
export interface TooltipRow {
  label: string
  value: string
  color?: string
  shape?: LegendItem['shape']
}

/** Something that happened at a moment on a time axis, flagged above the chart with a link to it. */
export interface ChartMark {
  id: string
  /** When, in milliseconds since 1970. */
  time: number
  /** How much it matters, to choose which of several flags that sit on top of each other is shown
   * and says what it is. */
  weight: number
  /** What a screen reader says, which is also what its table row says. */
  label: string
  /** The readout over it: when it was, then a row for each fact. */
  heading: string
  /** At least one: a flag that stands for several shows the first of each. */
  rows: readonly [TooltipRow, ...TooltipRow[]]
  /** A CSS color, and an icon, for what must never rest on color alone. */
  color: string
  icon: NonNullable<IconProps['icon']>
  /** Where the flag leads. */
  to: RouteLocationRaw
}
