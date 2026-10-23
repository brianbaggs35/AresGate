import {
  describeBrowser,
  formatAgo,
  formatBytes,
  formatDateTime,
  formatDuration,
  formatTimestamp,
} from '@/format'

const AGENTS = {
  chromeWindows:
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36',
  edgeWindows:
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36 Edg/130.0.0.0',
  operaMac:
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36 OPR/115.0.0.0',
  firefoxLinux: 'Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:132.0) Gecko/20100101 Firefox/132.0',
  safariMac:
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Safari/605.1.15',
  safariIphone:
    'Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1',
  chromeAndroid:
    'Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Mobile Safari/537.36',
  chromeOs:
    'Mozilla/5.0 (X11; CrOS x86_64 14541.0.0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36',
}

describe('describeBrowser', () => {
  it.each([
    [AGENTS.chromeWindows, 'Chrome on Windows'],
    [AGENTS.edgeWindows, 'Edge on Windows'],
    [AGENTS.operaMac, 'Opera on macOS'],
    [AGENTS.firefoxLinux, 'Firefox on Linux'],
    [AGENTS.safariMac, 'Safari on macOS'],
    [AGENTS.safariIphone, 'Safari on iOS'],
    [AGENTS.chromeAndroid, 'Chrome on Android'],
    [AGENTS.chromeOs, 'Chrome on ChromeOS'],
  ])('reads %#', (agent, described) => {
    expect(describeBrowser(agent)).toBe(described)
  })

  it('names what it can when it knows only part', () => {
    expect(describeBrowser('curl/8.5.0 (Linux)')).toBe('Linux')
    expect(describeBrowser('Firefox/132.0')).toBe('Firefox')
  })

  it('says so when it knows nothing', () => {
    expect(describeBrowser('curl/8.5.0')).toBe('Unknown device')
    expect(describeBrowser(null)).toBe('Unknown device')
    expect(describeBrowser('')).toBe('Unknown device')
  })
})

describe('formatDateTime', () => {
  it('writes the date and the time in the reader’s language', () => {
    const moment = '2026-03-04T15:30:00Z'
    const formatted = formatDateTime(moment, 'en-US')
    expect(formatted).toMatch(/Mar 4, 2026/)
    expect(formatted).toMatch(/\d{1,2}:30/)
  })
})

describe('formatTimestamp', () => {
  it('includes the seconds', () => {
    expect(formatTimestamp('2026-03-04T15:30:45Z', 'en-US')).toMatch(/Mar 4, 2026.*:30:45/)
  })
})

describe('formatAgo', () => {
  const now = Date.parse('2026-03-04T12:00:00Z')

  it.each([
    ['2026-03-04T12:00:00Z', 'just now'],
    ['2026-03-04T11:59:30Z', 'just now'],
    ['2026-03-04T11:55:00Z', '5 minutes ago'],
    ['2026-03-04T11:59:00Z', '1 minute ago'],
    ['2026-03-04T09:00:00Z', '3 hours ago'],
    ['2026-03-02T12:00:00Z', '2 days ago'],
    ['2026-03-03T12:00:00Z', 'yesterday'],
    ['2026-03-04T12:10:00Z', 'in 10 minutes'],
  ])('puts %s as %s', (iso, words) => {
    expect(formatAgo(iso, now, 'en-US')).toBe(words)
  })

  it('counts from now unless told when now is', () => {
    expect(
      formatAgo(new Date(Date.now() - 2 * 3600 * 1000).toISOString(), undefined, 'en-US'),
    ).toBe('2 hours ago')
  })
})

describe('formatBytes', () => {
  it.each([
    [0, '0 B'],
    [1023, '1023 B'],
    [1024, '1.0 KB'],
    [1536 * 1024, '1.5 MB'],
    [3 * 1024 ** 3, '3.0 GB'],
    [5 * 1024 ** 4, '5.0 TB'],
  ])('says %d as %s', (bytes, said) => {
    expect(formatBytes(bytes)).toBe(said)
  })
})

describe('formatDuration', () => {
  it.each([
    [0, '0m'],
    [59, '0m'],
    [60 * 12, '12m'],
    [3600, '1h 0m'],
    [3 * 3600 + 5 * 60, '3h 5m'],
    [86400, '1d 0h 0m'],
    [2 * 86400 + 4 * 3600 + 30 * 60, '2d 4h 30m'],
  ])('says %d seconds as %s', (seconds, said) => {
    expect(formatDuration(seconds)).toBe(said)
  })
})
