import {
  INCIDENT_SEARCH,
  LOG_EXAMPLES,
  LOG_RECENT_KEY,
  LOG_SEARCH,
  MAX_RECENT,
  RECENT_KEY,
  SEARCH_EXAMPLES,
  forget,
  groupsOf,
  hasTerm,
  impliedBy,
  kindChoices,
  readRecent,
  remember,
  severityChoices,
  sourceChoices,
  toggled,
  without,
  zone,
} from '@/search'

describe('taking a term out', () => {
  it('leaves the others with one space between them', () => {
    const text = 'ssh -source:wazuh  severity>=high'

    expect(without(text, { start: 4, end: 17 })).toBe('ssh severity>=high')
    expect(without(text, { start: 0, end: 3 })).toBe('-source:wazuh  severity>=high')
    expect(without(text, { start: 19, end: 33 })).toBe('ssh -source:wazuh')
  })

  it('leaves nothing when it was all there was', () => {
    expect(without('ssh', { start: 0, end: 3 })).toBe('')
  })
})

describe('finding a term', () => {
  it('is a whole term, written just so, in any case', () => {
    expect(hasTerm('ssh severity:high', 'severity:high')).toBe(true)
    expect(hasTerm('SEVERITY:HIGH', 'severity:high')).toBe(true)
    expect(hasTerm('severity:high', 'severity:high')).toBe(true)
    expect(hasTerm('severity:higher', 'severity:high')).toBe(false)
    expect(hasTerm('-severity:high', 'severity:high')).toBe(false)
    expect(hasTerm('', 'severity:high')).toBe(false)
  })

  it('is not fooled by what makes a pattern', () => {
    expect(hasTerm('address:10.0.0.0/8', 'address:10.0.0.0/8')).toBe(true)
    expect(hasTerm('address:10x0x0x0/8', 'address:10.0.0.0/8')).toBe(false)
    expect(hasTerm('a+b', 'a+b')).toBe(true)
  })
})

describe('turning a term on and off', () => {
  it('puts it at the end of the text', () => {
    expect(toggled('', 'source:wazuh')).toBe('source:wazuh')
    expect(toggled('  ', 'source:wazuh')).toBe('source:wazuh')
    expect(toggled('ssh ', 'source:wazuh')).toBe('ssh source:wazuh')
  })

  it('takes it out if it is there, and tidies up', () => {
    expect(toggled('ssh source:wazuh port:22', 'source:wazuh')).toBe('ssh port:22')
    expect(toggled('source:wazuh', 'source:wazuh')).toBe('')
    expect(toggled('ssh   source:wazuh', 'source:wazuh')).toBe('ssh')
  })
})

describe('what a search gives way to', () => {
  it('is every status when it names one, and the quieted ones when it names a verdict', () => {
    expect(impliedBy('ssh')).toEqual({ allStatuses: false, quieted: false })
    expect(impliedBy('status:resolved')).toEqual({ allStatuses: true, quieted: false })
    expect(impliedBy('ssh -status=open')).toEqual({ allStatuses: true, quieted: false })
    expect(impliedBy('VERDICT:threat')).toEqual({ allStatuses: false, quieted: true })
    expect(impliedBy('"status:x"')).toEqual({ allStatuses: false, quieted: false })
    expect(impliedBy('mystatus:x')).toEqual({ allStatuses: false, quieted: false })
  })
})

describe('the searches that are remembered', () => {
  afterEach(() => {
    localStorage.clear()
  })

  it('start as none', () => {
    expect(readRecent(RECENT_KEY)).toEqual([])
  })

  it('come back newest first, once each', () => {
    remember('ssh', RECENT_KEY)
    remember('source:wazuh', RECENT_KEY)
    remember('  ssh ', RECENT_KEY)

    expect(readRecent(RECENT_KEY)).toEqual(['ssh', 'source:wazuh'])
  })

  it('are only so many', () => {
    for (let n = 0; n < MAX_RECENT + 3; n++) remember(`port:${n + 1}`, RECENT_KEY)

    const recent = readRecent(RECENT_KEY)
    expect(recent).toHaveLength(MAX_RECENT)
    expect(recent[0]).toBe(`port:${MAX_RECENT + 3}`)
  })

  it('do not include a search of nothing', () => {
    expect(remember('   ', RECENT_KEY)).toEqual([])
    expect(localStorage.getItem(RECENT_KEY)).toBeNull()
  })

  it('can be forgotten', () => {
    remember('ssh', RECENT_KEY)
    forget(RECENT_KEY)

    expect(readRecent(RECENT_KEY)).toEqual([])
  })

  it('ignore what is in storage that is not a list of searches', () => {
    localStorage.setItem(RECENT_KEY, '{"a":1}')
    expect(readRecent(RECENT_KEY)).toEqual([])

    localStorage.setItem(RECENT_KEY, 'not json')
    expect(readRecent(RECENT_KEY)).toEqual([])

    localStorage.setItem(RECENT_KEY, JSON.stringify(['ssh', 4, '  ', null, 'port:22']))
    expect(readRecent(RECENT_KEY)).toEqual(['ssh', 'port:22'])
  })

  it('still work for the visit where storage is off', () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('blocked')
    })
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('blocked')
    })
    vi.spyOn(Storage.prototype, 'removeItem').mockImplementation(() => {
      throw new Error('blocked')
    })

    expect(readRecent(RECENT_KEY)).toEqual([])
    expect(remember('ssh', RECENT_KEY)).toEqual(['ssh'])
    expect(() => {
      forget(RECENT_KEY)
    }).not.toThrow()
  })
})

