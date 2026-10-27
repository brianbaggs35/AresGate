import { ban, incident, response } from '@/test/incidents'
import {
  banEnds,
  banReason,
  banStatus,
  headline,
  left,
  stepsOf,
  times,
  turnedAway,
} from '@/response'

const NOW = Date.parse('2026-10-27T12:00:00Z')
const at = (minutes: number) => new Date(NOW + minutes * 60_000).toISOString()

function judged(changes: Parameters<typeof response>[0], neighbours = 0) {
  return incident({
    first_seen_at: at(-60),
    last_seen_at: at(-50),
    neighbours,
    response: response(changes),
  })
}

describe('times', () => {
  it('says once, and then how many times', () => {
    expect(times(1)).toBe('once')
    expect(times(14)).toBe('14 times')
    expect(times(1234)).toBe('1,234 times')
  })
})

describe('left', () => {
  it('says how long, or that it is soon', () => {
    expect(left(at(192), NOW)).toBe('3h 12m')
    expect(left(at(0.5), NOW)).toBe('under a minute')
    expect(left(at(-5), NOW)).toBe('under a minute')
  })
})

describe('headline', () => {
  it('says that a rule has no address to act on', () => {
    expect(headline(judged({ state: 'no_address' }), NOW)).toBe(
      'This incident names no address, so there is nothing to ban or block.',
    )
  })

  it('says that nothing has been seen done', () => {
    expect(headline(judged({ state: 'none' }), NOW)).toBe(
      'Nothing has been done about it yet: AresGate has seen no ban and no block.',
    )
  })

  it('says how long a ban has left', () => {
    const bans = [ban({ ends_at: at(192) })]

    expect(headline(judged({ state: 'banned', bans }), NOW)).toBe(
      'CrowdSec banned 93.184.216.34. The ban has 3h 12m left.',
    )
  })

  it('says when how long a ban lasts is not known', () => {
    const bans = [ban({ ends_at: null })]

    expect(headline(judged({ state: 'banned', bans }), NOW)).toBe(
      "CrowdSec banned 93.184.216.34. How long the ban lasts isn't known.",
    )
  })

  it('counts the addresses that were banned when there were several', () => {
    const bans = [
      ban({ ends_at: at(60) }),
      ban({ address: '93.184.216.99', ends_at: at(120) }),
      ban({ address: '93.184.216.99', ends_at: at(30) }),
    ]

    expect(headline(judged({ state: 'banned', bans }), NOW)).toBe(
      'CrowdSec banned 2 addresses. The ban has 2h 0m left.',
    )
  })

  it('says that a ban whose details are gone was one', () => {
    expect(headline(judged({ state: 'banned' }), NOW)).toBe(
      'CrowdSec banned it, but the details of the ban are no longer kept.',
    )
  })

  it('says how many of the addresses were banned', () => {
    const bans = [ban({ ends_at: at(60) })]

    expect(headline(judged({ state: 'partly', bans }, 3), NOW)).toBe(
      'CrowdSec banned 1 of the 4 addresses it came from.',
    )
  })

  it('says when a ban ended', () => {
    const bans = [ban({ ends_at: at(-120), in_force: false })]

    expect(headline(judged({ state: 'ban_ended', bans }), NOW)).toBe(
      'CrowdSec banned it, and the ban ended 2 hours ago.',
    )
  })

  it('does not guess when a ban that ended did', () => {
    expect(headline(judged({ state: 'ban_ended' }), NOW)).toBe(
      'CrowdSec banned it, and the ban has ended.',
    )
  })

  it('says what turned it away when nothing banned it', () => {
    expect(headline(judged({ state: 'blocked', blocked: 14 }), NOW)).toBe(
      'The firewall turned it away 14 times. It was not banned.',
    )
    expect(headline(judged({ state: 'blocked', dropped: 1 }), NOW)).toBe(
      'Suricata stopped 1 alert. It was not banned.',
    )
    expect(headline(judged({ state: 'blocked', blocked: 1, dropped: 3 }), NOW)).toBe(
      'The firewall turned it away once and Suricata stopped 3 alerts. It was not banned.',
    )
  })
})

