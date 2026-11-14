import { ROLES } from '@/api/interfaces'
import { feedName, hero, latestSpeed, roleInfo, ROLE_INFO, totalSpeed } from '@/interfaces'
import { feed, iface, listing, speed, suggestion } from '@/test/interfaces'

describe('roles', () => {
  it('has words and a picture for each, and a side of the firewall', () => {
    expect(Object.keys(ROLE_INFO).sort()).toEqual([...ROLES].sort())
    for (const role of ROLES) {
      const info = roleInfo(role)
      expect(info.label).not.toBe('')
      expect(info.description).not.toBe('')
      expect(info.icon).toBeTruthy()
    }
    expect(roleInfo('internet').outside).toBe(true)
    expect(roleInfo('home').outside).toBe(false)
  })
})

describe('feedName', () => {
  it('names the program and the port', () => {
    expect(feedName(feed())).toBe('OPNsense igc0')
  })

  it('names the whole connection of a program that names no port', () => {
    expect(
      feedName(
        feed({
          integration_name: 'CrowdSec',
          native_name: '',
          connection_label: 'Local API',
        }),
      ),
    ).toBe('CrowdSec, all of Local API')
  })
})

describe('hero', () => {
  it('says there is nothing yet, and how to begin', () => {
    expect(hero(listing())).toMatchObject({
      tone: 'primary',
      title: 'No interfaces yet',
      detail: expect.stringMatching(/^Find interfaces to see/),
      mood: 'idle',
      level: 0,
    })
  })

  it('says how many feeds need a decision, and points at the suggestions when there are some', () => {
    const waiting = listing({
      interfaces: [iface({ feeds: [feed({ id: 1 })] })],
      unplaced: [feed({ id: 2 }), feed({ id: 3 }), feed({ id: 4 })],
      suggestions: [suggestion()],
    })

    expect(hero(waiting)).toMatchObject({
      tone: 'warning',
      title: '3 feeds need a decision',
      detail: 'Confirm the suggestions below, or place each feed yourself.',
      level: 25,
    })
  })

  it('says one feed in the singular, and tells what to do without suggestions', () => {
    const waiting = listing({ unplaced: [feed({ id: 2 })] })

    expect(hero(waiting)).toMatchObject({
      title: '1 feed needs a decision',
      detail: 'Place each feed on the part of your network it belongs to, or set it aside.',
      level: 0,
    })
  })

  it('says everything is placed once it is', () => {
    const done = listing({
      interfaces: [iface({ id: 1 }), iface({ id: 2, name: 'Home', role: 'home' })],
    })

    expect(hero(done)).toMatchObject({
      tone: 'success',
      title: '2 interfaces, every feed placed',
      level: 100,
    })
    expect(hero(listing({ interfaces: [iface()] })).title).toBe('1 interface, every feed placed')
  })
})

describe('speeds', () => {
  it('adds both directions a bucket at a time, and leaves a gap where neither was measured', () => {
    expect(totalSpeed(speed({ received: [null, 5, null], sent: [null, 2, 1] }))).toEqual([
      null,
      7,
      1,
    ])
  })

  it('treats a missing bucket of what was sent as unknown', () => {
    expect(totalSpeed(speed({ received: [4, 5], sent: [1] }))).toEqual([5, 5])
  })

  it('finds the latest bucket that was measured', () => {
    expect(latestSpeed([1, 2, null, null])).toBe(2)
    expect(latestSpeed([null, null])).toBeNull()
    expect(latestSpeed([])).toBeNull()
  })
})
