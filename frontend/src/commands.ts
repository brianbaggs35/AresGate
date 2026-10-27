import { Moon, Monitor, Search, ShieldAlert, Sun } from '@lucide/vue'
import type { RouteLocationRaw } from 'vue-router'
import type { IconProps } from 'vuetify'

import { VIEWS } from '@/incidents'
import { navItems } from '@/navigation'
import { settingsSections } from '@/settings'
import type { ThemePreference } from '@/stores/theme'

/** What choosing a command does: go somewhere, or change how the app looks. */
export type CommandAction =
  { kind: 'go'; to: RouteLocationRaw } | { kind: 'theme'; preference: ThemePreference }

/** One thing the command palette can do. */
export interface Command {
  id: string
  /** The heading it is listed under. */
  group: string
  title: string
  icon: NonNullable<IconProps['icon']>
  /** More words that find it, which are not shown. */
  keywords: string
  action: CommandAction
}

/** The groups in the order the palette lists them. */
export const GROUPS = ['Go to', 'Incidents', 'Appearance'] as const

const THEMES: readonly { preference: ThemePreference; title: string; icon: Command['icon'] }[] = [
  { preference: 'light', title: 'Use the light theme', icon: Sun },
  { preference: 'dark', title: 'Use the dark theme', icon: Moon },
  { preference: 'system', title: 'Follow the system theme', icon: Monitor },
]

/**
 * Everything the palette can do. The pages come from the menu and from Settings, so a page that
 * adds itself to either is found here without anyone remembering to.
 */
export const COMMANDS: readonly Command[] = [
  ...navItems
    // Settings opens its first page, which is listed by name below.
    .filter(({ route }) => route !== 'settings')
    .map(({ route, title, icon }): Command => ({
      id: `go-${route}`,
      group: 'Go to',
      title,
      icon,
      keywords: '',
      action: { kind: 'go', to: { name: route } },
    })),
  ...settingsSections.map(({ key, route, title, icon }): Command => ({
    id: `go-settings-${key}`,
    group: 'Go to',
    title: `Settings: ${title}`,
    icon,
    keywords: 'preferences options',
    action: { kind: 'go', to: { name: route } },
  })),
  ...VIEWS.map(({ key, label }): Command => ({
    id: `incidents-${key}`,
    group: 'Incidents',
    title: `Show ${label.toLowerCase()} incidents`,
    icon: ShieldAlert,
    keywords: 'list filter view',
    action: { kind: 'go', to: { name: 'incidents', query: { view: key } } },
  })),
  ...THEMES.map(({ preference, title, icon }): Command => ({
    id: `theme-${preference}`,
    group: 'Appearance',
    title,
    icon,
    keywords: 'theme dark light mode appearance',
    action: { kind: 'theme', preference },
  })),
]

/** How well a command answers a search: lower is better, and null is not at all. */
function rank(command: Command, terms: readonly string[]): number | null {
  const title = command.title.toLowerCase()
  const haystack = `${title} ${command.keywords}`
  if (!terms.every((term) => haystack.includes(term))) return null
  if (title.startsWith(terms[0] as string)) return 0
  return terms.every((term) => title.includes(term)) ? 1 : 2
}

const IPV4 = /^(?:(?:25[0-5]|2[0-4]\d|1?\d?\d)\.){3}(?:25[0-5]|2[0-4]\d|1?\d?\d)$/
const IPV6 = /^(?=(?:[^:]*:){2})[0-9a-f:.]{2,45}$/i

/** Whether text is a whole IP address, which is what the incidents search takes to look for. */
function isAddress(text: string): boolean {
  return IPV4.test(text) || IPV6.test(text)
}

/** The command that finds the incidents about an address that was typed whole. */
function findAddress(address: string): Command {
  return {
    id: 'incidents-address',
    group: 'Incidents',
    title: `Find incidents about ${address}`,
    icon: Search,
    keywords: address,
    action: { kind: 'go', to: { name: 'incidents', query: { view: 'all', q: address } } },
  }
}

/**
 * What matches a search, best first, in the order the groups are listed. Every word typed has to
 * be in the title or the hidden keywords. A whole IP address also offers to look for incidents
 * about it, since that is the one thing worth typing that no page name would match.
 */
export function commandsFor(search: string): Command[] {
  const text = search.trim().toLowerCase()
  const terms = text.split(/\s+/).filter(Boolean)
  const found = terms.length
    ? COMMANDS.flatMap((command) => {
        const score = rank(command, terms)
        return score === null ? [] : [{ command, score }]
      })
        .sort((a, b) => a.score - b.score)
        .map(({ command }) => command)
    : [...COMMANDS]
  const all = isAddress(text) ? [findAddress(search.trim()), ...found] : found
  return GROUPS.flatMap((group) => all.filter((command) => command.group === group))
}

/** What the shortcut that opens the palette is called on this computer. */
export function shortcutLabel(platform: string): string {
  return /Mac|iPhone|iPad/.test(platform) ? '⌘K' : 'Ctrl K'
}