describe('what a ban says', () => {
  it('says what it is', () => {
    expect(banStatus(ban())).toBe('In force')
    expect(banStatus(ban({ in_force: false }))).toBe('Ended')
    expect(banStatus(ban({ simulated: true, in_force: false }))).toBe('Simulated')
    expect(banStatus(ban({ kind: 'captcha', in_force: false }))).toBe('Captcha')
  })

  it('says when it runs out', () => {
    expect(banEnds(ban({ ends_at: at(192) }), NOW)).toContain('in 3h 12m.')
    expect(banEnds(ban({ ends_at: at(-30), in_force: false }), NOW)).toMatch(/^Ran out /)
    expect(banEnds(ban({ ends_at: null }), NOW)).toBe("How long it lasts isn't known.")
    expect(banEnds(ban({ simulated: true, in_force: false }), NOW)).toBe(
      'CrowdSec only pretended: it was in its simulation mode.',
    )
    expect(banEnds(ban({ kind: 'captcha', in_force: false }), NOW)).toBe(
      'Not a ban: CrowdSec chose captcha.',
    )
  })

  it('says what made it and where it came from, as far as that is known', () => {
    expect(banReason(ban())).toBe("crowdsecurity/ssh-bf · CrowdSec's own detection")
    expect(banReason(ban({ origin: null }))).toBe('crowdsecurity/ssh-bf')
    expect(banReason(ban({ scenario: null, origin: null }))).toBe('')
  })
})

describe('stepsOf', () => {
  it('has none for an incident about a rule', () => {
    expect(stepsOf(judged({ state: 'no_address' }), NOW)).toEqual([])
  })

  it('has only the first sighting when nothing was done', () => {
    expect(stepsOf(judged({ state: 'none' }), NOW).map((step) => step.title)).toEqual([
      'First seen',
    ])
  })

  it('puts the ban, the blocks that went on and the end of the ban in order', () => {
    const steps = stepsOf(
      judged({
        state: 'banned',
        bans: [ban({ seen_at: at(-50), ends_at: at(190) })],
        blocked: 6,
        blocked_since_ban: 4,
        last_blocked_at: at(-20),
      }),
      NOW,
    )

    expect(steps.map((step) => [step.title, step.detail])).toEqual([
      ['First seen', null],
      ['Banned', null],
      ['Still trying', 'The firewall turned it away 4 times after the ban. This was the last.'],
      ['Ban ends', null],
    ])
  })

  it('says a ban ended once it has, and names the address when there were several', () => {
    const steps = stepsOf(
      judged({
        state: 'ban_ended',
        bans: [
          ban({ seen_at: at(-50), ends_at: at(-10), in_force: false }),
          ban({ address: '93.184.216.99', seen_at: at(-45), ends_at: null }),
        ],
      }),
      NOW,
    )

    expect(steps.map((step) => [step.title, step.detail])).toEqual([
      ['First seen', null],
      ['Banned', '93.184.216.34'],
      ['Banned', '93.184.216.99'],
      ['Ban ended', '93.184.216.34'],
    ])
  })

  it('says it was turned away when there was no ban to go on after', () => {
    const steps = stepsOf(judged({ state: 'blocked', blocked: 2, last_blocked_at: at(-30) }), NOW)

    expect(steps.map((step) => [step.title, step.detail])).toEqual([
      ['First seen', null],
      ['Turned away', 'The firewall turned it away 2 times. This was the last.'],
    ])
  })

  it('leaves out a ban that was not one', () => {
    const steps = stepsOf(
      judged({
        state: 'none',
        bans: [
          ban({ simulated: true, in_force: false }),
          ban({ kind: 'captcha', in_force: false }),
        ],
      }),
      NOW,
    )

    expect(steps).toHaveLength(1)
  })
})

describe('turnedAway', () => {
  it('has nothing to say when nothing turned it away', () => {
    expect(turnedAway(response(), NOW)).toEqual([])
  })

  it('says how often the firewall did, and since the ban, and when last', () => {
    const [firewall] = turnedAway(
      response({ blocked: 14, blocked_since_ban: 9, last_blocked_at: at(-2) }),
      NOW,
    )

    expect(firewall).toEqual({
      id: 'firewall',
      label: 'Firewall',
      value: 'Turned it away 14 times. 9 of them after the ban. The last was 2 minutes ago.',
    })
  })

  it('says it without the ban or the time when it has neither', () => {
    expect(turnedAway(response({ blocked: 1 }), NOW)[0]?.value).toBe('Turned it away once.')
  })

  it('says how many alerts Suricata stopped', () => {
    expect(turnedAway(response({ dropped: 3 }), NOW)).toEqual([
      { id: 'suricata', label: 'Suricata', value: 'Stopped 3 alerts.' },
    ])
  })
})
