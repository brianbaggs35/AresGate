import {
  BellRing,
  Bot,
  ChartColumn,
  HeartPulse,
  LayoutDashboard,
  MonitorSmartphone,
  Network,
  Workflow,
  Plug,
  ScanSearch,
  ScrollText,
  Settings,
  ShieldAlert,
  Siren,
} from '@lucide/vue'
import type { IconProps } from 'vuetify'

/** A place in the menu. */
export interface NavItem {
  /** The name of the route it opens. */
  route: string
  title: string
  icon: NonNullable<IconProps['icon']>
  /** More words that find it in the command palette, which are not shown. */
  keywords?: string
}

/** A phone's bottom bar has room for this many destinations before it gets cramped. */
export const BOTTOM_BAR_LIMIT = 5

/** The menu, in order. A page that should be in it adds itself here. */
export const navItems: readonly NavItem[] = [
  { route: 'home', title: 'Dashboard', icon: LayoutDashboard },
  {
    route: 'threats',
    title: 'Threats',
    icon: ShieldAlert,
    keywords: 'attacks real noise background suspects kinds families lanes',
  },
  { route: 'incidents', title: 'Incidents', icon: Siren },
  { route: 'assistant', title: 'Assistant', icon: Bot },
  {
    route: 'agents',
    title: 'Agents',
    icon: Workflow,
    keywords: 'hunter analyst scanner health watch automation schedule run graph langgraph',
  },
  { route: 'logs', title: 'Logs', icon: ScrollText },
  { route: 'assets', title: 'Assets', icon: MonitorSmartphone },
  { route: 'integrations', title: 'Integrations', icon: Plug },
  {
    route: 'threat-intelligence',
    title: 'Threat intelligence',
    icon: ScanSearch,
    keywords: 'virustotal lookup reputation address domain url malicious search',
  },
  { route: 'interfaces', title: 'Interfaces', icon: Network },
  {
    route: 'ai-usage',
    title: 'AI usage',
    icon: ChartColumn,
    keywords: 'spending cost money tokens limit budget level',
  },
  { route: 'alerts', title: 'Alerts', icon: BellRing },
  { route: 'status', title: 'Status', icon: HeartPulse },
  { route: 'settings', title: 'Settings', icon: Settings },
]

/** What the bottom bar of a phone holds: the places in the menu while they fit, and otherwise as
 * many as leave room for a "More" button, with the rest behind it. */
export function bottomBar(
  items: readonly NavItem[] = navItems,
  limit: number = BOTTOM_BAR_LIMIT,
): { bar: readonly NavItem[]; more: readonly NavItem[] } {
  if (items.length <= limit) return { bar: items, more: [] }
  return { bar: items.slice(0, limit - 1), more: items.slice(limit - 1) }
}
