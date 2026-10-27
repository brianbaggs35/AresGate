import { placeMarks, readingOf, FLAG_SIZE } from '@/charts/marks'
import type { ChartMark } from '@/charts/types'

const mark = (id: string, time: number, weight = 1): ChartMark => ({
  id,
  time,
  weight,
  label: id,
  heading: id,
  rows: [{ label: id, value: '1' }],
  color: 'red',
  icon: 'x',
  to: '/',
})

/** A hundred pixels for a hundred units of time. */
const place = (marks: ChartMark[]) => placeMarks(marks, [0, 100], (time) => time)

describe('placeMarks', () => {
  it('puts a flag at the pixel of each mark, in the order of their times', () => {
    const flags = place([mark('b', 80), mark('a', 10), mark('c', 50)])

    expect(flags.map(({ x, marks }) => [x, marks.map(({ id }) => id)])).toEqual([
      [10, ['a']],
      [50, ['c']],
      [80, ['b']],
    ])
  })

  it('keeps marks too close to tell apart as one flag, at the place of the one that matters', () => {
    const flags = place([mark('near', 10, 1), mark('main', 20, 5), mark('far', 90, 1)])

    expect(flags).toHaveLength(2)
    expect(flags[0]?.x).toBe(20)
    expect(flags[0]?.marks.map(({ id }) => id)).toEqual(['main', 'near'])
    expect(flags[1]?.marks.map(({ id }) => id)).toEqual(['far'])
  })

  it('keeps those that are just far enough apart separate', () => {
    expect(place([mark('a', 0), mark('b', FLAG_SIZE)])).toHaveLength(2)
    expect(place([mark('a', 0), mark('b', FLAG_SIZE - 1)])).toHaveLength(1)
  })

  it('puts the earlier first when two matter the same, and breaks a tie of times by name', () => {
    const [flag] = place([mark('late', 12, 3), mark('early', 10, 3)])
    expect(flag?.marks.map(({ id }) => id)).toEqual(['early', 'late'])

    const [tied] = place([mark('b', 10), mark('a', 10)])
    expect(tied?.marks.map(({ id }) => id)).toEqual(['a', 'b'])
  })

  it('puts a mark outside the chart at the nearest end', () => {
    const flags = place([mark('before', -50), mark('after', 500)])

    expect(flags.map(({ x }) => x)).toEqual([0, 100])
  })

  it('has no flags for no marks', () => {
    expect(place([])).toEqual([])
  })
})

describe('readingOf', () => {
  const times = [10, 20, 30]

  it('is the last reading that is not after the time', () => {
    expect(readingOf(times, 20)).toBe(1)
    expect(readingOf(times, 25)).toBe(1)
    expect(readingOf(times, 99)).toBe(2)
  })

  it('is the first for a time before them all', () => {
    expect(readingOf(times, 1)).toBe(0)
  })
})
