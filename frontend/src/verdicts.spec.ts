import type { Signal } from '@/api/incidents'
import type { Verdict } from '@/api/verdicts'
import { detail, signal } from '@/test/incidents'
import { verdict as rule } from '@/test/verdicts'
import {
  VERDICT,
  aboutVerdict,
  givenAs,
  isMuting,
  mutedIn,
  scopesOf,
  standing,
  verdictsIn,
} from '@/verdicts'

describe('what each verdict looks like', () => {
  it('has a name, an icon and a meaning, so it is never only a color', () => {
    for (const look of Object.values(VERDICT)) {
      expect(look.label).not.toBe('')
      expect(look.icon).toBeTruthy()
      expect(look.meaning).not.toBe('')
    }
    expect(Object.values(VERDICT).map((look) => look.label)).toEqual([
      'Not suspicious',
      'Low priority',
      'Real threat',
    ])
  })

  it('keeps a signal from counting unless it is a threat', () => {
    expect(isMuting('not_suspicious')).toBe(true)
    expect(isMuting('low_priority')).toBe(true)
    expect(isMuting('threat')).toBe(false)
  })
})

describe('mutedIn', () => {
  it('counts the signals a verdict keeps from counting', () => {
    expect(mutedIn({ verdict_counts: {} })).toBe(0)
    expect(mutedIn({ verdict_counts: { not_suspicious: 2, low_priority: 1, threat: 4 } })).toBe(3)
  })
})

describe('standing', () => {
  const base = { verdict: null, verdict_counts: {}, signal_count: 4, filtered_count: 0 } as const

  it('says nothing was said', () => {
    expect(standing(base)).toBe("You haven't said anything about it yet.")
  })

  it('says how many signals are left out when some are', () => {
    expect(standing({ ...base, verdict_counts: { low_priority: 1 } })).toBe(
      '1 of its 4 signals match a verdict you gave and are not counted.',
    )
  })

  it('says how many signals the noise filters set aside', () => {
    expect(standing({ ...base, filtered_count: 3 })).toBe(
      '3 of its 4 signals were set aside by your noise filters and are not counted.',
    )
  })

  it('says both when verdicts and noise filters left some out', () => {
    expect(standing({ ...base, verdict_counts: { not_suspicious: 1 }, filtered_count: 2 })).toBe(
      '1 of its 4 signals match a verdict you gave and 2 were set aside by your noise filters, so none of those are counted.',
    )
  })

  it('says it raises no alarm when the noise filters, or them and verdicts, left every signal out', () => {
    const none = 'sure of nothing and will not raise an alarm'

    expect(standing({ ...base, filtered_count: 4 })).toContain(none)
    expect(standing({ ...base, verdict_counts: { low_priority: 1 }, filtered_count: 3 })).toBe(
      'Every signal in it was left out by a verdict you gave or your noise filters, so AresGate is sure of nothing and will not raise an alarm for it.',
    )
  })

  it('says it raises no alarm when every signal is left out', () => {
    expect(standing({ ...base, verdict: 'not_suspicious' })).toContain('will not raise an alarm')
    expect(standing({ ...base, verdict: 'low_priority' })).toContain('sure of nothing')
  })

  it('says the owner called it a threat', () => {
    expect(standing({ ...base, verdict: 'threat' })).toBe(
      'You said it is a real threat, so AresGate is certain of it.',
    )
  })
})

