import { areaPath, barPath, linePath } from '@/charts/paths'

describe('linePath', () => {
  it('goes through the points in order', () => {
    expect(
      linePath([
        [0, 10],
        [5, 20.126],
        [10, 15],
      ]),
    ).toBe('M0,10L5,20.13L10,15')
  })

  it('breaks where the data has a gap instead of drawing a zero', () => {
    expect(
      linePath([
        [0, 10],
        [5, 20],
        [10, null],
        [15, null],
        [20, 5],
        [25, 6],
      ]),
    ).toBe('M0,10L5,20M20,5L25,6')
  })

  it('draws a point on its own as a dot (a zero-length line with round caps)', () => {
    expect(
      linePath([
        [0, null],
        [5, 7],
        [10, null],
      ]),
    ).toBe('M5,7L5,7')
  })

  it('draws nothing for nothing', () => {
    expect(linePath([])).toBe('')
    expect(linePath([[0, null]])).toBe('')
  })
})

describe('areaPath', () => {
  it('closes each stretch down to the baseline', () => {
    expect(
      areaPath(
        [
          [0, 10],
          [5, 20],
          [10, null],
          [15, 3],
          [20, 4],
        ],
        50,
      ),
    ).toBe('M0,50L0,10L5,20L5,50ZM15,50L15,3L20,4L20,50Z')
  })

  it('has no area where there is no data', () => {
    expect(areaPath([[0, null]], 50)).toBe('')
  })
})

describe('barPath', () => {
  it('rounds only the end the data reaches', () => {
    expect(barPath(0, 0, 100, 20, 4, 'right')).toBe('M0,0H96A4,4 0 0 1 100,4V16A4,4 0 0 1 96,20H0Z')
    expect(barPath(10, 0, 20, 100, 4, 'top')).toBe(
      'M10,100V4A4,4 0 0 1 14,0H26A4,4 0 0 1 30,4V100Z',
    )
  })

  it('is a plain rectangle with no round end', () => {
    expect(barPath(0, 0, 100, 20, 4, null)).toBe('M0,0h100v20h-100Z')
  })

  it('rounds less on a bar too thin or too short for it', () => {
    expect(barPath(0, 0, 100, 4, 4, 'right')).toContain('A2,2')
    expect(barPath(0, 0, 3, 20, 4, 'right')).toContain('A3,3')
    expect(barPath(0, 0, 20, 3, 4, 'top')).toContain('A3,3')
  })

  it('is a rectangle when there is no length to round', () => {
    expect(barPath(0, 0, 0, 20, 4, 'right')).toBe('M0,0h0v20h0Z')
  })
})
