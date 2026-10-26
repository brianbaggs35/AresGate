import { barPath } from '@/charts/paths'
import { linear } from '@/charts/scales'

/** How bars are drawn, the same on every chart: never thicker than this, with this much surface
 * between bars that touch, and this round at the end the data reaches. */
export const THICKEST = 24
export const GAP = 2
const RADIUS = 4
/** The air a category's slot keeps around its bars at least. */
const AIR = 8
/** A bar for a value above nothing is never shorter than this, so it can still be seen. */
const SHORTEST = 4

export interface BarLayoutInput {
  orientation: 'horizontal' | 'vertical'
  stacked: boolean
  /** The values of each series being drawn, one for each category. */
  values: readonly (readonly number[])[]
  categories: number
  /** How far the value axis goes in pixels, which is where `max` is. */
  length: number
  /** The room of one category along the other axis, in pixels. */
  band: number
  max: number
}

export interface BarShape {
  series: number
  category: number
  path: string
}

/** The value written at the end of a bar, or of a stack. */
export interface BarLabel {
  category: number
  value: number
  /** How far along the value axis the bar ends, and where across it the bar's middle is. */
  tip: number
  center: number
}

/**
 * Where every bar goes. Bars grow from the left (horizontal) or the bottom (vertical) of the
 * plot, with the plot's own corner as 0,0. Only the end the data reaches is rounded: a bar's own,
 * or the last segment of a stack. Series are drawn side by side, or one on top of the other when
 * stacked, with a gap of surface between segments.
 */
export function layoutBars(input: BarLayoutInput): { shapes: BarShape[]; labels: BarLabel[] } {
  const { orientation, stacked, values, categories, length, band, max } = input
  const horizontal = orientation === 'horizontal'
  const scale = linear([0, max], [0, length])
  const groups = stacked ? 1 : Math.max(1, values.length)
  const thickness = Math.max(2, Math.min(THICKEST, (band - AIR - (groups - 1) * GAP) / groups))
  const used = groups * thickness + (groups - 1) * GAP
  const shapes: BarShape[] = []
  const labels: BarLabel[] = []

  const draw = (
    series: number,
    category: number,
    across: number,
    from: number,
    size: number,
    round: boolean,
  ) => {
    const end = round ? (horizontal ? 'right' : 'top') : null
    const path = horizontal
      ? barPath(from, across, size, thickness, RADIUS, end)
      : barPath(across, length - from - size, thickness, size, RADIUS, end)
    shapes.push({ series, category, path })
  }

  for (let category = 0; category < categories; category++) {
    const start = category * band + (band - used) / 2
    const at = (series: number) => values[series]?.[category] ?? 0
    if (stacked) {
      const drawn = values.map((_, series) => series).filter((series) => at(series) > 0)
      let total = 0
      for (const series of drawn) {
        const from = scale(total)
        total += at(series)
        const last = series === drawn[drawn.length - 1]
        draw(
          series,
          category,
          start,
          from,
          Math.max(1, scale(total) - from - (last ? 0 : GAP)),
          last,
        )
      }
      if (total > 0)
        labels.push({ category, value: total, tip: scale(total), center: start + thickness / 2 })
    } else {
      values.forEach((_, series) => {
        const value = at(series)
        if (value <= 0) return
        const across = start + series * (thickness + GAP)
        const size = Math.max(SHORTEST, scale(value))
        draw(series, category, across, 0, size, true)
        if (values.length === 1)
          labels.push({ category, value, tip: size, center: across + thickness / 2 })
      })
    }
  }
  return { shapes, labels }
}