describe('aboutVerdict', () => {
  const none = {
    address: null,
    destination: null,
    source: null,
    source_name: null,
    signature: null,
  }

  it.each<[string, Partial<Verdict>, string]>([
    ['an address', { address: '93.184.216.34' }, '93.184.216.34'],
    [
      'an address as one program saw it',
      { address: '93.184.216.34', source: 'wazuh', source_name: 'Wazuh' },
      'Anything about 93.184.216.34, as seen by Wazuh',
    ],
    ['a program', { source: 'wazuh', source_name: 'Wazuh' }, 'Everything Wazuh reports'],
    ['a program this version has no name for', { source: 'zeek' }, 'Everything zeek reports'],
    ['a signature', { signature: 'ET SCAN' }, '“ET SCAN” from any address'],
    [
      'a signature from an address',
      { signature: 'ET SCAN', address: '93.184.216.34' },
      '“ET SCAN” from 93.184.216.34',
    ],
    [
      'all three',
      { signature: 'ET SCAN', address: '93.184.216.34', source: 'wazuh', source_name: 'Wazuh' },
      '“ET SCAN” from 93.184.216.34, as seen by Wazuh',
    ],
    [
      'a device sending to a network',
      { address: '192.168.1.20', destination: '52.1.2.0/24' },
      'Traffic from 192.168.1.20 to 52.1.2.0/24',
    ],
    [
      'a signature a device sent to an address, as one program saw it',
      {
        signature: 'ET POLICY',
        address: '192.168.1.20',
        destination: '52.1.2.9',
        source: 'ntopng',
        source_name: 'ntopng',
      },
      '“ET POLICY” from 192.168.1.20 to 52.1.2.9, as seen by ntopng',
    ],
    [
      'a destination with no device named',
      { destination: '52.1.2.0/24' },
      'Traffic from any address to 52.1.2.0/24',
    ],
  ])('says %s', (_name, changes, words) => {
    expect(aboutVerdict({ ...none, ...changes })).toBe(words)
  })

  it('has something to say about a verdict with nothing to match, which the API refuses', () => {
    expect(aboutVerdict(none)).toBe('Everything one program reports')
  })
})

describe('scopesOf', () => {
  it('offers the address, then each alert from anywhere, then each alert from the address', () => {
    const scopes = scopesOf(
      detail({
        signals: [
          signal(),
          signal({ source: 'opnsense', source_name: 'OPNsense', signature: 'ET SCAN' }),
          signal({ signature: 'Brute force on ssh' }),
          signal({ signature: null }),
        ],
      }),
    )

    expect(scopes.map(({ title }) => title)).toEqual([
      '93.184.216.34',
      '“Brute force on ssh”',
      '“ET SCAN”',
      '“Brute force on ssh” from 93.184.216.34',
      '“ET SCAN” from 93.184.216.34',
    ])
    expect(scopes.map(({ request }) => request)).toEqual([
      { address: '93.184.216.34' },
      { source: 'wazuh', signature: 'Brute force on ssh' },
      { source: 'opnsense', signature: 'ET SCAN' },
      { address: '93.184.216.34', source: 'wazuh', signature: 'Brute force on ssh' },
      { address: '93.184.216.34', source: 'opnsense', signature: 'ET SCAN' },
    ])
    expect(scopes[2]?.hint).toBe('From any address, as seen by OPNsense')
    expect(scopes[4]?.hint).toBe('Only this address, as seen by OPNsense')
    expect(new Set(scopes.map(({ key }) => key)).size).toBe(scopes.length)
  })

  it('offers only the alerts of an incident about a rule, which has no address', () => {
    const scopes = scopesOf(detail({ subject: 'rule:wazuh:5710' }))

    expect(scopes.map(({ title }) => title)).toEqual([
      '“Brute force on ssh”',
      '“ET SCAN Potential SSH Scan”',
    ])
  })

  it('offers nothing where there is nothing to match', () => {
    expect(
      scopesOf(detail({ subject: 'rule:wazuh:5710', signals: [signal({ signature: null })] })),
    ).toEqual([])
  })

  it('offers an address alone where the signals have no signature', () => {
    const scopes = scopesOf(detail({ signals: [signal({ signature: null })] }))

    expect(scopes.map(({ title }) => title)).toEqual(['93.184.216.34'])
  })

  it('offers only so many alerts', () => {
    const many = Array.from({ length: 9 }, (_, number) =>
      signal({ signature: `Alert ${number.toString()}` }),
    )

    const scopes = scopesOf(detail({ signals: many }))

    // The address, and four alerts twice.
    expect(scopes).toHaveLength(9)
  })
})

