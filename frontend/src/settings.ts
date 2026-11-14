import {
  ClipboardCheck,
  Database,
  Funnel,
  Gavel,
  Workflow,
  History,
  Hourglass,
  MonitorSmartphone,
  ShieldAlert,
  Sparkles,
  UserRound,
} from '@lucide/vue'
import type { IconProps } from 'vuetify'

/** A page of the Settings area. */
export interface SettingsSection {
  /** What its link is called in tests, and the end of its address. */
  key: string
  /** The name of the route it opens. */
  route: string
  title: string
  icon: NonNullable<IconProps['icon']>
}

/** The Settings area's list, in order. A settings page adds itself here, so it is in the list
 * on a computer and the tabs on a phone. */
export const settingsSections: readonly SettingsSection[] = [
  { key: 'account', route: 'settings-account', title: 'Account', icon: UserRound },
  { key: 'sign-ins', route: 'settings-sign-ins', title: 'Sign-ins', icon: MonitorSmartphone },
  { key: 'activity', route: 'settings-activity', title: 'Activity', icon: History },
  { key: 'verdicts', route: 'settings-verdicts', title: 'Verdicts', icon: Gavel },
  {
    key: 'noise-filters',
    route: 'settings-noise-filters',
    title: 'Noise filters',
    icon: Funnel,
  },
  {
    key: 'threat-detection',
    route: 'settings-threat-detection',
    title: 'Threat detection',
    icon: ShieldAlert,
  },
  { key: 'review', route: 'settings-review', title: 'Review', icon: ClipboardCheck },
  { key: 'ai', route: 'settings-ai', title: 'AI', icon: Sparkles },
  { key: 'agents', route: 'settings-agents', title: 'Agents', icon: Workflow },
  { key: 'data', route: 'settings-data', title: 'Data', icon: Database },
  { key: 'retention', route: 'settings-retention', title: 'Retention', icon: Hourglass },
]
