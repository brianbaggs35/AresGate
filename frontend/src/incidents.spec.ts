import {
  ACTIVITY,
  CONFIDENCE_FILTERS,
  DEFAULT_VIEW,
  HIGH_CONFIDENCE,
  MEDIUM_CONFIDENCE,
  NO_FILTERS,
  STATUS,
  VIEWS,
  actionsFor,
  activeFilters,
  changedTo,
  countIn,
  flowOf,
  isAboutRule,
  lasted,
  otherAddresses,
  portLabel,
  portsTouched,
  queryOf,
  reasonLabel,
  spanOf,
  spreadOf,
  storyOf,
} from '@/incidents'
import { INCIDENT_STATUSES } from '@/api/incidents'
import { zone } from '@/search'
import { detail, device, incident, signal } from '@/test/incidents'

const AT = Date.parse('2026-10-26T14:00:00Z')
const MINUTE = 60_000
const at = (minutes: number) => new Date(AT + minutes * MINUTE).toISOString()

describe('statuses', () => {
  it('look like something other than a color', () => {
    for (const status of INCIDENT_STATUSES) {
      expect(STATUS[status].label).toBeTruthy()
      expect(STATUS[status].icon).toBeTruthy()
      expect(STATUS[status].meaning).toMatch(/\.$/)
    }
    expect(new Set(INCIDENT_STATUSES.map((status) => STATUS[status].label)).size).toBe(4)
  })

  it('offer the next things to do', () => {
    expect(actionsFor('open').map(({ status }) => status)).toEqual([
      'investigating',
      'resolved',
      'dismissed',
    ])
    expect(actionsFor('investigating').map(({ label }) => label)).toEqual([
      'Resolve',
      'Dismiss',
      'Back to open',
    ])
    expect(actionsFor('resolved').map(({ status }) => status)).toEqual(['open'])
    expect(actionsFor('dismissed').map(({ label }) => label)).toEqual(['Reopen'])
  })

  it('make one thing the one to reach for first', () => {
    for (const status of INCIDENT_STATUSES) {
      expect(actionsFor(status).filter(({ primary }) => primary)).toHaveLength(1)
    }
  })

  it('say what was done', () => {
    expect(changedTo('resolved')).toBe('Marked as resolved.')
    expect(changedTo('investigating')).toBe('Marked as investigating.')
    expect(changedTo('open')).toBe('Reopened.')
  })
})

describe('reasonLabel', () => {
  it('names the reasons there are, and uses the key for one it does not know', () => {
    expect(reasonLabel('corroborated')).toBe('Other programs agree')
    expect(reasonLabel('banned')).toBe('Banned')
    expect(reasonLabel('muted')).toBe('Left out by your verdicts')
    expect(reasonLabel('threat')).toBe('You said it is a real threat')
    expect(reasonLabel('geo')).toBe('geo')
  })
})

describe('the views of the list', () => {
  const counts = { open: 2, investigating: 1, resolved: 14, dismissed: 3 }

  it('start with what needs someone', () => {
    expect(DEFAULT_VIEW).toBe('active')
    expect(VIEWS[0].statuses).toEqual(['open', 'investigating'])
  })

  it('count the incidents in them', () => {
    expect(countIn('active', counts)).toBe(3)
    expect(countIn('open', counts)).toBe(2)
    expect(countIn('resolved', counts)).toBe(14)
    expect(countIn('dismissed', counts)).toBe(3)
    expect(countIn('all', counts)).toBe(20)
  })
})

