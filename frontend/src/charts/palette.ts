import type { Severity } from '@/severity'

/** The colors a chart draws with are CSS variables (src/styles/charts.scss), so each theme has
 * its own steps of the same hues. A series takes the next in this fixed order, never a color
 * chosen for it, so the same thing is the same color on every chart. */
const SERIES = 8

/** The color of the `index`th series (from 0). There are eight hues that can be told apart;
 * past them everything is "other", a neutral gray. Fold a longer tail into one "Other" series
 * rather than invent hues. */
export function seriesColor(index: number): string {
  return index < SERIES ? `var(--chart-${(index + 1).toString()})` : 'var(--chart-other)'
}

/** The color of a severity. Besides the hue, anything that shows one also shows its icon and
 * its name (`SEVERITY` in src/severity.ts). */
export function severityColor(severity: Severity): string {
  return `var(--chart-severity-${severity})`
}

/** How many steps the sequential scale has, from `--chart-step-1` (the least) to the last. */
export const STEPS = 5

/** The color of a step of the sequential scale, 1 to `STEPS`. */
export function stepColor(step: number): string {
  return `var(--chart-step-${step.toString()})`
}
