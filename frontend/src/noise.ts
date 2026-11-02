import type { DashboardWindow, Noise, NoisySignature } from '@/api/dashboard'
import { formatCount } from '@/format'
import type { Scope } from '@/verdicts'

/** What an alert that names no rule is called. */
export const UNNAMED = 'Alerts that name no rule'

/** What share of all the alerts a count is, from 0 to 1. */
export function shareOf(count: number, total: number): number {
  return total > 0 ? Math.min(1, count / total) : 0
}

/** The share as a percentage in words: a count that rounds to nothing is "under 1%". */
export function percentOf(count: number, total: number): string {
  const percent = Math.round(shareOf(count, total) * 100)
  return count > 0 && percent === 0 ? 'under 1%' : `${formatCount(percent)}%`
}

/** What an alert is called in the list. */
export function nameOf(item: Pick<NoisySignature, 'signature'>): string {
  return item.signature ?? UNNAMED
}

/** The search of the Logs page that finds an alert's rows in the window the dashboard shows. */
export function logsQuery(
  item: Pick<NoisySignature, 'source' | 'signature'>,
  window: DashboardWindow,
): string {
  // The search language has no way to write a quote inside quotes: a rule's name is matched as
  // the words around it.
  const words = (item.signature ?? '').replaceAll('"', ' ').trim()
  const rule = words ? ` signature:"${words}"` : ''
  return `kind:alert source:${item.source}${rule} since:${window}`
}

/** What a verdict on every alert like this one is about, which can't be said of one that names
 * no rule. */
export function scopeOf(item: NoisySignature): Scope | null {
  if (item.signature === null) return null
  return {
    key: `alert:${item.source}:${item.signature}`,
    title: `“${item.signature}”`,
    hint: `From any address, as seen by ${item.source_name}`,
    request: { source: item.source, signature: item.signature },
  }
}

/** Where the alerts come from, in a sentence: the program that reported most, and how many of its
 * alerts were serious, and how many in all were between two addresses on the network. */
export function summaryOf(noise: Noise, total: number): string {
  const [top] = noise.sources
  if (!top) return ''
  const reported =
    noise.sources.length === 1
      ? `${top.source_name} reported all ${formatCount(top.total)} of the alerts`
      : `${top.source_name} reported ${formatCount(top.total)} of the ${formatCount(total)} alerts (${percentOf(top.total, total)})`
  const serious =
    top.serious > 0
      ? `, ${formatCount(top.serious)} of them high or critical`
      : ', none of them high or critical'
  const inside = noise.sources.reduce((sum, { inside: count }) => sum + count, 0)
  const within =
    inside > 0
      ? ` ${formatCount(inside)} (${percentOf(inside, total)}) of all of them were between two addresses on your own network.`
      : ''
  return `${reported}${serious}.${within}`
}
