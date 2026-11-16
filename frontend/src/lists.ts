import type { LocationQuery } from 'vue-router'

import type { ViewPage, ViewQuery } from '@/api/views'

/** The pages whose lists can be exported and kept as views: what each is called and where it is. */
export const LIST_PAGES: Record<ViewPage, { title: string; route: string }> = {
  incidents: { title: 'Incidents', route: 'incidents' },
  alerts: { title: 'Alerts', route: 'alerts' },
  devices: { title: 'Devices', route: 'devices' },
  assets: { title: 'Assets', route: 'assets' },
}

/** What a page's address holds, as a view keeps it: each filter that is set, with its value or
 * values, and nothing for one that has none. */
export function queryOfRoute(query: LocationQuery): ViewQuery {
  const kept: ViewQuery = {}
  for (const [name, value] of Object.entries(query)) {
    const values = (Array.isArray(value) ? value : [value]).filter(
      (item): item is string => typeof item === 'string' && item !== '',
    )
    if (values.length === 0) continue
    kept[name] = Array.isArray(value) ? values : (values[0] as string)
  }
  return kept
}

/** Whether two queries set the same filters to the same things, whatever order they came in. */
export function sameQuery(a: ViewQuery, b: ViewQuery): boolean {
  const names = Object.keys(a)
  if (names.length !== Object.keys(b).length) return false
  return names.every((name) => {
    const other = b[name]
    return other !== undefined && JSON.stringify(a[name]) === JSON.stringify(other)
  })
}

/** The programs a view mentions: the integrations it is narrowed to, by the filter that says so
 * or by a word in its search, such as `source:wazuh`. */
export function programsOf(query: ViewQuery): string[] {
  const named = query.source ?? []
  const words = [...(typeof query.q === 'string' ? query.q.matchAll(/(?:^|\s)source:(\S+)/gi) : [])]
  const found = [
    ...(Array.isArray(named) ? named : [named]),
    ...words.map((word) => (word[1] as string).replace(/^"|"$/g, '')),
  ]
  return [...new Set(found.map((program) => program.toLowerCase()))]
}
