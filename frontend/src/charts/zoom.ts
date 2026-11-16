import { ref, type Ref } from 'vue'

import type { ChartMark } from '@/charts/types'

/** A stretch of time, in milliseconds since 1970: the first moment and the last. */
export type Span = readonly [from: number, to: number]

/** What a page keeps of a zoom: the span its charts are narrowed to (null when they are not), and
 * how to narrow them or put them back. A page that changes its own range puts the zoom back. */
export interface Zoom {
  span: Ref<Span | null>
  zoom: (from: number, to: number) => void
  reset: () => void
}

export function useZoom(): Zoom {
  const span = ref<Span | null>(null)
  return {
    span,
    zoom(from, to) {
      span.value = [Math.min(from, to), Math.max(from, to)]
    },
    reset() {
      span.value = null
    },
  }
}

/** One series of numbers, a value for each moment. */
interface Values {
  values: readonly (number | null)[]
}

/**
 * The places (from 0) of the moments within a span: all of them with no span. A span that holds
 * fewer than two moments is not a stretch to look at, so it also gives all of them: a zoom never
 * leaves a chart with nothing to draw.
 */
export function indexesWithin(times: readonly number[], span: Span | null): number[] {
  const all = times.map((_, index) => index)
  if (!span) return all
  const kept = all.filter(
    (index) => (times[index] as number) >= span[0] && (times[index] as number) <= span[1],
  )
  return kept.length < 2 ? all : kept
}

/** The moments within a span and each series' numbers for them, all of them with no span. */
export function trimToSpan<T extends Values>(
  times: readonly number[],
  series: readonly T[],
  span: Span | null,
): { times: readonly number[]; series: T[] } {
  const kept = indexesWithin(times, span)
  if (kept.length === times.length) return { times, series: [...series] }
  return {
    times: kept.map((index) => times[index] as number),
    series: series.map((each) => ({
      ...each,
      values: kept.map((index) => each.values[index] ?? null),
    })),
  }
}

/** Whether a zoom has narrowed what the chart is given, which is what its *Reset zoom* is for. */
export function isZoomed(times: readonly number[], trimmed: readonly number[]): boolean {
  return trimmed.length < times.length
}

/** The marks that fall within the span, so a chart narrowed to it flags only what happened in it. */
export function marksWithin(marks: readonly ChartMark[], span: Span | null): ChartMark[] {
  return span ? marks.filter(({ time }) => time >= span[0] && time <= span[1]) : [...marks]
}

/** A moment as the Logs search writes one. */
const written = (ms: number) => new Date(ms).toISOString().replace('.000Z', 'Z')

/** The stretch of time a reading stands for, from it to the next (or as long again after the last),
 * written as the Logs search's `since:` and `before:` take it. */
export function readingRange(
  times: readonly number[],
  time: number,
): { start: string; end: string } {
  const index = times.indexOf(time)
  const next = times[index + 1]
  const before = times[index - 1]
  const width = next === undefined ? time - (before ?? time - 60_000) : next - time
  return { start: written(time), end: written(time + Math.max(width, 1000)) }
}
