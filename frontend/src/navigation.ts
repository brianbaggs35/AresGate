import {
  BellRing,
  Bot,
  ChartColumn,
  HeartPulse,
  LayoutDashboard,
  LifeBuoy,
  MonitorSmartphone,
  Network,
  Radar,
  Workflow,
  Plug,
  ScanSearch,
  ClipboardCheck,
  ScrollText,
  Settings,
  ShieldAlert,
  ShieldCheck,
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
  /** On a phone it is behind the More button, though it would fit in the bottom bar, to leave the
   * bar for the places that are used most. */
  behindMore?: boolean
  /** The heading it is under in the menu. */
  category: NavCategory
}

/** A phone's bottom bar has room for this many destinations before it gets cramped. */
export const BOTTOM_BAR_LIMIT = 5

/** The headings the menu is divided under, in the order they appear. */
export const NAV_CATEGORIES = [
  { key: 'overview', title: 'Overview' },
  { key: 'security', title: 'Security' },
  { key: 'ai', title: 'AI' },
  { key: 'network', title: 'Network' },
  { key: 'system', title: 'System' },
] as const

export type NavCategory = (typeof NAV_CATEGORIES)[number]['key']

/** The menu, in order, each place under its heading. The places of a heading are together, and a
 * page that should be in the menu adds itself here, under the heading it belongs to. */
export const navItems: readonly NavItem[] = [
  { route: 'home', title: 'Dashboard', icon: LayoutDashboard, category: 'overview' },
  {
    route: 'threats',
    title: 'Threats',
    icon: ShieldAlert,
    keywords: 'attacks real noise background suspects kinds families lanes',
    category: 'security',
  },
  { route: 'incidents', title: 'Incidents', icon: Siren, category: 'security' },
  {
    route: 'incident-response',
    title: 'Incident response',
    icon: LifeBuoy,
    keywords: 'responded banned blocked ban crowdsec firewall suricata answered waiting stopped',
    behindMore: true,
    category: 'security',
  },
  {
    route: 'review',
    title: 'Review',
    icon: ClipboardCheck,
    keywords: 'ai decisions agree disagree approve reason trust auto decide waiting',
    category: 'security',
  },
  { route: 'alerts', title: 'Alerts', icon: BellRing, category: 'security' },
  {
    route: 'trust',
    title: 'Trust',
    icon: ShieldCheck,
    keywords: 'safe allow whitelist allowlist known good false positive camera mark trusted',
    category: 'security',
  },
  {
    route: 'threat-intelligence',
    title: 'Threat intelligence',
    icon: ScanSearch,
    keywords: 'virustotal lookup reputation address domain url malicious search',
    category: 'security',
  },
  { route: 'assistant', title: 'Assistant', icon: Bot, category: 'ai' },
  {
    route: 'agents',
    title: 'Agents',
    icon: Workflow,
    keywords: 'hunter analyst scanner health watch automation schedule run graph langgraph',
    category: 'ai',
  },
  {
    route: 'ai-usage',
    title: 'AI usage',
    icon: ChartColumn,
    keywords: 'spending cost money tokens limit budget level',
    category: 'ai',
  },
  { route: 'assets', title: 'Assets', icon: MonitorSmartphone, category: 'network' },
  {
    route: 'devices',
    title: 'Devices',
    icon: Radar,
    keywords:
      'connections incoming outgoing source destination port protocol peers remote internet',
    category: 'network',
  },
  { route: 'interfaces', title: 'Interfaces', icon: Network, category: 'network' },
  { route: 'logs', title: 'Logs', icon: ScrollText, category: 'network' },
  { route: 'integrations', title: 'Integrations', icon: Plug, category: 'system' },
  { route: 'status', title: 'Status', icon: HeartPulse, category: 'system' },
  { route: 'settings', title: 'Settings', icon: Settings, category: 'system' },
]

/** The menu under its headings: each heading with its places in order, and no heading that has
 * none. */
export function navGroups(
  items: readonly NavItem[] = navItems,
): { key: NavCategory; title: string; items: readonly NavItem[] }[] {
  return NAV_CATEGORIES.map((category) => ({
    ...category,
    items: items.filter((item) => item.category === category.key),
  })).filter((group) => group.items.length > 0)
}

/** What the bottom bar of a phone holds: the places in the menu while they fit, and otherwise as
 * many as leave room for a "More" button, with the rest behind it. A place that asks to be behind
 * More is never in the bar when there is a More button, and the places in each keep their order. */
export function bottomBar(
  items: readonly NavItem[] = navItems,
  limit: number = BOTTOM_BAR_LIMIT,
): { bar: readonly NavItem[]; more: readonly NavItem[] } {
  if (items.length <= limit) return { bar: items, more: [] }
  const bar = items.filter((item) => !item.behindMore).slice(0, limit - 1)
  return { bar, more: items.filter((item) => !bar.includes(item)) }
}