describe('queryOf', () => {
  it('asks for the statuses of the view and nothing else by default', () => {
    expect(queryOf(NO_FILTERS, 25)).toEqual({
      statuses: ['open', 'investigating'],
      verdicts: ['none', 'threat'],
      minConfidence: 0,
      limit: 25,
    })
  })

  it('leaves out the incidents the owner quieted unless asked for them', () => {
    expect(queryOf(NO_FILTERS, 10).verdicts).toEqual(['none', 'threat'])
    expect(queryOf({ ...NO_FILTERS, quieted: true }, 10)).not.toHaveProperty('verdicts')
  })

  it('adds what the list is narrowed to', () => {
    const filters = {
      view: 'resolved' as const,
      severity: 'high' as const,
      confidence: HIGH_CONFIDENCE,
      q: ' source:wazuh -port:22 ',
      quieted: true,
    }

    expect(queryOf(filters, 10)).toEqual({
      statuses: ['resolved'],
      minSeverity: 'high',
      minConfidence: 65,
      q: 'source:wazuh -port:22',
      tz: zone(),
      limit: 10,
    })
  })

  it('does not search for a search with nothing in it', () => {
    expect(queryOf({ ...NO_FILTERS, q: '   ' }, 10)).not.toHaveProperty('q')
    expect(queryOf({ ...NO_FILTERS, q: '   ' }, 10)).not.toHaveProperty('tz')
  })

  it('asks for no status to see them all', () => {
    expect(queryOf({ ...NO_FILTERS, view: 'all' }, 10).statuses).toEqual([])
  })
})

describe('activeFilters', () => {
  it('counts the ones that narrow the list, not the view', () => {
    expect(activeFilters(NO_FILTERS)).toBe(0)
    expect(activeFilters({ ...NO_FILTERS, view: 'resolved' })).toBe(0)
    expect(activeFilters({ ...NO_FILTERS, severity: 'high' })).toBe(1)
    expect(activeFilters({ ...NO_FILTERS, confidence: MEDIUM_CONFIDENCE })).toBe(1)
    expect(activeFilters({ ...NO_FILTERS, q: '10.0.0.1' })).toBe(1)
    expect(activeFilters({ ...NO_FILTERS, q: '  ' })).toBe(0)
    expect(activeFilters({ ...NO_FILTERS, quieted: true })).toBe(1)
    expect(
      activeFilters({
        view: 'all',
        severity: 'high',
        confidence: 65,
        q: '10.0.0.1',
        quieted: true,
      }),
    ).toBe(4)
  })

  it('offers the confidence the words low, medium and high are drawn at', () => {
    expect(CONFIDENCE_FILTERS.map(({ value }) => value)).toEqual([
      0,
      MEDIUM_CONFIDENCE,
      HIGH_CONFIDENCE,
    ])
  })
})

describe('lasted', () => {
  it('says how long an incident went on', () => {
    expect(lasted({ first_seen_at: at(0), last_seen_at: at(0) })).toBe('Under a minute')
    expect(lasted({ first_seen_at: at(0), last_seen_at: at(18) })).toBe('18m')
    expect(lasted({ first_seen_at: at(0), last_seen_at: at(192) })).toBe('3h 12m')
  })
})

describe('spanOf', () => {
  it('says how long the signals took to come in', () => {
    expect(spanOf({ first_seen_at: at(0), last_seen_at: at(0) })).toBe('within a minute')
    expect(spanOf({ first_seen_at: at(0), last_seen_at: at(192) })).toBe('over 3h 12m')
  })
})

describe('addresses', () => {
  it('leaves out the one the incident is about', () => {
    expect(otherAddresses(incident({ addresses: ['93.184.216.34', '192.168.1.20'] }))).toEqual([
      '192.168.1.20',
    ])
    expect(otherAddresses(incident({ addresses: [] }))).toEqual([])
  })

  it('tells an incident about a rule from one about an address', () => {
    expect(isAboutRule('rule:wazuh:sshd')).toBe(true)
    expect(isAboutRule('93.184.216.34')).toBe(false)
  })
})

