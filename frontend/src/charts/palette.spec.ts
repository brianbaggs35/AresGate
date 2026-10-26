import { seriesColor, severityColor, STEPS, stepColor } from '@/charts/palette'

describe('palette', () => {
  it('gives each series the next hue in order', () => {
    expect(seriesColor(0)).toBe('var(--chart-1)')
    expect(seriesColor(7)).toBe('var(--chart-8)')
  })

  it('gives every series past the eighth the same neutral, never a ninth hue', () => {
    expect(seriesColor(8)).toBe('var(--chart-other)')
    expect(seriesColor(40)).toBe('var(--chart-other)')
  })

  it('names a severity’s color', () => {
    expect(severityColor('critical')).toBe('var(--chart-severity-critical)')
  })

  it('has five steps of the sequential scale', () => {
    expect(STEPS).toBe(5)
    expect(stepColor(1)).toBe('var(--chart-step-1)')
    expect(stepColor(STEPS)).toBe('var(--chart-step-5)')
  })
})
