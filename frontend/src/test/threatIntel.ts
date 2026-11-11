import type { KnownPage, Lookup, Ruling } from '@/api/threatIntel'

/** A domain no engine flagged, as a search that asked VirusTotal answers. */
export const CLEAN_LOOKUP: Lookup = {
  kind: 'domain',
  subject: 'example.com',
  judgement: 'clean',
  reported_judgement: 'clean',
  ruling: null,
  checked_at: '2026-11-09T12:00:00Z',
  cached: false,
  stale: false,
  notice: null,
  repeatable: true,
  first_checked_at: '2026-11-09T12:00:00Z',
  checks: 1,
  fresh_until: '2026-11-16T12:00:00Z',
  changed_at: null,
  previous_judgement: null,
  analysed_at: '2026-11-08T09:30:00Z',
  malicious: 0,
  suspicious: 0,
  harmless: 70,
  undetected: 12,
  reputation: 4,
  categories: [],
  details: [{ label: 'Registrar', value: 'Example Registrar' }],
  link: 'https://www.virustotal.com/gui/domain/example.com',
}

/** An address engines flagged as malicious. */
export const MALICIOUS_LOOKUP: Lookup = {
  ...CLEAN_LOOKUP,
  kind: 'ip',
  subject: '93.184.216.34',
  judgement: 'malicious',
  reported_judgement: 'malicious',
  fresh_until: '2026-11-11T12:00:00Z',
  analysed_at: '2026-11-07T00:00:00Z',
  malicious: 3,
  suspicious: 1,
  harmless: 60,
  undetected: 20,
  reputation: -12,
  categories: ['malware', 'phishing'],
  details: [{ label: 'Owner', value: 'Example Hosting' }],
  link: 'https://www.virustotal.com/gui/ip-address/93.184.216.34',
}

/** A web address with no report, as the list of what is kept shows it: by its host alone. */
export const KEPT_URL: Lookup = {
  ...CLEAN_LOOKUP,
  kind: 'url',
  subject: 'login.example.net',
  judgement: 'unknown',
  reported_judgement: 'unknown',
  cached: true,
  stale: true,
  repeatable: false,
  analysed_at: null,
  harmless: 0,
  undetected: 0,
  reputation: null,
  details: [],
  link: 'https://www.virustotal.com/gui/url/0f1e2d',
}

/** What is kept: one answer of each of three judgements, newest first. */
export function knownPage(overrides: Partial<KnownPage> = {}): KnownPage {
  return {
    total: 3,
    counts: { malicious: 1, suspicious: 0, clean: 1, unknown: 1 },
    items: [{ ...MALICIOUS_LOOKUP, cached: true }, { ...CLEAN_LOOKUP, cached: true }, KEPT_URL],
    ...overrides,
  }
}

/** What the owner ruled of an address: that it is safe, and why. */
export const SAFE_RULING: Ruling = {
  kind: 'ip',
  subject: '93.184.216.34',
  verdict: 'safe',
  note: "My friend's server",
  set_at: '2026-11-11T09:00:00Z',
  judgement: 'clean',
}

/** An address VirusTotal flagged, that the owner ruled safe. */
export const RULED_LOOKUP: Lookup = {
  ...MALICIOUS_LOOKUP,
  judgement: 'clean',
  reported_judgement: 'malicious',
  ruling: SAFE_RULING,
}
