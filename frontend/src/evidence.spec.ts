import {
  agreedBy,
  hasDetail,
  namedByKind,
  namedLook,
  reportsOf,
  share,
  volumesOf,
  worthListing,
} from '@/evidence'
import { confirmation, evidence, occurrence, signal } from '@/test/incidents'

describe('namedLook', () => {
  it('says what a kind of thing is called, and has a fallback for one it does not know', () => {
    expect(namedLook('hostname').label).toBe('Host name')
    expect(namedLook('url').plural).toBe('Addresses asked for')
    expect(namedLook('something-new')).toMatchObject({
      label: 'something-new',
      plural: 'something-new',
    })
  })
})

describe('namedByKind', () => {
  it('groups by kind in the order the kinds first appear', () => {
    const items = [
      { kind: 'user', value: 'root' },
      { kind: 'dns', value: 'a.example' },
      { kind: 'user', value: 'admin' },
    ]

    expect(namedByKind(items)).toEqual([
      ['user', [items[0], items[2]]],
      ['dns', [items[1]]],
    ])
    expect(namedByKind([])).toEqual([])
  })
})

describe('share', () => {
  it('draws against the largest, and never so thin that it is not seen', () => {
    expect(share(50, 100)).toBe(50)
    expect(share(100, 100)).toBe(100)
    expect(share(1, 1000)).toBe(4)
    expect(share(0, 0)).toBe(0)
  })
})

describe('volumesOf', () => {
  it('says each volume that was counted, and how much of the whole went out', () => {
    expect(volumesOf({ packets_out: 3, packets_in: 1, bytes_out: 2048, bytes_in: 2048 })).toEqual([
      { label: 'Packets', out: 3, in: 1, outText: '3', inText: '1', outShare: 75 },
      { label: 'Data', out: 2048, in: 2048, outText: '2.0 KB', inText: '2.0 KB', outShare: 50 },
    ])
  })

  it('leaves out what was not counted and says which side was not said', () => {
    expect(
      volumesOf({ packets_out: 3, packets_in: null, bytes_out: null, bytes_in: null }),
    ).toEqual([
      { label: 'Packets', out: 3, in: 0, outText: '3', inText: 'not said', outShare: 100 },
    ])
    expect(
      volumesOf({ packets_out: null, packets_in: 4, bytes_out: null, bytes_in: null })[0],
    ).toMatchObject({ outText: 'not said', inText: '4', outShare: 0 })
  })

  it('splits evenly a flow that carried nothing', () => {
    expect(
      volumesOf({ packets_out: 0, packets_in: 0, bytes_out: null, bytes_in: null })[0]?.outShare,
    ).toBe(50)
  })

  it('is nothing for a program that gave none', () => {
    expect(volumesOf(null)).toEqual([])
    expect(
      volumesOf({ packets_out: null, packets_in: null, bytes_out: null, bytes_in: null }),
    ).toEqual([])
  })
})

describe('hasDetail', () => {
  it('is false for nothing and for an evidence with nothing in it', () => {
    expect(hasDetail(null)).toBe(false)
    expect(hasDetail(evidence())).toBe(false)
  })

  it.each([
    { facts: [{ label: 'Rule', value: '1' }] },
    { tags: ['sshd'] },
    { mitre: [{ id: 'T1110', tactic: '', technique: 'Brute Force' }] },
    { named: [{ kind: 'user', value: 'root' }] },
    { traffic: { packets_out: 1, packets_in: null, bytes_out: null, bytes_in: null } },
    { host: 'web1' },
    { app: 'ssh' },
    { excerpt: 'a line' },
  ])('is true when the program said %j', (said) => {
    expect(hasDetail(evidence(said))).toBe(true)
  })
})

describe('reports and what is worth listing', () => {
  const wazuh = evidence({ host: 'web1' })
  const agreed = occurrence({
    signal: signal({ source: 'wazuh', source_name: 'Wazuh' }),
    evidence: wazuh,
    duplicates: 2,
    confirmations: [
      confirmation(),
      confirmation({ source: 'ntopng', source_name: 'ntopng', evidence: evidence({ app: 'ssh' }) }),
    ],
  })

  it('lists the program that reported it first, then the programs that agreed', () => {
    expect(reportsOf(agreed)).toEqual([
      { source: 'wazuh', name: 'Wazuh', evidence: wazuh },
      { source: 'opnsense', name: 'OPNsense', evidence: null },
      { source: 'ntopng', name: 'ntopng', evidence: evidence({ app: 'ssh' }) },
    ])
  })

  it('names the programs that agreed, or says another did where that is all that is known', () => {
    expect(agreedBy(agreed)).toBe('OPNsense and ntopng')
    expect(agreedBy(occurrence({ duplicates: 1 }))).toBe('another program')
  })

  it.each([
    [occurrence(), false],
    [occurrence({ count: 2 }), true],
    [occurrence({ duplicates: 1 }), true],
    [occurrence({ confirmations: [confirmation()] }), true],
    [occurrence({ evidence: evidence({ app: 'ssh' }) }), true],
    [occurrence({ evidence: evidence() }), false],
  ])('whether %# is worth listing', (item, listed) => {
    expect(worthListing(item)).toBe(listed)
  })
})
