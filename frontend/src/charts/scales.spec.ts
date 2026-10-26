import { formatTick, linear, nearest, sequentialStep, timeTicks, valueAxis } from '@/charts/scales'

describe('linear', () => {
  it('maps the domain onto the range, in either direction', () => {
    expect(linear([0, 10], [0, 100])(2.5)).toBe(25)
    expect(linear([0, 10], [100, 0])(2.5)).toBe(75)
    expect(linear([5, 15], [0, 100])(5)).toBe(0)
  })

  it('puts a domain with no extent in the middle of the range', () => {
    expect(linear([3, 3], [0, 100])(3)).toBe(50)
  })
})

describe('valueAxis', () => {
  it('has no lines between whole numbers for counts', () => {
    expect(valueAxis(2, 4, true)).toEqual({ ticks: [0, 1, 2], top: 2 })
    expect(valueAxis(1, 4, true)).toEqual({ ticks: [0, 1], top: 1 })
    expect(valueAxis(3, 4, true)).toEqual({ ticks: [0, 1, 2, 3], top: 3 })
    // Larger counts are as they always were.
    expect(valueAxis(100, 4, true)).toEqual(valueAxis(100))
    // And others have as many lines as they need.
    expect(valueAxis(2)).toEqual({ ticks: [0, 0.5, 1, 1.5, 2], top: 2 })
  })

  it.each([
    [0, [0, 1], 1],
    [-4, [0, 1], 1],
    [1, [0, 0.5, 1], 1],
    [7, [0, 2, 4, 6, 8], 8],
    [12_408, [0, 5000, 10_000, 15_000], 15_000],
    [80, [0, 20, 40, 60, 80], 80],
    [81, [0, 50, 100], 100],
    [0.3, [0, 0.1, 0.2, 0.3], 0.3],
  ])('goes in clean steps over %d', (max, ticks, top) => {
    expect(valueAxis(max)).toEqual({ ticks, top })
  })

  it('aims for the steps it is asked for', () => {
    expect(valueAxis(100, 2).ticks).toEqual([0, 50, 100])
  })
})

describe('timeTicks', () => {
  const at = (hour: number, minute = 0, day = 26) => new Date(2026, 9, day, hour, minute).getTime()

  it('puts ticks on whole hours of the viewer’s own clock', () => {
    expect(timeTicks(at(9, 30), at(14, 30), 6)).toEqual([at(10), at(11), at(12), at(13), at(14)])
  })

  it('takes bigger steps over a longer time', () => {
    expect(timeTicks(at(0), at(23), 4)).toEqual([at(0), at(6), at(12), at(18)])
  })

  it('puts ticks on midnights over days', () => {
    expect(timeTicks(at(12, 0, 20), at(12, 0, 26), 6)).toEqual([
      at(0, 0, 21),
      at(0, 0, 22),
      at(0, 0, 23),
      at(0, 0, 24),
      at(0, 0, 25),
      at(0, 0, 26),
    ])
  })

  it('never goes past a week between ticks', () => {
    const ticks = timeTicks(at(0, 0, 1), at(0, 0, 31), 2)
    expect(ticks.length).toBeGreaterThan(2)
    expect(ticks[1]! - ticks[0]!).toBe(7 * 86_400_000)
  })
})

describe('formatTick', () => {
  const moment = new Date(2026, 9, 26, 18, 5).getTime()

  it('says the time of day over a day or two', () => {
    expect(formatTick(moment, 3_600_000, 'en-US')).toMatch(/6:05\sPM/)
    expect(formatTick(moment, 2 * 86_400_000, 'en-US')).toMatch(/6:05\sPM/)
  })

  it('says the date over longer', () => {
    expect(formatTick(moment, 3 * 86_400_000, 'en-US')).toBe('Oct 26')
  })
})

describe('sequentialStep', () => {
  it.each([
    [0, null],
    [-1, null],
    [1, 1],
    [20, 1],
    [21, 2],
    [50, 3],
    [100, 5],
    [150, 5],
  ])('puts %d of 100 on step %s of five', (value, step) => {
    expect(sequentialStep(value, 100, 5)).toBe(step)
  })

  it('has no steps when there is nothing to scale by', () => {
    expect(sequentialStep(5, 0, 5)).toBeNull()
  })
})

describe('nearest', () => {
  const times = [10, 20, 30, 40]

  it('finds the position whose value is closest', () => {
    expect(nearest(times, 21)).toBe(1)
    expect(nearest(times, 29)).toBe(2)
    expect(nearest(times, 34)).toBe(2)
    expect(nearest(times, 36)).toBe(3)
  })

  it('takes the earlier of two that are as near', () => {
    expect(nearest(times, 25)).toBe(1)
  })

  it('stops at the ends', () => {
    expect(nearest(times, -100)).toBe(0)
    expect(nearest(times, 100)).toBe(3)
    expect(nearest([7], 100)).toBe(0)
  })
})
