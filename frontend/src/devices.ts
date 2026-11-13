import { Globe, MonitorSmartphone, Network } from '@lucide/vue'
import type { LocationQuery } from 'vue-router'
import type { IconProps } from 'vuetify'

import {
  DEVICE_DIRECTIONS,
  DEVICE_SCOPES,
  DEVICE_SORTS,
  type Device,
  type DeviceDirection,
  type DeviceQuery,
  type DeviceScope,
  type DeviceSort,
} from '@/api/devices'

interface ScopeLook {
  label: string
  /** What it means, because "yours" and "local" are easy to mix up. */
  description: string
  icon: NonNullable<IconProps['icon']>
}

/** Never just a color: each scope has its own icon and its name. */
export const SCOPE: Readonly<Record<DeviceScope, ScopeLook>> = {
  yours: {
    label: 'Your devices',
    description: 'An address of one of the assets on the Assets page.',
    icon: MonitorSmartphone,
  },
  local: {
    label: 'Other local',
    description:
      "A private address that is not an asset: something on your network that nothing has listed, or a neighbour's.",
    icon: Network,
  },
  outside: {
    label: 'On the Internet',
    description: 'A public address: a server your devices called, or something that called in.',
    icon: Globe,
  },
}

export const SORTS: readonly { value: DeviceSort; label: string }[] = [
  { value: 'recent', label: 'Seen most recently' },
  { value: 'busiest', label: 'Most connections' },
  { value: 'address', label: 'Address' },
]

export const DEFAULT_SORT: DeviceSort = 'recent'

export const DIRECTION: Readonly<Record<DeviceDirection, { label: string; description: string }>> =
  {
    incoming: { label: 'Connected to', description: 'Something connected to it.' },
    outgoing: { label: 'Connected out', description: 'It connected to something.' },
  }

/** What the list is narrowed to and how it is ordered. It lives in the address of the page. */
export interface Filters {
  q: string
  scope: DeviceScope | null
  direction: DeviceDirection | null
  flagged: boolean
  sort: DeviceSort
}

export const NO_FILTERS: Readonly<Filters> = {
  q: '',
  scope: null,
  direction: null,
  flagged: false,
  sort: DEFAULT_SORT,
}

/** The filters an address says. Anything in it that isn't one of the choices is ignored. */
export function filtersOf(query: LocationQuery): Filters {
  const one = (name: string) => {
    const value = query[name]
    return typeof value === 'string' ? value : ''
  }
  return {
    q: one('q'),
    scope: DEVICE_SCOPES.find((each) => each === one('scope')) ?? null,
    direction: DEVICE_DIRECTIONS.find((each) => each === one('direction')) ?? null,
    flagged: one('flagged') === '1',
    sort: DEVICE_SORTS.find((each) => each === one('sort')) ?? DEFAULT_SORT,
  }
}

/** The address of the page for these filters: only what differs from showing everything. */
export function routeQuery(filters: Filters): Record<string, string> {
  const query: Record<string, string> = {}
  if (filters.q.trim()) query.q = filters.q.trim()
  if (filters.scope) query.scope = filters.scope
  if (filters.direction) query.direction = filters.direction
  if (filters.flagged) query.flagged = '1'
  if (filters.sort !== DEFAULT_SORT) query.sort = filters.sort
  return query
}

/** What to ask the API for. */
export function queryOf(filters: Filters, limit: number, offset = 0): DeviceQuery {
  const q = filters.q.trim()
  return {
    ...(q ? { q } : {}),
    ...(filters.scope ? { scope: filters.scope } : {}),
    ...(filters.direction ? { direction: filters.direction } : {}),
    flagged: filters.flagged,
    sort: filters.sort,
    limit,
    offset,
  }
}

/** How many choices narrow the list, besides its scope (which has a control of its own). */
export function activeFilters(filters: Filters): number {
  return (
    Number(filters.q.trim() !== '') + Number(filters.direction !== null) + Number(filters.flagged)
  )
}

/** What a device is called: its asset's name, else what its reverse lookup said, else nothing
 * beyond the address. */
export function nameOf(device: Pick<Device, 'asset' | 'name'>): string | null {
  return device.asset?.name ?? device.name
}

/** How many connections it was in, either way. */
export function connectionsOf(device: Pick<Device, 'incoming' | 'outgoing'>): number {
  return device.incoming + device.outgoing
}

/** How much of its connections were made to it, from 0 to 100, for the bar that splits them. */
export function incomingShare(device: Pick<Device, 'incoming' | 'outgoing'>): number {
  const all = connectionsOf(device)
  return all === 0 ? 0 : Math.round((device.incoming / all) * 100)
}
