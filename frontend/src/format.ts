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
