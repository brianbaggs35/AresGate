import {
  deviceQuery,
  portLabel,
  portQuery,
  reachLabel,
  shareOfSides,
  SIDES,
  sidesSummary,
} from '@/blocked'

const none = { inbound: 0, outbound: 0, inside: 0 }

describe('SIDES', () => {
  it('names the three ways a connection can go, the internet first', () => {
    expect(SIDES.map((side) => side.key)).toEqual(['inbound', 'outbound', 'inside'])
  })
})

describe('shareOfSides', () => {
  it('is the part of the sorted blocks that went one way', () => {
    expect(shareOfSides({ inbound: 3, outbound: 1, inside: 0 }, 'inbound')).toBe(0.75)
    expect(shareOfSides({ inbound: 3, outbound: 1, inside: 0 }, 'inside')).toBe(0)
  })

  it('is nothing when nothing was blocked', () => {
    expect(shareOfSides(none, 'inbound')).toBe(0)
  })
})

describe('sidesSummary', () => {
  it('says nothing was refused', () => {
    expect(sidesSummary(none)).toBe('The firewall refused nothing.')
  })

  it('calls blocks that all came from the internet the firewall doing its job', () => {
    expect(sidesSummary({ ...none, inbound: 1_200 })).toBe(
      'All 1,200 came from the internet: the firewall doing its job.',
    )
  })

  it('says none of your devices were turned away when only networks of yours were', () => {
    expect(sidesSummary({ inbound: 10, outbound: 0, inside: 2 })).toBe(
      '10 came from the internet, the firewall doing its job. None of your devices were turned away.',
    )
  })

  it('points at your own devices when any were refused', () => {
    expect(sidesSummary({ inbound: 10, outbound: 1, inside: 0 })).toBe(
      '10 came from the internet, the firewall doing its job. 1 connection from your own devices were refused: worth a look if one device keeps trying.',
    )
    expect(sidesSummary({ inbound: 10, outbound: 4, inside: 0 })).toContain(
      '4 connections from your own devices were refused',
    )
  })
})

describe('the searches', () => {
  it('find the blocks of a device or a port in the window', () => {
    expect(deviceQuery('192.168.1.20', '24h')).toBe(
      'kind:firewall severity>=low from:192.168.1.20 since:24h',
    )
    expect(portQuery(22, '7d')).toBe('kind:firewall severity>=low port:22 since:7d')
  })
})

describe('portLabel and reachLabel', () => {
  it('name a port with what it is for, where that is known', () => {
    expect(portLabel({ port: 22, service: 'SSH' })).toBe('22 · SSH')
    expect(portLabel({ port: 8080, service: null })).toBe('8080')
  })

  it('count the addresses a device tried to reach', () => {
    expect(reachLabel(0)).toBe('to no address the firewall named')
    expect(reachLabel(1)).toBe('to 1 address')
    expect(reachLabel(3)).toBe('to 3 addresses')
  })
})
