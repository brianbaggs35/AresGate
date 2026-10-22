/**
 * What a person chose in this browser, such as the theme, remembered in local storage. Storage
 * can be switched off (private mode, blocked site data), so a failure to read or write it never
 * stops a choice from applying for the visit.
 */

/** The saved choice, or null when there is none, it isn't one of `allowed`, or storage fails. */
export function readChoice<T extends string>(key: string, allowed: readonly T[]): T | null {
  try {
    const stored = localStorage.getItem(key)
    return allowed.find((choice) => choice === stored) ?? null
  } catch {
    return null
  }
}

export function saveChoice(key: string, value: string): void {
  try {
    localStorage.setItem(key, value)
  } catch {
    // Storage can be unavailable; the choice still applies for this visit.
  }
}
