import type { LocationQuery } from 'vue-router'

import {
  DEFAULT_SORT,
  NO_FILTERS,
  STATUS,
  activeFilters,
  addressesOf,
  filtersOf,
  queryOf,
  routeQuery,
  sourcesOf,
  wayOf,
} from '@/inventory'
import { asset, listed } from '@/test/assets'

describe('what the address of the page says', () => {
  it('is no filters when it says nothing', () => {
    expect(filtersOf({})).toEqual(NO_FILTERS)
  })

  it('reads every choice', () => {
    const query: LocationQuery = {
      status: 'recent',
      q: 'laptop',
      source: ['wazuh', 'ntopng', 'wazuh'],
      interface: '4',
      new: '1',
      unidentified: '1',
      sort: 'name',
    }

    expect(filtersOf(query)).toEqual({
      status: 'recent',
      q: 'laptop',
      sources: ['wazuh', 'ntopng'],
      interface: 4,
      new: true,
      unidentified: true,
      sort: 'name',
    })
  })

  it('reads one source as well as several', () => {
    expect(filtersOf({ source: 'wazuh' }).sources).toEqual(['wazuh'])
  })

  it('ignores what is not one of the choices', () => {
    const filters = filtersOf({
      status: 'asleep',
      sort: 'size',
      interface: '-3',
      new: 'yes',
      source: ['', null],
      q: ['a', 'b'],
    })

    expect(filters).toEqual(NO_FILTERS)
    expect(filtersOf({ interface: 'one' }).interface).toBeNull()
    expect(filtersOf({ interface: '1.5' }).interface).toBeNull()
  })

  it('is written back as only what differs from showing everything', () => {
    expect(routeQuery(NO_FILTERS)).toEqual({})
    expect(
      routeQuery({
        status: 'away',
        q: '  camera ',
        sources: ['wazuh'],
        interface: 2,
        new: true,
        unidentified: true,
        sort: 'address',
      }),
    ).toEqual({
      status: 'away',
      q: 'camera',
      source: ['wazuh'],
      interface: '2',
      new: '1',
      unidentified: '1',
      sort: 'address',
    })
  })

  it('is written and read back as the same filters', () => {
    const filters = { ...NO_FILTERS, status: 'online' as const, q: 'tv', sources: ['ntopng'] }

    expect(filtersOf(routeQuery(filters) as LocationQuery)).toEqual(filters)
  })
})

describe('what to ask for', () => {
  it('leaves out what is not narrowed', () => {
    expect(queryOf(NO_FILTERS, 30)).toEqual({
      sources: [],
      new: false,
      unidentified: false,
      sort: DEFAULT_SORT,
      limit: 30,
      offset: 0,
    })
  })

  it('has every choice, with the words trimmed, and where to start', () => {
    expect(
      queryOf(
        { ...NO_FILTERS, status: 'online', q: ' tv ', sources: ['wazuh'], interface: 3, new: true },
        10,
        20,
      ),
    ).toMatchObject({
      q: 'tv',
      status: 'online',
      sources: ['wazuh'],
      interface: 3,
      new: true,
      limit: 10,
      offset: 20,
    })
  })
})

describe('how many choices narrow the list', () => {
  it('counts each choice but the state and the order', () => {
    expect(activeFilters({ ...NO_FILTERS, status: 'away', sort: 'name' })).toBe(0)
    expect(
      activeFilters({
        ...NO_FILTERS,
        q: ' ',
        sources: ['a', 'b'],
        interface: 1,
        new: true,
        unidentified: true,
      }),
    ).toBe(5)
    expect(activeFilters({ ...NO_FILTERS, q: 'x' })).toBe(1)
  })
})

describe('the programs that listed an asset', () => {
  it('has each once, with its ways and when it last listed it', () => {
    const found = sourcesOf({
      listings: [
        listed({ via: 'arp', via_label: 'ARP table', last_seen_at: '2026-11-01T11:00:00Z' }),
        listed({ via: 'dhcp', via_label: 'DHCP leases', last_seen_at: '2026-11-01T11:30:00Z' }),
        listed({ via: 'x', via_label: 'Older', last_seen_at: '2026-11-01T10:00:00Z' }),
        listed({
          source: 'wazuh',
          source_name: 'Wazuh',
          via_label: 'Agent',
          matched_by: 'hostname',
        }),
      ],
    })

    expect(found).toEqual([
      {
        key: 'opnsense',
        name: 'OPNsense',
        ways: ['ARP table', 'DHCP leases', 'Older'],
        last_seen_at: '2026-11-01T11:30:00Z',
      },
      {
        key: 'wazuh',
        name: 'Wazuh',
        ways: ['Agent (matched by hostname)'],
        last_seen_at: '2026-11-01T11:58:00Z',
      },
    ])
  })

  it('has none for an asset nothing lists', () => {
    expect(sourcesOf({ listings: [] })).toEqual([])
  })

  it('says how a machine was matched to a device, because that is a guess', () => {
    expect(wayOf(listed())).toBe('ARP table')
    expect(wayOf(listed({ via_label: 'Agent', matched_by: 'address' }))).toBe(
      'Agent (matched by address)',
    )
  })
})

describe('the addresses of an asset to show in a list', () => {
  it('has the ones it has now, up to a few, and how many more there are', () => {
    const addresses = ['10.0.0.1', '10.0.0.2', '10.0.0.3', '10.0.0.4', '10.0.0.5']

    expect(addressesOf({ addresses, current_addresses: 5 })).toEqual({
      shown: addresses.slice(0, 3),
      more: 2,
    })
    expect(addressesOf({ addresses, current_addresses: 2 })).toEqual({
      shown: addresses.slice(0, 2),
      more: 3,
    })
  })

  it('always has one if it has any, even when none is current', () => {
    expect(addressesOf({ addresses: ['10.0.0.1', '10.0.0.2'], current_addresses: 0 })).toEqual({
      shown: ['10.0.0.1'],
      more: 1,
    })
    expect(addressesOf({ addresses: [], current_addresses: 0 })).toEqual({ shown: [], more: 0 })
  })

  it('works on a whole asset', () => {
    expect(addressesOf(asset())).toEqual({ shown: ['192.168.1.20'], more: 0 })
  })
})

describe('the states', () => {
  it('each has a name, an icon and a meaning, so none is only a color', () => {
    for (const look of Object.values(STATUS)) {
      expect(look.label).not.toBe('')
      expect(look.description).not.toBe('')
      expect(look.icon).toBeDefined()
    }
  })
})
