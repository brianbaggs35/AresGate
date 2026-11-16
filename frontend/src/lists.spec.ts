import { LIST_PAGES, programsOf, queryOfRoute, sameQuery } from '@/lists'

describe('queryOfRoute', () => {
  it('keeps what is set, one value or several', () => {
    expect(queryOfRoute({ view: 'all', status: ['open', 'resolved'], q: 'ssh' })).toEqual({
      view: 'all',
      status: ['open', 'resolved'],
      q: 'ssh',
    })
  })

  it('leaves out what is empty or has no value', () => {
    expect(queryOfRoute({ a: '', b: null, c: [null, ''], d: ['x', null] })).toEqual({ d: ['x'] })
  })
})

describe('sameQuery', () => {
  it('is true for the same filters in any order', () => {
    expect(sameQuery({ a: '1', b: ['x', 'y'] }, { b: ['x', 'y'], a: '1' })).toBe(true)
  })

  it('is false when a filter is missing, extra or different', () => {
    expect(sameQuery({ a: '1' }, {})).toBe(false)
    expect(sameQuery({ a: '1' }, { b: '1' })).toBe(false)
    expect(sameQuery({ a: '1' }, { a: '2' })).toBe(false)
    expect(sameQuery({ a: ['1'] }, { a: '1' })).toBe(false)
  })

  it('is true for none and none', () => {
    expect(sameQuery({}, {})).toBe(true)
  })
})

describe('programsOf', () => {
  it('names the integrations a filter or a word of the search is narrowed to', () => {
    expect(programsOf({ source: ['OPNsense', 'wazuh'] })).toEqual(['opnsense', 'wazuh'])
    expect(programsOf({ source: 'wazuh' })).toEqual(['wazuh'])
    expect(programsOf({ q: 'severity>=high source:wazuh -port:22 source:"crowdsec"' })).toEqual([
      'wazuh',
      'crowdsec',
    ])
  })

  it('names each once, and none where there are none', () => {
    expect(programsOf({ source: 'wazuh', q: 'source:Wazuh' })).toEqual(['wazuh'])
    expect(programsOf({ view: 'all' })).toEqual([])
    expect(programsOf({ q: ['source:a'] })).toEqual([])
  })
})

describe('LIST_PAGES', () => {
  it('has a page for each list that keeps views', () => {
    expect(Object.keys(LIST_PAGES)).toEqual(['incidents', 'alerts', 'devices', 'assets'])
  })
})
