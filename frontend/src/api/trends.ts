import { apiGet } from '@/api/client'
import type { Severity } from '@/severity'

export type TrendStep = 'hour' | 'day'

/** How many requests for one address's trend, at most, so a page asks once for all of its cards. */
export const MOST_ADDRESSES = 50

/** Messages made in each hour, by how serious what they were about. */
export interface DeliveryTrend {
  times: string[]
  step: TrendStep
  severities: Record<Severity, number[]>
}

/** The events each address was in, in each hour or day: the connections to it and from it. */
export interface AddressTrends {
  times: string[]
  step: TrendStep
  items: Record<string, { incoming: number[]; outgoing: number[] }>
}

/** The incidents of each kind that began each day, by the kind's id. */
export interface KindTrends {
  times: string[]
  step: TrendStep
  items: Record<string, number[]>
}

/** How an hour of an integration's calls went: none were made, all worked, or one failed. */
export type HourState = 'none' | 'ok' | 'problem'

export interface IntegrationTrends {
  times: string[]
  step: TrendStep
  items: Record<string, HourState[]>
}

export function fetchDeliveryTrend(
  query: { destination_id?: number; state?: string } = {},
  hours = 48,
): Promise<DeliveryTrend> {
  const params = new URLSearchParams({ hours: hours.toString() })
  if (query.destination_id !== undefined)
    params.set('destination_id', query.destination_id.toString())
  if (query.state !== undefined) params.set('state', query.state)
  return apiGet<DeliveryTrend>(`/trends/deliveries?${params.toString()}`)
}

export function fetchAddressTrends(
  addresses: readonly string[],
  step: TrendStep = 'day',
  count = 7,
): Promise<AddressTrends> {
  const params = new URLSearchParams({ step, count: count.toString() })
  for (const address of addresses.slice(0, MOST_ADDRESSES)) params.append('address', address)
  return apiGet<AddressTrends>(`/trends/addresses?${params.toString()}`)
}

export function fetchKindTrends(ids: readonly number[], days = 7): Promise<KindTrends> {
  const params = new URLSearchParams({ days: days.toString() })
  for (const id of ids.slice(0, MOST_ADDRESSES)) params.append('id', id.toString())
  return apiGet<KindTrends>(`/trends/kinds?${params.toString()}`)
}

export function fetchIntegrationTrends(hours = 24): Promise<IntegrationTrends> {
  return apiGet<IntegrationTrends>(`/trends/integrations?hours=${hours}`)
}
