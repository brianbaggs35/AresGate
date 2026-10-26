import { layoutBars, type BarLayoutInput } from '@/charts/bars'

const base: BarLayoutInput = {
  orientation: 'horizontal',
  stacked: false,
  values: [[100, 50, 0]],
  categories: 3,
  length: 200,
  band: 36,
  max: 100,
}

describe('layoutBars', () => {
  it('grows horizontal bars from the left, as thick as the slot allows up to 24', () => {
    const { shapes, labels } = layoutBars(base)
    // The slot is 36 and keeps 8 of air, so the bar is 24 thick and has 6 above it.
    expect(shapes[0]?.path).toBe('M0,6H196A4,4 0 0 1 200,10V26A4,4 0 0 1 196,30H0Z')
    expect(shapes[1]?.path).toBe('M0,42H96A4,4 0 0 1 100,46V62A4,4 0 0 1 96,66H0Z')
    expect(labels).toEqual([
      { category: 0, value: 100, tip: 200, center: 18 },
      { category: 1, value: 50, tip: 100, center: 54 },
    ])
  })

  it('draws no bar for nothing, and one that can still be seen for very little', () => {
    const { shapes } = layoutBars({ ...base, values: [[0, 0.1, 0]] })
    expect(shapes).toHaveLength(1)
    expect(shapes[0]?.category).toBe(1)
    expect(shapes[0]?.path).toContain('H')
    expect(shapes[0]?.path.startsWith('M0,42')).toBe(true)
  })

  it('makes a bar thinner when the slot is small', () => {
    const { shapes } = layoutBars({ ...base, band: 20 })
    // 20 less 8 of air is 12 thick, which starts 4 down.
    expect(shapes[0]?.path).toBe('M0,4H196A4,4 0 0 1 200,8V12A4,4 0 0 1 196,16H0Z')
  })

  it('grows columns up from the bottom', () => {
    const { shapes } = layoutBars({
      ...base,
      orientation: 'vertical',
      band: 40,
      length: 100,
      values: [[100, 50]],
      categories: 2,
    })
    // A 24 wide column in a 40 wide slot is 8 in; 100 tall from the bottom of a 100 plot.
    expect(shapes[0]?.path).toBe('M8,100V4A4,4 0 0 1 12,0H28A4,4 0 0 1 32,4V100Z')
    expect(shapes[1]?.path).toBe('M48,100V54A4,4 0 0 1 52,50H68A4,4 0 0 1 72,54V100Z')
  })

  it('puts series side by side, sharing the slot, with a gap between them', () => {
    const { shapes, labels } = layoutBars({
      ...base,
      values: [
        [100, 0, 0],
        [50, 0, 0],
      ],
      band: 40,
    })
    // Two bars of 15 and a gap of 2 make 32 in a slot of 40: 4 above, then 4 below.
    expect(shapes.map(({ series }) => series)).toEqual([0, 1])
    expect(shapes[0]?.path.startsWith('M0,4')).toBe(true)
    expect(shapes[1]?.path.startsWith('M0,21')).toBe(true)
    // Not a number on every bar.
    expect(labels).toEqual([])
  })

  it('stacks series, a gap between segments and only the end of the stack rounded', () => {
    const { shapes, labels } = layoutBars({
      ...base,
      stacked: true,
      values: [
        [40, 0, 0],
        [20, 0, 0],
        [40, 0, 0],
      ],
      max: 100,
    })
    expect(shapes.map(({ series }) => series)).toEqual([0, 1, 2])
    // 40% of 200 is 80, less 2 of surface.
    expect(shapes[0]?.path).toBe('M0,6h78v24h-78Z')
    expect(shapes[1]?.path).toBe('M80,6h38v24h-38Z')
    expect(shapes[2]?.path).toBe('M120,6H196A4,4 0 0 1 200,10V26A4,4 0 0 1 196,30H120Z')
    expect(labels).toEqual([{ category: 0, value: 100, tip: 200, center: 18 }])
  })

  it('skips the series with nothing when stacking, and rounds the last that has something', () => {
    const { shapes } = layoutBars({
      ...base,
      stacked: true,
      values: [
        [40, 0, 0],
        [0, 0, 0],
      ],
    })
    expect(shapes).toHaveLength(1)
    expect(shapes[0]?.path).toContain('A4,4')
  })

  it('keeps a thin segment visible', () => {
    const { shapes } = layoutBars({
      ...base,
      stacked: true,
      values: [
        [100, 0, 0],
        [0.1, 0, 0],
        [100, 0, 0],
      ],
      max: 200.1,
    })
    // Just after the first segment's end: a sliver less than the gap is still a pixel wide.
    expect(shapes[1]?.path).toBe('M99.95,6h1v24h-1Z')
  })

  it('stacks columns upwards', () => {
    const { shapes } = layoutBars({
      ...base,
      orientation: 'vertical',
      stacked: true,
      band: 40,
      length: 100,
      categories: 1,
      values: [[50], [50]],
    })
    expect(shapes[0]?.path).toBe('M8,52h24v48h-24Z')
    expect(shapes[1]?.path).toBe('M8,50V4A4,4 0 0 1 12,0H28A4,4 0 0 1 32,4V50Z')
  })

  it('treats a series with fewer values than categories as zero for the rest', () => {
    const { shapes } = layoutBars({ ...base, values: [[100]] })
    expect(shapes).toHaveLength(1)
  })
})
