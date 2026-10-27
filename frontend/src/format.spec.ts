import {
  describeBrowser,
  formatAgo,
  formatBitrate,
  formatBytes,
  formatCompact,
  formatCount,
  formatDateTime,
  formatDays,
  formatDue,
  formatDuration,
  formatElapsed,
  formatFigure,
  formatList,
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

describe('formatDue', () => {
  const now = Date.parse('2026-03-04T12:00:00Z')

  it.each([
    ['2026-03-04T11:00:00Z', 'within a minute'],
    ['2026-03-04T12:00:30Z', 'within a minute'],
    ['2026-03-04T12:05:00Z', 'in 5 minutes'],
    ['2026-03-04T15:00:00Z', 'in 3 hours'],
  ])('puts %s as %s', (iso, words) => {
    expect(formatDue(iso, now, 'en-US')).toBe(words)
  })

  it('counts from now unless told when now is', () => {
    expect(
      formatDue(new Date(Date.now() + 2 * 3600 * 1000).toISOString(), undefined, 'en-US'),
    ).toBe('in 2 hours')
  })
})

describe('formatElapsed', () => {
  it.each([
    [0, '0 ms'],
    [340, '340 ms'],
    [999, '999 ms'],
    [1000, '1.0 s'],
    [1840, '1.8 s'],
    [59_000, '59.0 s'],
    [60_000, '1 min 0 s'],
    [125_000, '2 min 5 s'],
  ])('says %d milliseconds as %s', (milliseconds, said) => {
    expect(formatElapsed(milliseconds)).toBe(said)
  })
})

describe('formatDays', () => {
  it('says day for one and days for any other number', () => {
    expect(formatDays(1)).toBe('1 day')
    expect(formatDays(30)).toBe('30 days')
    expect(formatDays(3650)).toBe('3650 days')
  })
})

describe('formatCount', () => {
  it('groups the digits the way the language does', () => {
    expect(formatCount(12408, 'en-US')).toBe('12,408')
    expect(formatCount(12408, 'de-DE')).toBe('12.408')
    expect(formatCount(0, 'en-US')).toBe('0')
  })
})

describe('formatCompact', () => {
  it('writes a number short from a thousand up', () => {
    expect(formatCompact(0, 'en-US')).toBe('0')
    expect(formatCompact(950, 'en-US')).toBe('950')
    expect(formatCompact(1000, 'en-US')).toBe('1K')
    expect(formatCompact(12_900, 'en-US')).toBe('12.9K')
    expect(formatCompact(4_200_000, 'en-US')).toBe('4.2M')
  })
})

describe('formatFigure', () => {
  it('writes a number in full while it fits and short after', () => {
    expect(formatFigure(1284, 'en-US')).toBe('1,284')
    expect(formatFigure(9999, 'en-US')).toBe('9,999')
    expect(formatFigure(12_900, 'en-US')).toBe('12.9K')
    expect(formatFigure(-12_900, 'en-US')).toBe('-12.9K')
  })
})

describe('formatBitrate', () => {
  it('says bits, kilobits, megabits and gigabits a second, in thousands', () => {
    expect(formatBitrate(0)).toBe('0 b/s')
    expect(formatBitrate(950)).toBe('950 b/s')
    expect(formatBitrate(1_500)).toBe('1.5 kb/s')
    expect(formatBitrate(80_000_000)).toBe('80 Mb/s')
    expect(formatBitrate(123_456_789)).toBe('123 Mb/s')
    expect(formatBitrate(2_500_000_000)).toBe('2.5 Gb/s')
  })

  it('moves up a unit instead of rounding to a thousand', () => {
    expect(formatBitrate(999_600)).toBe('1 Mb/s')
    expect(formatBitrate(999_400)).toBe('999 kb/s')
  })

  it('goes on to terabits for a link nobody has at home', () => {
    expect(formatBitrate(3_000_000_000_000)).toBe('3 Tb/s')
  })
})

describe('formatList', () => {
  it('names one, two or several the way people say them', () => {
    expect(formatList(['CrowdSec'], 'en-US')).toBe('CrowdSec')
    expect(formatList(['CrowdSec', 'Wazuh'], 'en-US')).toBe('CrowdSec and Wazuh')
    expect(formatList(['CrowdSec', 'OPNsense', 'Wazuh'], 'en-US')).toBe(
      'CrowdSec, OPNsense, and Wazuh',
    )
  })
})
