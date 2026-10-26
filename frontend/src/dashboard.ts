import type { AlertCounts, DashboardWindow } from '@/api/dashboard'
import type { CollectorsReport } from '@/api/collectors'
import { formatCount } from '@/format'
import { SEVERITIES, type Severity } from '@/severity'

/** How a number has changed, as the stat tile shows it. */
export interface Change {
  text: string
  direction: 'up' | 'down' | 'flat'
  tone: 'neutral' | 'good' | 'bad'
}

/**
 * How a count compares with the one for the stretch of time before it, in words. Whether more is
 * worse is up to what is counted: more alerts are, more refused connections only say that
 * something is knocking, so those stay neutral.
 */
export function changeOf(
  total: number,
  previous: number,
  before: string,
  moreIsWorse: boolean,
): Change {
  if (total === previous) {
    return {
      text: total === 0 ? `None, as in ${before}` : `The same as ${before}`,
      direction: 'flat',
      tone: 'neutral',
    }
  }
  const direction = total > previous ? 'up' : 'down'
  const tone = !moreIsWorse ? 'neutral' : direction === 'up' ? 'bad' : 'good'
  if (previous === 0) return { text: `Up from none ${before}`, direction, tone }
  const percent = Math.round((Math.abs(total - previous) / previous) * 100)
  if (percent === 0)
    return { text: `About the same as ${before}`, direction: 'flat', tone: 'neutral' }
  const more = direction === 'up' ? 'more' : 'fewer'
  return { text: `${formatCount(percent)}% ${more} than ${before}`, direction, tone }
}

/** How many there were in each bucket, all severities together. */
export function sumBuckets(bySeverity: AlertCounts['by_severity']): number[] {
  return bySeverity.info.map((_, bucket) =>
    SEVERITIES.reduce((sum, severity) => sum + (bySeverity[severity][bucket] as number), 0),
  )
}

/** How the collectors are doing, for the tile and for the banner. */
export interface Collection {
  /** None are running (nothing is connected, or collecting is off), they all work, or some don't. */
  state: 'none' | 'ok' | 'problem'
  total: number
  /** What the tile says. */
  label: string
  /** What is wrong, in a clause that can start a sentence, or null while nothing is. */
  trouble: string | null
}

const plural = (count: number, one: string, many: string) =>
  `${formatCount(count)} ${count === 1 ? one : many}`

export function collectionOf(report: CollectorsReport): Collection {
  const total = report.collectors.length
  if (total === 0) return { state: 'none', total, label: 'None', trouble: null }
  const failing = report.collectors.filter(
    ({ state }) => state === 'problem' || state === 'late',
  ).length
  if (failing > 0) {
    return {
      state: 'problem',
      total,
      label: `${formatCount(failing)} failing`,
      trouble: `${plural(failing, 'collector is', 'collectors are')} not working`,
    }
  }
  if (report.worker.state === 'stopped') {
    return {
      state: 'problem',
      total,
      label: 'Stopped',
      trouble: 'The collector worker has stopped',
    }
  }
  const starting = report.collectors.every(({ state }) => state === 'waiting')
  return { state: 'ok', total, label: starting ? 'Starting' : 'Working', trouble: null }
}

/** How things stand, in one word for the banner at the top. */
export type PostureState = 'attention' | 'watch' | 'calm' | 'setup'

export interface Posture {
  state: PostureState
  title: string
  detail: string
}

/**
 * What to tell someone first. Until the analyst has learned what is normal on this network it
 * goes by how serious the alerts are, and it never says all is quiet while the collectors that
 * would raise the alarm aren't working.
 */
export function postureOf(
  alerts: AlertCounts,
  collection: Collection,
  window: DashboardWindow,
): Posture {
  const last = window === '24h' ? 'the last 24 hours' : 'the last 7 days'
  if (collection.state === 'none') {
    return {
      state: 'setup',
      title: 'Nothing is watching yet',
      detail:
        'Connect OPNsense or another integration and AresGate starts collecting what happens on your network.',
    }
  }
  const count = (severity: Severity) =>
    alerts.by_severity[severity].reduce((total, number) => total + number, 0)
  const blind = collection.trouble
    ? ` ${collection.trouble}, so a quiet network may not be a safe one.`
    : ''
  const serious = count('high') + count('critical')
  if (serious > 0) {
    return {
      state: 'attention',
      title: 'Needs your attention',
      detail: `${plural(serious, 'serious alert', 'serious alerts')} in ${last} (high or critical).${blind}`,
    }
  }
  const medium = count('medium')
  if (medium > 0) {
    return {
      state: 'watch',
      title: 'Worth a look',
      detail: `${plural(medium, 'medium alert', 'medium alerts')} in ${last}, none serious.${blind}`,
    }
  }
  const minor =
    alerts.total === 0
      ? `No alerts in ${last}.`
      : `${plural(alerts.total, 'minor alert', 'minor alerts')} in ${last}.`
  if (collection.trouble) {
    return { state: 'watch', title: "Some sources aren't reporting", detail: `${minor}${blind}` }
  }
  return {
    state: 'calm',
    title: 'All quiet',
    detail: alerts.total === 0 ? minor : `${minor} Nothing that needs you.`,
  }
}

/** The label of a bucket on a chart: the hour for a day, the day and hour for a week. */
export function bucketLabel(iso: string, window: DashboardWindow, locale?: string): string {
  const options: Intl.DateTimeFormatOptions =
    window === '24h' ? { hour: 'numeric' } : { weekday: 'short', hour: 'numeric' }
  return new Intl.DateTimeFormat(locale, options).format(new Date(iso))
}
