import {
  indexesWithin,
  isZoomed,
  marksWithin,
  readingRange,
  trimToSpan,
  useZoom,
} from '@/charts/zoom'
import type { ChartMark } from '@/charts/types'

const times = [0, 60_000, 120_000, 180_000, 240_000]
const series = [{ id: 'a', label: 'A', values: [1, null, 3, 4, 5] }]

describe('useZoom', () => {
  it('keeps the span the owner picked, either way round, and lets it go', () => {
    const { span, zoom, reset } = useZoom()
    expect(span.value).toBeNull()

    zoom(200, 100)
    expect(span.value).toEqual([100, 200])

    reset()
    expect(span.value).toBeNull()
  })
})

describe('indexesWithin', () => {
  it('is every moment with no span, and those inside it with one', () => {
    expect(indexesWithin(times, null)).toEqual([0, 1, 2, 3, 4])
    expect(indexesWithin(times, [60_000, 180_000])).toEqual([1, 2, 3])
  })

  it('is every moment again when the span holds fewer than two', () => {
    expect(indexesWithin(times, [61_000, 100_000])).toEqual([0, 1, 2, 3, 4])
    expect(indexesWithin(times, [60_000, 60_000])).toEqual([0, 1, 2, 3, 4])
  })
})

describe('trimToSpan', () => {
  it('gives each series the numbers of the moments kept, gaps as they were', () => {
    const trimmed = trimToSpan(times, series, [60_000, 180_000])

    expect(trimmed.times).toEqual([60_000, 120_000, 180_000])
    expect(trimmed.series).toEqual([{ id: 'a', label: 'A', values: [null, 3, 4] }])
  })

  it('gives all of it with no span', () => {
    const trimmed = trimToSpan(times, series, null)

    expect(trimmed.times).toBe(times)
    expect(trimmed.series).toEqual(series)
    expect(isZoomed(times, trimmed.times)).toBe(false)
    expect(isZoomed(times, [60_000])).toBe(true)
  })

  it('reads a series that is shorter than its moments as gaps', () => {
    const short = [{ id: 'a', label: 'A', values: [1] }]

    expect(trimToSpan(times, short, [0, 120_000]).series[0]?.values).toEqual([1, null, null])
  })
})

describe('marksWithin', () => {
  const mark = (time: number) => ({ id: time.toString(), time }) as ChartMark

  it('keeps those in the span, or all with none', () => {
    const marks = [mark(10), mark(50), mark(90)]

    expect(marksWithin(marks, [40, 100]).map(({ time }) => time)).toEqual([50, 90])
    expect(marksWithin(marks, null)).toHaveLength(3)
  })
})

describe('readingRange', () => {
  it('runs from a reading to the next, as the logs search writes it', () => {
    expect(readingRange(times, 60_000)).toEqual({
      start: '1970-01-01T00:01:00Z',
      end: '1970-01-01T00:02:00Z',
    })
  })

  it('lasts as long as the one before for the last reading', () => {
    expect(readingRange(times, 240_000).end).toBe('1970-01-01T00:05:00Z')
  })

  it('lasts a minute for a reading that stands alone', () => {
    expect(readingRange([300_000], 300_000).end).toBe('1970-01-01T00:06:00Z')
  })
})
