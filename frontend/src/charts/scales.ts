const HOUR = 3_600_000
const DAY = 24 * HOUR

/** Maps a value in `domain` to its place in `range`. When the domain is a single value, which has
 * no extent, everything goes to the middle. */
export function linear(
  domain: readonly [number, number],
  range: readonly [number, number],
): (value: number) => number {
  const [from, to] = domain
  const [start, end] = range
  const extent = to - from
  return (value) =>
    extent === 0 ? (start + end) / 2 : start + ((value - from) / extent) * (end - start)
}

/** The nearest of 1, 2, 5 and 10 times a power of ten that is at least `raw`. */
function niceStep(raw: number): number {
  const power = 10 ** Math.floor(Math.log10(raw))
  const fraction = raw / power
  if (fraction <= 1) return power
  if (fraction <= 2) return 2 * power
  if (fraction <= 5) return 5 * power
  return 10 * power
}

/** The gridlines of a value axis from zero: clean steps (0, 5, 10, 15) and the top one, which is
 * at or above `max`. About `target` steps, fewer when the data is small. */
export function valueAxis(max: number, target = 4): { ticks: number[]; top: number } {
  if (max <= 0) return { ticks: [0, 1], top: 1 }
  const step = niceStep(max / target)
  const count = Math.ceil(max / step - 1e-9)
  const ticks = Array.from({ length: count + 1 }, (_, index) =>
    Number((index * step).toPrecision(12)),
  )
  return { ticks, top: ticks[count] as number }
}

/** How far apart ticks may be on a time axis, from a minute to a week. */
const TIME_STEPS = [
  60_000,
  5 * 60_000,
  15 * 60_000,
  30 * 60_000,
  HOUR,
  3 * HOUR,
  6 * HOUR,
  12 * HOUR,
  DAY,
  7 * DAY,
]

/** Where the ticks of a time axis between two moments (milliseconds) go: on whole minutes,
 * hours or days of the viewer's own clock, at most about `target` of them. */
export function timeTicks(start: number, end: number, target: number): number[] {
  const step = TIME_STEPS.find((candidate) => (end - start) / candidate <= target) ?? 7 * DAY
  // Whole hours and days are those of the viewer's clock, not of UTC.
  const offset = -new Date(start).getTimezoneOffset() * 60_000
  const ticks: number[] = []
  for (let tick = Math.ceil((start + offset) / step) * step - offset; tick <= end; tick += step) {
    ticks.push(tick)
  }
  return ticks
}

/** A time axis tick as people read it: the hour while the axis is a day or two long, the date
 * when it is longer. */
export function formatTick(moment: number, span: number, locale?: string): string {
  const options: Intl.DateTimeFormatOptions =
    span <= 2 * DAY ? { timeStyle: 'short' } : { month: 'short', day: 'numeric' }
  return new Intl.DateTimeFormat(locale, options).format(moment)
}

/** The step, from 1 to `steps`, of a sequential scale that a value falls in, with 1 for anything
 * above nothing. Nothing at all has no step. */
export function sequentialStep(value: number, max: number, steps: number): number | null {
  if (value <= 0 || max <= 0) return null
  return Math.min(steps, Math.max(1, Math.ceil((value / max) * steps)))
}

/** The position in `sorted` (ascending) whose value is nearest to `target`; the earlier when
 * they are as near. There must be at least one. */
export function nearest(sorted: readonly number[], target: number): number {
  let low = 0
  let high = sorted.length - 1
  while (low < high) {
    const middle = (low + high) >> 1
    if ((sorted[middle] as number) < target) low = middle + 1
    else high = middle
  }
  if (low > 0 && target - (sorted[low - 1] as number) <= (sorted[low] as number) - target)
    return low - 1
  return low
}
