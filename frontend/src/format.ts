/** A moment as people read it, in their own language and time zone. */
export function formatDateTime(iso: string, locale?: string): string {
  return new Intl.DateTimeFormat(locale, { dateStyle: 'medium', timeStyle: 'short' }).format(
    new Date(iso),
  )
}

/** A moment as people read it, down to the second, for a log. */
export function formatTimestamp(iso: string, locale?: string): string {
  return new Intl.DateTimeFormat(locale, { dateStyle: 'medium', timeStyle: 'medium' }).format(
    new Date(iso),
  )
}

/** How long ago a moment was, in words ("5 minutes ago"), or "just now" within a minute. */
export function formatAgo(iso: string, now: number = Date.now(), locale?: string): string {
  const seconds = (new Date(iso).getTime() - now) / 1000
  if (Math.abs(seconds) < 60) return 'just now'
  const formatter = new Intl.RelativeTimeFormat(locale, { numeric: 'auto' })
  for (const [unit, size] of [
    ['day', 86400],
    ['hour', 3600],
  ] as const) {
    if (Math.abs(seconds) >= size) return formatter.format(Math.round(seconds / size), unit)
  }
  return formatter.format(Math.round(seconds / 60), 'minute')
}

/** When something is due ("in 5 minutes"), or "within a minute" once it is that close or past. */
export function formatDue(iso: string, now: number = Date.now(), locale?: string): string {
  if ((new Date(iso).getTime() - now) / 1000 < 60) return 'within a minute'
  return formatAgo(iso, now, locale)
}

/** How long something took, from milliseconds: "340 ms" or "1.8 s", or minutes for a long one. */
export function formatElapsed(milliseconds: number): string {
  if (milliseconds < 1000) return `${milliseconds.toFixed(0)} ms`
  const seconds = milliseconds / 1000
  if (seconds < 60) return `${seconds.toFixed(1)} s`
  return `${Math.floor(seconds / 60).toString()} min ${Math.round(seconds % 60).toString()} s`
}

// The first that matches wins: Edge and Opera also say Chrome, and Chrome also says Safari.
const BROWSERS: readonly (readonly [RegExp, string])[] = [
  [/Edg(?:e|A|iOS)?\//, 'Edge'],
  [/OPR\/|Opera/, 'Opera'],
  [/Firefox\/|FxiOS\//, 'Firefox'],
  [/Chrome\/|CriOS\//, 'Chrome'],
  [/Safari\//, 'Safari'],
]
// iPhones and iPads say they are Macs, and Android says it is Linux, so those come first.
const SYSTEMS: readonly (readonly [RegExp, string])[] = [
  [/iPhone|iPad|iPod/, 'iOS'],
  [/Android/, 'Android'],
  [/Windows/, 'Windows'],
  [/Mac OS X|Macintosh/, 'macOS'],
  [/CrOS/, 'ChromeOS'],
  [/Linux|X11/, 'Linux'],
]

function firstMatch(rules: readonly (readonly [RegExp, string])[], text: string) {
  return rules.find(([pattern]) => pattern.test(text))?.[1]
}

/** "Firefox on Linux" from a browser's user agent, as much of it as can be told. */
export function describeBrowser(userAgent: string | null): string {
  if (!userAgent) return 'Unknown device'
  const browser = firstMatch(BROWSERS, userAgent)
  const system = firstMatch(SYSTEMS, userAgent)
  if (browser && system) return `${browser} on ${system}`
  return browser ?? system ?? 'Unknown device'
}

/** A size in bytes the way people say it ("1.5 GB"), in powers of 1024. */
export function formatBytes(bytes: number): string {
  let amount = bytes
  for (const unit of ['B', 'KB', 'MB', 'GB']) {
    if (amount < 1024)
      return unit === 'B' ? `${amount.toFixed(0)} B` : `${amount.toFixed(1)} ${unit}`
    amount /= 1024
  }
  return `${amount.toFixed(1)} TB`
}

/** How long something has been going ("3d 4h 12m"): hours only once there are hours, and so on. */
export function formatDuration(seconds: number): string {
  const days = Math.floor(seconds / 86400)
  const hours = Math.floor((seconds % 86400) / 3600)
  const minutes = Math.floor((seconds % 3600) / 60)
  const parts = days ? [`${days.toString()}d`] : []
  if (days || hours) parts.push(`${hours.toString()}h`)
  parts.push(`${minutes.toString()}m`)
  return parts.join(' ')
}

/** A number of days in words: "1 day" or "30 days". */
export function formatDays(days: number): string {
  return `${days.toString()} ${days === 1 ? 'day' : 'days'}`
}

/** A count the way people read it, with the separators of their language: "12,408". */
export function formatCount(count: number, locale?: string): string {
  return new Intl.NumberFormat(locale).format(count)
}