describe('flowOf', () => {
  it('shows where the traffic went', () => {
    expect(flowOf(signal())).toBe('93.184.216.34:51514 → 192.168.1.20:22 (tcp)')
  })

  it('leaves out the ports and protocol it was not told', () => {
    expect(flowOf(signal({ src_port: null, dst_port: null, protocol: null }))).toBe(
      '93.184.216.34 → 192.168.1.20',
    )
  })

  it('shows one end alone', () => {
    expect(flowOf(signal({ dst_address: null, dst_port: null }))).toBe('93.184.216.34:51514 (tcp)')
    expect(flowOf(signal({ src_address: null, src_port: null, protocol: null }))).toBe(
      '→ 192.168.1.20:22',
    )
  })

  it('puts an IPv6 address in brackets when there is a port after it', () => {
    expect(
      flowOf(signal({ src_address: '2606:2800:220:1::1', src_port: 443, protocol: null })),
    ).toBe('[2606:2800:220:1::1]:443 → 192.168.1.20:22')
    expect(flowOf(signal({ src_address: '2606:2800:220:1::1', src_port: null }))).toContain(
      '2606:2800:220:1::1 → ',
    )
  })

  it('has nothing to show for a signal that named no address', () => {
    expect(
      flowOf(signal({ src_address: null, dst_address: null, src_port: null, dst_port: null })),
    ).toBeNull()
  })
})

describe('spreadOf', () => {
  const programs = [
    { key: 'opnsense', name: 'OPNsense' },
    { key: 'wazuh', name: 'Wazuh' },
  ]
  const from = (minutes: number, source = 'wazuh') =>
    signal({ occurred_at: at(minutes), source, source_name: source })

  it('counts the signals of each program in bars of equal width', () => {
    const spread = spreadOf([from(0), from(1), from(3, 'opnsense'), from(12)], programs, 'en-US')

    expect(spread.width).toBe('1 minute')
    expect(spread.categories).toHaveLength(13)
    expect(spread.series.map(({ id, label }) => [id, label])).toEqual([
      ['opnsense', 'OPNsense'],
      ['wazuh', 'Wazuh'],
    ])
    const [opnsense, wazuh] = spread.series
    expect(opnsense?.values.reduce((sum, count) => sum + count, 0)).toBe(1)
    expect(opnsense?.values[3]).toBe(1)
    expect(wazuh?.values[0]).toBe(1)
    expect(wazuh?.values[1]).toBe(1)
    expect(wazuh?.values[12]).toBe(1)
  })

  it('labels the bars with the clock for a short stretch', () => {
    const spread = spreadOf([from(0), from(5)], programs, 'en-US')

    expect(spread.categories[0]).toMatch(/^\d{1,2}:\d{2}\s?[AP]M$/)
  })

  it('uses wider bars for a longer stretch, to keep to a couple of dozen', () => {
    const spread = spreadOf([from(0), from(100)], programs, 'en-US')

    expect(spread.width).toBe('5 minutes')
    expect(spread.categories.length).toBeLessThanOrEqual(24)
    expect(spread.series[1]?.values.reduce((sum, count) => sum + count, 0)).toBe(2)
  })

  it('counts in hours for an incident that went on for a day', () => {
    const spread = spreadOf([from(0), from(60 * 20)], programs, 'en-US')

    expect(spread.width).toBe('1 hour')
    expect(spread.categories[0]).toMatch(/^\d{1,2}:\d{2}\s?[AP]M$/)
  })

  it('labels the bars of a longer stretch with the day', () => {
    const spread = spreadOf([from(0), from(60 * 40)], programs, 'en-US')

    expect(spread.width).toBe('3 hours')
    expect(spread.categories[0]).toMatch(/^[A-Z][a-z]{2},? \d{1,2}\s?[AP]M$/)
  })

  it('names the widest bars', () => {
    expect(spreadOf([from(0), from(60 * 24 * 40)], programs, 'en-US').width).toBe('24 hours')
  })

  it('makes one bar of signals that all happened together', () => {
    const spread = spreadOf([from(0), from(0)], programs, 'en-US')

    expect(spread.categories).toHaveLength(1)
    expect(spread.series[1]?.values).toEqual([2])
  })

  it('leaves out a program it was not told about', () => {
    const spread = spreadOf([from(0), from(1, 'ntopng')], programs, 'en-US')

    expect(
      spread.series.flatMap(({ values }) => values).reduce((sum, count) => sum + count, 0),
    ).toBe(1)
  })
})

