import { onBeforeUnmount, ref, watch } from 'vue'

import type { AddressTrends, DeliveryTrend, HourState } from '@/api/trends'
import { severityColor } from '@/charts/palette'
import { formatCount } from '@/format'
import { SEVERITIES, SEVERITY } from '@/severity'
import { useSessionStore } from '@/stores/session'

/**
 * Loads a trend after the page that it sits on, and again when what it is about changes (`key`:
 * a text that is the same while it is, or null for nothing to show). A trend only adds to a page,
 * so one that can't be had is not an error: it is not there.
 */
export function useTrend<T>(key: () => string | null, ask: () => Promise<T>) {
  const session = useSessionStore()
  const trend = ref<T | null>(null)
  const loading = ref(false)
  /** Only the newest request's answer counts, so a slow one can't replace a later one. */
  let latest = 0

  async function load() {
    const mine = ++latest
    if (key() === null) {
      trend.value = null
      loading.value = false
      return
    }
    loading.value = true
    try {
      const found = await session.call(ask)
      if (mine === latest) trend.value = found
    } catch {
      if (mine === latest) trend.value = null
    } finally {
      if (mine === latest) loading.value = false
    }
  }

  watch(key, load, { immediate: true })
  onBeforeUnmount(() => latest++)
  return { trend, loading, reload: load }
}

/** The labels under the bars of an hourly chart: the weekday and the hour. */
export function hourLabel(time: string): string {
  return new Date(time).toLocaleString(undefined, { weekday: 'short', hour: 'numeric' })
}

/** The messages of each hour as stacked bars, the severities there were any of, least serious
 * first so the worst sit on top. */
export function deliverySeries(trend: DeliveryTrend) {
  return SEVERITIES.flatMap((severity) => {
    const values = trend.severities[severity]
    return values.some((count) => count > 0)
      ? [
          {
            id: severity,
            label: SEVERITY[severity].label,
            values,
            color: severityColor(severity),
            icon: SEVERITY[severity].icon,
          },
        ]
      : []
  })
}

/** All the events an address was in, in each bucket, in or out. */
export function activityOf(trend: AddressTrends, address: string): number[] | null {
  const item = trend.items[address]
  return item ? item.incoming.map((count, index) => count + (item.outgoing[index] as number)) : null
}

const IPV4 = /^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$/
const IPV6 = /^[0-9a-f:.]+$/i

/** Whether text could be an IP address, so that a request for many is not refused for one that
 * is a name. The server has the last word. */
export function looksLikeAddress(text: string): boolean {
  return IPV4.test(text) || (text.includes(':') && IPV6.test(text))
}

/** What a small line says in words, since the line alone says neither what it is nor how much. */
export function sparkLabel(noun: string, values: readonly number[], span: string): string {
  const total = values.reduce((sum, count) => sum + count, 0)
  if (total === 0) return `No ${noun} in ${span}.`
  const latest = values.at(-1) as number
  return `${formatCount(total)} ${noun} in ${span}, ${formatCount(latest)} in the latest.`
}

/** How a day of calls to an integration went, in words. */
export const HOUR_STATES: Readonly<Record<HourState, string>> = {
  ok: 'Working',
  problem: 'Problem',
  none: 'No calls',
}

/** How the last hours of an integration went, in a sentence. */
export function stripSummary(states: readonly HourState[]): string {
  const count = (state: HourState) => states.filter((one) => one === state).length
  const problems = count('problem')
  const working = count('ok')
  if (problems === 0 && working === 0) return `No calls in the last ${states.length} hours.`
  const parts = [
    `${formatCount(working)} ${working === 1 ? 'hour' : 'hours'} working`,
    `${formatCount(problems)} with a problem`,
  ]
  return `In the last ${states.length} hours: ${parts.join(', ')}.`
}
