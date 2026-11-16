import type { PlaceOut, WidgetSize } from '@/api/dashboardLayout'

/** The widgets of the dashboard, under the status banner and its four numbers. The ids are the
 * API's (`app/dashboard_layout.py` has the same list, in the same order). */
export type WidgetId =
  | 'filtered'
  | 'review'
  | 'needs_you'
  | 'traffic'
  | 'alerts'
  | 'blocked'
  | 'noise'
  | 'sources'
  | 'latest'

export interface Place {
  id: WidgetId
  size: WidgetSize
  hidden: boolean
}

export interface WidgetInfo {
  id: WidgetId
  title: string
  description: string
  /** The integrations that feed it, any one of which will do, or none when it reads what AresGate
   * itself holds. Without one connected it says so, instead of showing nothing. */
  needs: readonly string[] | null
}

/** The programs that tell AresGate about alerts. */
const ALERT_SOURCES = ['opnsense', 'wazuh', 'crowdsec', 'ntopng'] as const

/** In the order the dashboard shows them to someone who has not changed it. */
export const WIDGETS: readonly WidgetInfo[] = [
  {
    id: 'filtered',
    title: 'What was left out',
    description: 'How many incidents need you and how many the filters left out, with the reasons.',
    needs: null,
  },
  {
    id: 'review',
    title: 'Review',
    description: 'A reminder to look at what the AI decided on its own.',
    needs: null,
  },
  {
    id: 'needs_you',
    title: 'Needs a decision',
    description: 'The open incidents that most need a decision, which can be judged right there.',
    needs: null,
  },
  {
    id: 'traffic',
    title: 'Traffic',
    description: 'What each interface carried, with the incidents flagged on it.',
    needs: ['opnsense', 'ntopng'],
  },
  {
    id: 'alerts',
    title: 'Alerts by severity',
    description: 'Alerts in each hour or six hours, by severity.',
    needs: ALERT_SOURCES,
  },
  {
    id: 'blocked',
    title: 'Blocked connections',
    description: 'What the firewall turned away, and where to.',
    needs: ['opnsense'],
  },
  {
    id: 'noise',
    title: 'What makes the noise',
    description: 'The alerts that fire most, and what to do about them.',
    needs: ALERT_SOURCES,
  },
  {
    id: 'sources',
    title: 'Most blocked addresses',
    description: 'Where the firewall refused the most connections from.',
    needs: ['opnsense'],
  },
  {
    id: 'latest',
    title: 'Latest alerts',
    description: 'The newest alerts, whatever program reported them.',
    needs: ALERT_SOURCES,
  },
]

const SIZES: Readonly<Record<WidgetId, WidgetSize>> = {
  filtered: 'full',
  review: 'full',
  needs_you: 'full',
  traffic: 'half',
  alerts: 'half',
  blocked: 'full',
  noise: 'full',
  sources: 'half',
  latest: 'half',
}

/** What the dashboard is until an account changes it, which is also what it is when the account's
 * own layout can't be read. */
export const DEFAULT_PLACES: readonly Place[] = WIDGETS.map(({ id }) => ({
  id,
  size: SIZES[id],
  hidden: false,
}))

export const widgetInfo = (id: WidgetId): WidgetInfo =>
  WIDGETS.find((widget) => widget.id === id) as WidgetInfo

/** What the API sent as places this page can draw: a widget this version doesn't know is left
 * out, and one that is missing comes last, shown. */
export function placesFrom(sent: readonly PlaceOut[]): Place[] {
  const known = new Set<string>(WIDGETS.map(({ id }) => id))
  const places = sent.filter(({ id }) => known.has(id)) as Place[]
  const there = new Set(places.map(({ id }) => id))
  return [...places, ...DEFAULT_PLACES.filter(({ id }) => !there.has(id))].map((place) => ({
    ...place,
  }))
}

/** The places that are shown, in order. */
export const shownPlaces = (places: readonly Place[]): Place[] =>
  places.filter(({ hidden }) => !hidden)

/** The places with the widget `id` moved `by` places towards the end (or the start, when
 * negative), stopping at either end. */
export function moveBy(places: readonly Place[], id: WidgetId, by: number): Place[] {
  const from = places.findIndex((place) => place.id === id)
  const to = Math.min(places.length - 1, Math.max(0, from + by))
  const moved = [...places]
  const [place] = moved.splice(from, 1)
  moved.splice(to, 0, place as Place)
  return moved
}

/** The places with the widget `id` put where `target` is, which takes the next place. Dropping a
 * widget on itself changes nothing. */
export function moveTo(places: readonly Place[], id: WidgetId, target: WidgetId): Place[] {
  if (id === target) return [...places]
  const to = places.findIndex((place) => place.id === target)
  const without = places.filter((place) => place.id !== id)
  const at = without.findIndex((place) => place.id === target)
  const from = places.findIndex((place) => place.id === id)
  const moved = [...without]
  // Coming from above, it goes after the one it was dropped on, as coming from below it goes
  // before: the one dropped on is where it ends up.
  moved.splice(from < to ? at + 1 : at, 0, places[from] as Place)
  return moved
}

/** The places with one of them changed. */
export function change(
  places: readonly Place[],
  id: WidgetId,
  changes: Partial<Pick<Place, 'size' | 'hidden'>>,
): Place[] {
  return places.map((place) => (place.id === id ? { ...place, ...changes } : place))
}

const NAMES: Readonly<Record<string, string>> = {
  opnsense: 'OPNsense',
  ntopng: 'ntopng',
  wazuh: 'Wazuh',
  crowdsec: 'CrowdSec',
}

/** What a widget needs that is not connected, in a sentence, or null when it has what it needs.
 * `connected` holds the integrations that have a collector. */
export function connectWords(info: WidgetInfo, connected: ReadonlySet<string>): string | null {
  if (info.needs === null || info.needs.some((name) => connected.has(name))) return null
  const names = info.needs.map((name) => NAMES[name] ?? name)
  const last = names.pop() as string
  const list = names.length ? `${names.join(', ')} or ${last}` : last
  return `Connect ${list} to see this.`
}
