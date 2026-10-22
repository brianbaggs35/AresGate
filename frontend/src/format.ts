/** A moment as people read it, in their own language and time zone. */
export function formatDateTime(iso: string, locale?: string): string {
  return new Intl.DateTimeFormat(locale, { dateStyle: 'medium', timeStyle: 'short' }).format(
    new Date(iso),
  )
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
