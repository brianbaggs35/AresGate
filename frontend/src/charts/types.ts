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
