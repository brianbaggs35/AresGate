/** A point on a chart: where along the x axis, and where up the y axis. A `null` y is a gap in
 * the data, not a zero. */
export type Point = readonly [x: number, y: number | null]

type Located = readonly [x: number, y: number]

const round = (value: number) => Math.round(value * 100) / 100
const at = (x: number, y: number) => `${round(x)},${round(y)}`

/** The stretches of points between gaps. */
function runs(points: readonly Point[]): Located[][] {
  const found: Located[][] = []
  let current: Located[] | null = null
  for (const [x, y] of points) {
    if (y === null) {
      current = null
    } else if (current) {
      current.push([x, y])
    } else {
      current = [[x, y]]
      found.push(current)
    }
  }
  return found
}

/** A line through the points, broken where the data has a gap. A point on its own becomes a dot
 * (with a round line cap). */
export function linePath(points: readonly Point[]): string {
  return runs(points)
    .map(([first, ...rest]) => {
      const start = `M${at(...(first as Located))}`
      if (!rest.length) return `${start}L${at(...(first as Located))}`
      return start + rest.map((point) => `L${at(...point)}`).join('')
    })
    .join('')
}

/** The area between a line and the baseline, one shape for each stretch between gaps. */
export function areaPath(points: readonly Point[], baseline: number): string {
  return runs(points)
    .map((run) => {
      const [first, last] = [run[0] as Located, run.at(-1) as Located]
      const along = run.map((point) => `L${at(...point)}`).join('')
      return `M${at(first[0], baseline)}${along}L${at(last[0], baseline)}Z`
    })
    .join('')
}

/** Where a bar grows to: its rounded end is at the right of a horizontal bar and at the top of a
 * column. */
export type BarEnd = 'right' | 'top'

/** A bar, square at its baseline and with a rounded data end of at most `radius` (less on a bar
 * too thin or too short for it). With no `end` it is a plain rectangle. */
export function barPath(
  x: number,
  y: number,
  width: number,
  height: number,
  radius: number,
  end: BarEnd | null,
): string {
  const thickness = end === 'right' ? height : width
  const length = end === 'right' ? width : height
  const r = end === null ? 0 : Math.min(radius, thickness / 2, length)
  if (r <= 0) return `M${at(x, y)}h${round(width)}v${round(height)}h${round(-width)}Z`
  const [right, bottom] = [x + width, y + height]
  const arc = `A${r},${r} 0 0 1`
  if (end === 'right') {
    return `M${at(x, y)}H${round(right - r)}${arc} ${at(right, y + r)}V${round(bottom - r)}${arc} ${at(right - r, bottom)}H${round(x)}Z`
  }
  return `M${at(x, bottom)}V${round(y + r)}${arc} ${at(x + r, y)}H${round(right - r)}${arc} ${at(right, y + r)}V${round(bottom)}Z`
}
