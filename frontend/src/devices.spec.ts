import type { LocationQuery } from 'vue-router'

import {
  DEFAULT_SORT,
  NO_FILTERS,
  SCOPE,
  activeFilters,
  connectionsOf,
  filtersOf,
  incomingShare,
  nameOf,
  queryOf,
  routeQuery,
} from '@/devices'
import { device, deviceAsset } from '@/test/devices'

describe('what the address of the page says', () => {
  it('is no filters when it says nothing', () => {
    expect(filtersOf({})).toEqual(NO_FILTERS)
  })

  it('reads every choice', () => {
    const query: LocationQuery = {
      q: 'camera',
      scope: 'outside',
      direction: 'incoming',
      flagged: '1',
      sort: 'busiest',
    }

    expect(filtersOf(query)).toEqual({
      q: 'camera',
      scope: 'outside',
      direction: 'incoming',
      flagged: true,
      sort: 'busiest',
    })
  })

  it('ignores what is not one of the choices', () => {
    expect(
      filtersOf({ scope: 'moon', direction: 'sideways', sort: 'size', flagged: 'yes', q: ['a'] }),
    ).toEqual(NO_FILTERS)
  })

  it('is written back as only what differs from showing everything', () => {
    expect(routeQuery(NO_FILTERS)).toEqual({})
    expect(
      routeQuery({
        q: '  tv ',
        scope: 'yours',
        direction: 'outgoing',
        flagged: true,
        sort: 'address',
      }),
    ).toEqual({ q: 'tv', scope: 'yours', direction: 'outgoing', flagged: '1', sort: 'address' })
  })

  it('is written and read back as the same filters', () => {
    const filters = { ...NO_FILTERS, scope: 'local' as const, q: 'tv' }

    expect(filtersOf(routeQuery(filters))).toEqual(filters)
  })
})

describe('what to ask for', () => {
  it('leaves out what is not narrowed', () => {
    expect(queryOf(NO_FILTERS, 30)).toEqual({
      flagged: false,
      sort: DEFAULT_SORT,
      limit: 30,
      offset: 0,
    })
  })

  it('has every choice, with the words trimmed, and where to start', () => {
    expect(
      queryOf(
        { q: ' tv ', scope: 'yours', direction: 'incoming', flagged: true, sort: 'busiest' },
        10,
        20,
      ),
    ).toEqual({
      q: 'tv',
      scope: 'yours',
      direction: 'incoming',
      flagged: true,
      sort: 'busiest',
      limit: 10,
      offset: 20,
    })
  })
})

describe('how many choices narrow the list', () => {
  it('counts each choice but the scope and the order', () => {
    expect(activeFilters({ ...NO_FILTERS, scope: 'yours', sort: 'address' })).toBe(0)
    expect(activeFilters({ ...NO_FILTERS, q: ' ', direction: 'incoming', flagged: true })).toBe(2)
    expect(activeFilters({ ...NO_FILTERS, q: 'x' })).toBe(1)
  })
})

describe('the scopes', () => {
  it('each has a name, an icon and a meaning, so none is only a color', () => {
    for (const look of Object.values(SCOPE)) {
      expect(look.label).not.toBe('')
      expect(look.description).not.toBe('')
      expect(look.icon).toBeDefined()
    }
  })
})

describe('what a device says of itself', () => {
  it('is called by its asset, else by its reverse lookup, else by nothing', () => {
    expect(nameOf(device({ asset: deviceAsset({ name: 'Laptop' }), name: 'x.test' }))).toBe(
      'Laptop',
    )
    expect(nameOf(device({ name: 'example.test' }))).toBe('example.test')
    expect(nameOf(device())).toBeNull()
  })

  it('has connections both ways, and the share that was made to it', () => {
    expect(connectionsOf({ incoming: 3, outgoing: 1 })).toBe(4)
    expect(incomingShare({ incoming: 3, outgoing: 1 })).toBe(75)
    expect(incomingShare({ incoming: 0, outgoing: 0 })).toBe(0)
  })
})