describe('where a device sends its traffic', () => {
  const inside = '192.168.1.20'

  /** The titles of the scopes about where a device sent its traffic, for the signals given. */
  const sentTo = (...changes: Partial<Signal>[]) =>
    scopesOf(detail({ signals: changes.map((change) => signal(change)) }))
      .filter(({ key }) => key.startsWith('sent:'))
      .map(({ title }) => title)

  it('offers the address the device sent to, then the whole network it is in', () => {
    const scopes = scopesOf(
      detail({ signals: [signal({ src_address: inside, dst_address: '52.1.2.9' })] }),
    )

    expect(scopes.slice(-2)).toEqual([
      {
        key: 'sent:192.168.1.20>52.1.2.9',
        title: 'Traffic from 192.168.1.20 to 52.1.2.9',
        hint: 'Only what this device sends there',
        request: { address: inside, destination: '52.1.2.9' },
      },
      {
        key: 'sent:192.168.1.20>52.1.2.0/24',
        title: 'Traffic from 192.168.1.20 to 52.1.2.0/24',
        hint: 'Only what this device sends to the whole network',
        request: { address: inside, destination: '52.1.2.0/24' },
      },
    ])
  })

  it('offers a whole network once, however many of its addresses the device sent to', () => {
    expect(
      sentTo(
        { src_address: inside, dst_address: '52.1.2.9' },
        { src_address: inside, dst_address: '52.1.2.8' },
      ),
    ).toEqual([
      'Traffic from 192.168.1.20 to 52.1.2.9',
      'Traffic from 192.168.1.20 to 52.1.2.0/24',
      'Traffic from 192.168.1.20 to 52.1.2.8',
    ])
  })

  it('offers an IPv6 address alone, as no network of it is offered', () => {
    expect(sentTo({ src_address: inside, dst_address: '2606:2800:220:1::1' })).toEqual([
      'Traffic from 192.168.1.20 to 2606:2800:220:1::1',
    ])
  })

  it('counts the private ranges a home network hands out as inside, and nothing else', () => {
    expect(sentTo({ src_address: '10.0.0.5', dst_address: '52.1.2.9' })).toHaveLength(2)
    expect(sentTo({ src_address: '172.20.0.5', dst_address: '52.1.2.9' })).toHaveLength(2)
    expect(sentTo({ src_address: 'fd12:3456::7', dst_address: '52.1.2.9' })).toHaveLength(2)
    expect(sentTo({ src_address: '172.32.0.5', dst_address: '52.1.2.9' })).toEqual([])
    expect(sentTo({ src_address: '93.184.216.34', dst_address: '52.1.2.9' })).toEqual([])
  })

  it('keeps to a few devices, not every one that sent something', () => {
    expect(
      sentTo(
        { src_address: inside, dst_address: '52.1.2.9' },
        { src_address: inside, dst_address: '52.1.3.9' },
        { src_address: '192.168.1.30', dst_address: '52.1.4.9' },
      ),
    ).toEqual([
      'Traffic from 192.168.1.20 to 52.1.2.9',
      'Traffic from 192.168.1.20 to 52.1.2.0/24',
      'Traffic from 192.168.1.20 to 52.1.3.9',
      'Traffic from 192.168.1.20 to 52.1.3.0/24',
    ])
  })

  it('skips a signal that names no destination, no device, or the device itself', () => {
    expect(
      sentTo(
        { src_address: inside, dst_address: null },
        { src_address: null, dst_address: '52.1.2.9' },
        { src_address: inside, dst_address: inside },
      ),
    ).toEqual([])
  })
})

describe('givenAs', () => {
  it('says what was remembered', () => {
    const [scope] = scopesOf(detail())

    expect(givenAs(scope!, 'low_priority')).toBe('Remembered: 93.184.216.34 is low priority.')
    expect(givenAs(scope!, 'threat')).toBe('Remembered: 93.184.216.34 is a real threat.')
  })
})

describe('verdictsIn', () => {
  it('finds the verdicts that were applied to the signals of an incident', () => {
    const incident = detail({
      signals: [signal({ verdict_rule_id: 2 }), signal({ verdict_rule_id: null })],
    })

    expect(verdictsIn(incident, [rule({ id: 1 }), rule({ id: 2 })]).map(({ id }) => id)).toEqual([
      2,
    ])
  })
})
