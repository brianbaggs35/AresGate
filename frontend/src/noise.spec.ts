import { logsQuery, nameOf, percentOf, scopeOf, shareOf, summaryOf, UNNAMED } from '@/noise'
import { noisySignature, sourceAlerts } from '@/test/dashboard'

describe('shareOf and percentOf', () => {
  it('is what part of the whole a count is', () => {
    expect(shareOf(1, 4)).toBe(0.25)
    expect(percentOf(3_642, 4_460)).toBe('82%')
    expect(percentOf(4_460, 4_460)).toBe('100%')
  })

  it('is nothing when there is no whole, and never more than all of it', () => {
    expect(shareOf(5, 0)).toBe(0)
    expect(percentOf(0, 0)).toBe('0%')
    expect(shareOf(9, 4)).toBe(1)
  })

  it('says under 1% for a count that is something but rounds to nothing', () => {
    expect(percentOf(2, 10_000)).toBe('under 1%')
    expect(percentOf(0, 10_000)).toBe('0%')
  })
})

describe('nameOf', () => {
  it('is the rule, or says there is none', () => {
    expect(nameOf({ signature: 'Blacklisted flow' })).toBe('Blacklisted flow')
    expect(nameOf({ signature: null })).toBe(UNNAMED)
  })
})

describe('logsQuery', () => {
  it('finds the alert from the program in the window of the dashboard', () => {
    const item = { source: 'ntopng', signature: 'Blacklisted flow' }

    expect(logsQuery(item, '24h')).toBe(
      'kind:alert source:ntopng signature:"Blacklisted flow" since:24h',
    )
    expect(logsQuery(item, '7d')).toBe(
      'kind:alert source:ntopng signature:"Blacklisted flow" since:7d',
    )
  })

  it('leaves out the rule when there is none, and the quotes in one that has them', () => {
    expect(logsQuery({ source: 'wazuh', signature: null }, '24h')).toBe(
      'kind:alert source:wazuh since:24h',
    )
    expect(logsQuery({ source: 'wazuh', signature: 'a "b" c' }, '24h')).toBe(
      'kind:alert source:wazuh signature:"a  b  c" since:24h',
    )
  })

  it('leaves out a rule that is only quotes', () => {
    expect(logsQuery({ source: 'wazuh', signature: '""' }, '24h')).toBe(
      'kind:alert source:wazuh since:24h',
    )
  })
})

describe('scopeOf', () => {
  it('is every alert like it from that program, whichever address it comes from', () => {
    expect(scopeOf(noisySignature())).toEqual({
      key: 'alert:ntopng:Blacklisted flow',
      title: '“Blacklisted flow”',
      hint: 'From any address, as seen by ntopng',
      request: { source: 'ntopng', signature: 'Blacklisted flow' },
    })
  })

  it('is nothing for an alert that names no rule: there is nothing to judge it by', () => {
    expect(scopeOf(noisySignature({ signature: null }))).toBeNull()
  })
})

describe('summaryOf', () => {
  it('says nothing when there are no alerts', () => {
    expect(summaryOf({ sources: [], signatures: [] }, 0)).toBe('')
  })

  it('names the program that reported most, and how many of its alerts were serious', () => {
    const noise = {
      sources: [
        sourceAlerts({ total: 3_610, serious: 3_598 }),
        sourceAlerts({ source: 'wazuh', source_name: 'Wazuh', total: 850, serious: 44 }),
      ],
      signatures: [],
    }

    expect(summaryOf(noise, 4_460)).toBe(
      'ntopng reported 3,610 of the 4,460 alerts (81%), 3,598 of them high or critical.',
    )
  })

  it('says all of them when one program reported them all, and when none was serious', () => {
    const noise = { sources: [sourceAlerts({ total: 7, serious: 0 })], signatures: [] }

    expect(summaryOf(noise, 7)).toBe(
      'ntopng reported all 7 of the alerts, none of them high or critical.',
    )
  })

  it('adds how many were between two addresses on the network', () => {
    const noise = {
      sources: [
        sourceAlerts({ total: 60, serious: 10, inside: 30 }),
        sourceAlerts({ source: 'wazuh', source_name: 'Wazuh', total: 40, serious: 0, inside: 10 }),
      ],
      signatures: [],
    }

    expect(summaryOf(noise, 100)).toBe(
      'ntopng reported 60 of the 100 alerts (60%), 10 of them high or critical. 40 (40%) of all of them were between two addresses on your own network.',
    )
  })
})
