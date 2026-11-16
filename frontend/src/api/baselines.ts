import { apiGet, apiPost, apiPut } from '@/api/client'

/** What is usual for an hour of the day (UTC), in bytes in the hour, and how far is far. */
export interface BaselineHour {
  hour: number
  median: number
  spread: number
  samples: number
}

/** An hour that carried far more than is usual, as it was raised. */
export interface BaselineDeviation {
  at: string
  summary: string
  observed: number
  usual: number
  severity: number
}

/** The usual traffic of one interface in one direction. */
export interface BaselineSeries {
  /** What the integration calls it, such as igc0. */
  interface: string | null
  /** What you call it, once it is placed. */
  name: string | null
  direction: 'received' | 'sent'
  hours: BaselineHour[]
  learned_at: string | null
  samples: number
  deviations: BaselineDeviation[]
}

export interface BaselineInterfaces {
  series: BaselineSeries[]
  /** Whether any interface counter is collected at all. */
  counted: boolean
  /** The weeks and the hours it takes before an hour of the day is learned. */
  weeks: number
  min_hours: number
}

/** A device and how much is known of where it talks to. */
export interface BaselineTalker {
  address: string
  name: string | null
  places: number
  expected: number
  hits: number
  learning_since: string
  last_seen_at: string
  /** Whether enough is known to call a new place unusual. */
  judged: boolean
}

export interface BaselineTalkers {
  items: BaselineTalker[]
  total: number
  watched_days: number
  min_places: number
  forget_days: number
}

/** A network (a /24 or a /64) and a port (0 where there is none) a device talks to. */
export interface BaselinePlace {
  network: string
  port: number
  first_seen_at: string
  last_seen_at: string
  hits: number
  expected: boolean
}

export interface BaselinePlaces {
  address: string
  name: string | null
  places: BaselinePlace[]
}

export function fetchBaselineInterfaces(): Promise<BaselineInterfaces> {
  return apiGet<BaselineInterfaces>('/baselines/interfaces')
}

export function fetchBaselineTalkers(): Promise<BaselineTalkers> {
  return apiGet<BaselineTalkers>('/baselines/devices')
}

export function fetchBaselinePlaces(address: string): Promise<BaselinePlaces> {
  return apiGet<BaselinePlaces>(`/baselines/devices/${encodeURIComponent(address)}`)
}

/** Says a place is expected for a device, or takes that off. A place never learned is made. */
export function expectPlace(
  address: string,
  place: { network: string; port: number; expected: boolean },
  csrfToken: string,
): Promise<BaselinePlace> {
  return apiPut<BaselinePlace>(
    `/baselines/devices/${encodeURIComponent(address)}/places`,
    place,
    csrfToken,
  )
}

/** Forgets a place, so the next time the device goes there it is new again. */
export function forgetPlace(
  address: string,
  place: { network: string; port: number },
  csrfToken: string,
): Promise<undefined> {
  return apiPost(`/baselines/devices/${encodeURIComponent(address)}/forget`, place, csrfToken)
}
