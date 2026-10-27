import type { ChartMark } from '@/charts/types'

/** Flags this many pixels apart, or closer, are drawn as one. */
export const FLAG_SIZE = 28

/** What one flag stands for: a mark, or several that sit too close to tell apart. */
export interface Flag {
  /** Where it is, in pixels along the plot. */
  x: number
  /** The marks it stands for, the one that matters most first. */
  marks: readonly [ChartMark, ...ChartMark[]]
}

/**
 * Puts each mark at the pixel its time has, keeping those that would overlap together as one flag
 * that stands for all of them, at the place of the one that matters most. A mark outside the
 * chart's time is put at the nearest end, so one that began before it or after the last reading is
 * not lost. `toX` maps a time to a pixel along the plot.
 */
export function placeMarks(
  marks: readonly ChartMark[],
  [first, last]: readonly [number, number],
  toX: (time: number) => number,
): Flag[] {
  const clamp = (time: number) => Math.min(last, Math.max(first, time))
  const groups: { x: number; marks: ChartMark[] }[] = []
  for (const mark of [...marks].sort((a, b) => a.time - b.time || a.id.localeCompare(b.id))) {
    const x = toX(clamp(mark.time))
    const group = groups.at(-1)
    if (group && x - group.x < FLAG_SIZE) group.marks.push(mark)
    else groups.push({ x, marks: [mark] })
  }
  return groups.map(({ marks: members }) => {
    const [top, ...rest] = [...members].sort((a, b) => b.weight - a.weight || a.time - b.time)
    return { x: toX(clamp((top as ChartMark).time)), marks: [top as ChartMark, ...rest] }
  })
}

/**
 * The index of the reading a time belongs to: the last one that is not after it, or the first for
 * a time before them all.
 */
export function readingOf(times: readonly number[], time: number): number {
  const after = times.findIndex((reading) => reading > time)
  return Math.max(0, (after === -1 ? times.length : after) - 1)
}