describe('what an incident was doing', () => {
  it('names the kinds of activity', () => {
    expect(ACTIVITY.scan.label).toBe('Scanning')
    expect(ACTIVITY.brute_force.label).toBe('Brute force')
  })

  it('names a port by the service it is known for, if it is one', () => {
    expect(portLabel(22)).toBe('22 (SSH)')
    expect(portLabel(3389)).toBe('3389 (RDP)')
    expect(portLabel(49152)).toBe('49152')
  })

  it('counts the ports it touched, and says "at least" when more were not kept', () => {
    expect(portsTouched({ port_count: 1, ports_capped: false })).toBe('1 port')
    expect(portsTouched({ port_count: 14, ports_capped: false })).toBe('14 ports')
    expect(portsTouched({ port_count: 1000, ports_capped: true })).toBe('at least 1,000 ports')
  })
})

describe('storyOf', () => {
  const story = (changes: Parameters<typeof detail>[0] = {}) => storyOf(detail(changes), 'en-US')

  it('says that programs agree, and who reported what about whom over how long', () => {
    const { title, detail: text } = story({
      sources: [
        { key: 'crowdsec', name: 'CrowdSec' },
        { key: 'opnsense', name: 'OPNsense' },
        { key: 'wazuh', name: 'Wazuh' },
      ],
      signal_count: 9,
      first_seen_at: at(0),
      last_seen_at: at(28),
      devices: [],
      blocked: 0,
    })

    expect(title).toBe('3 programs agree')
    expect(text).toBe(
      'CrowdSec, OPNsense, and Wazuh reported 9 signals about 93.184.216.34 over 28m.',
    )
  })

  it('says when only one program saw it, and that one signal took no time', () => {
    const { title, detail: text } = story({
      sources: [{ key: 'ntopng', name: 'ntopng' }],
      signal_count: 1,
      devices: [],
      blocked: null,
    })

    expect(title).toBe('One program saw it')
    expect(text).toBe('ntopng reported 1 signal about 93.184.216.34.')
  })

  it('says what a rule with no address is', () => {
    const { detail: text } = story({
      subject: 'rule:wazuh:5710',
      signal_count: 4,
      first_seen_at: at(0),
      last_seen_at: at(0),
      devices: [],
      blocked: null,
    })

    expect(text).toContain('about a rule that names no address within a minute.')
  })

  it('says that it was banned', () => {
    expect(story({ banned: true, devices: [], blocked: null }).detail).toContain(
      ' An integration banned the address.',
    )
    expect(story({ banned: false, devices: [], blocked: null }).detail).not.toContain('banned')
  })

  it('names the devices on the network that it involves, a few of them and then how many more', () => {
    const named = (hostname: string | null, id: number) =>
      device({ id, hostname, address: `192.168.1.${id}` })

    expect(story({ devices: [named('nas', 20)], blocked: null }).detail).toContain(
      ' It involves nas on your network.',
    )
    expect(story({ devices: [named(null, 21)], blocked: null }).detail).toContain(
      'It involves 192.168.1.21 on your network.',
    )
    expect(story({ devices: [named('nas', 20), named('tv', 21)], blocked: null }).detail).toContain(
      'It involves nas and tv on your network.',
    )
    expect(
      story({
        devices: [named('a', 1), named('b', 2), named('c', 3), named('d', 4), named('e', 5)],
        blocked: null,
      }).detail,
    ).toContain('It involves a, b, c and 2 more on your network.')
  })

  it('says how often the firewall turned the address away, if it did', () => {
    expect(story({ devices: [], blocked: 12 }).detail).toContain(
      ' The firewall turned the address away 12 times around then.',
    )
    expect(story({ devices: [], blocked: 1 }).detail).toContain('away once around then.')
    expect(story({ devices: [], blocked: 0 }).detail).not.toContain('firewall')
    expect(story({ devices: [], blocked: null }).detail).not.toContain('firewall')
  })
})