describe('the way to search', () => {
  it.each([
    ['incidents', SEARCH_EXAMPLES],
    ['logs', LOG_EXAMPLES],
  ])('is shown for the %s with examples, each of them whole', (_name, examples) => {
    expect(examples.length).toBeGreaterThan(10)
    for (const { text, meaning } of examples) {
      expect(text).not.toBe('')
      expect(meaning).not.toBe('')
    }
  })

  it('keeps the searches of the incidents and of the logs apart', () => {
    expect(INCIDENT_SEARCH.recentKey).toBe(RECENT_KEY)
    expect(LOG_SEARCH.recentKey).toBe(LOG_RECENT_KEY)
    expect(RECENT_KEY).not.toBe(LOG_RECENT_KEY)
    expect(LOG_SEARCH.examples).toBe(LOG_EXAMPLES)
  })

  it('remembers the searches of each under its own name', () => {
    remember('ssh', RECENT_KEY)
    remember('kind:alert', LOG_RECENT_KEY)

    expect(readRecent(RECENT_KEY)).toEqual(['ssh'])
    expect(readRecent(LOG_RECENT_KEY)).toEqual(['kind:alert'])

    localStorage.clear()
  })

  it('has a time zone to say where the person is', () => {
    expect(zone()).toEqual(expect.any(String))
  })

  it('has no time zone to say when the browser has none', () => {
    vi.spyOn(Intl, 'DateTimeFormat').mockReturnValue({
      resolvedOptions: () => ({ timeZone: '' }),
    } as Intl.DateTimeFormat)

    expect(zone()).toBeUndefined()
  })
})

describe('the choices under a search', () => {
  const counts = { info: 0, low: 2, medium: 0, high: 5, critical: 1 }
  const labels = (choices: { label: string; count: number }[]) =>
    choices.map(({ label, count }) => `${label}${count.toString()}`)

  it('are the severities that have any, the most serious first', () => {
    expect(labels(severityChoices(counts, ''))).toEqual(['Critical1', 'High5', 'Low2'])
  })

  it('give a severity its color and icon, and the others none', () => {
    const [critical] = severityChoices(counts, '')
    const [wazuh] = sourceChoices([{ key: 'wazuh', name: 'Wazuh', count: 1 }], '')

    expect(critical).toMatchObject({ term: 'severity:critical', color: 'error' })
    expect(critical?.icon).toBeDefined()
    expect(wazuh?.color).toBeUndefined()
    expect(wazuh?.icon).toBeUndefined()
  })

  it('still offer a severity that is on when nothing is left at it', () => {
    const none = { info: 0, low: 0, medium: 0, high: 0, critical: 0 }

    expect(labels(severityChoices(none, 'severity:medium'))).toEqual(['Medium0'])
    expect(severityChoices(none, '')).toEqual([])
  })

  it('are the integrations in the order they are given, and the kinds', () => {
    const sources = [
      { key: 'wazuh', name: 'Wazuh', count: 7 },
      { key: 'crowdsec', name: 'CrowdSec', count: 1 },
    ]

    expect(sourceChoices(sources, '').map(({ term }) => term)).toEqual([
      'source:wazuh',
      'source:crowdsec',
    ])
    expect(
      kindChoices(
        [
          { kind: 'alert', count: 4 },
          { kind: 'firewall', count: 2 },
        ],
        '',
      ).map(({ term, label, count }) => [term, label, count]),
    ).toEqual([
      ['kind:alert', 'alert', 4],
      ['kind:firewall', 'firewall', 2],
    ])
  })

  it('say which are on by the search that is applied', () => {
    const search = 'ssh severity:high source:crowdsec kind:alert'

    expect(severityChoices(counts, search).map(({ on }) => on)).toEqual([false, true, false])
    expect(
      sourceChoices(
        [
          { key: 'wazuh', name: 'Wazuh', count: 7 },
          { key: 'crowdsec', name: 'CrowdSec', count: 1 },
        ],
        search,
      ).map(({ on }) => on),
    ).toEqual([false, true])
    expect(kindChoices([{ kind: 'alert', count: 1 }], search)[0]?.on).toBe(true)
  })

  it('are grouped, leaving out a group with nothing to choose', () => {
    const some = { name: 'Severity', choices: severityChoices(counts, '') }
    const none = { name: 'Kind', choices: [] }

    expect(groupsOf(some, none)).toEqual([some])
    expect(groupsOf(none)).toEqual([])
  })
})
