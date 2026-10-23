import { CircleAlert, Info, OctagonAlert, Siren, TriangleAlert } from '@lucide/vue'
import type { IconProps } from 'vuetify'

/** How serious something is, from least to most. Alerts, threats and incidents all use these. */
export const SEVERITIES = ['info', 'low', 'medium', 'high', 'critical'] as const
export type Severity = (typeof SEVERITIES)[number]

interface Look {
  label: string
  /** A theme color. */
  color: string
  icon: NonNullable<IconProps['icon']>
  /** The most serious stand out from the rest: solid where the others are tinted. */
  variant: 'tonal' | 'flat'
}

/** Never just a color: each also has its own icon and its name, for people who can't tell them
 * apart. */
export const SEVERITY: Readonly<Record<Severity, Look>> = {
  info: { label: 'Info', color: 'info', icon: Info, variant: 'tonal' },
  low: { label: 'Low', color: 'success', icon: CircleAlert, variant: 'tonal' },
  medium: { label: 'Medium', color: 'warning', icon: TriangleAlert, variant: 'tonal' },
  high: { label: 'High', color: 'error', icon: OctagonAlert, variant: 'tonal' },
  critical: { label: 'Critical', color: 'error', icon: Siren, variant: 'flat' },
}
