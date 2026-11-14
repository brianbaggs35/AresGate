import { answer, coverage, headline, RANGES } from '@/incidentResponse'
import { item, overview } from '@/test/incidentResponse'

const NOW = Date.parse('2026-11-14T12:00:00Z')

describe('incident response', () => {
  it('offers the ranges from the shortest', () => {
    expect(RANGES.map(({ key }) => key)).toEqual(['24h', '7d', '30d'])
  })

  describe('the headline', () => {
    it('says how many need a response, in the singular for one', () => {
      expect(headline(overview({ needs_response: [item()] }), 'the last 7 days')).toMatchObject({
        tone: 'urgent',
        title: '1 incident still needs a response',
      })
      expect(
        headline(overview({ needs_response: [item(), item({ id: 2 })] }), 'the last 7 days').title,
      ).toBe('2 incidents still need a response')
    })

    it('says so when everything has been answered', () => {
      const found = headline(overview({ banned: [item({ state: 'banned' })] }), 'the last 7 days')

      expect(found).toMatchObject({
        tone: 'calm',
        title: 'Everything that matters has been answered',
      })
      expect(found.detail).toBe(
        '1 incident went on in the last 7 days, and none of them is waiting for a response.',
      )
    })

    it('says so when nothing went on', () => {
      expect(headline(overview(), 'the last 24 hours')).toMatchObject({
        tone: 'idle',
        title: 'No serious incidents in the last 24 hours',
        detail: 'Nothing of medium severity or higher went on, so there was nothing to respond to.',
      })
    })
  })

  describe('what it cannot see', () => {
    it('says nothing when both programs are connected', () => {
      expect(coverage(overview())).toBeNull()
    })

    it('names a program that is missing, and what that hides', () => {
      expect(coverage(overview({}, { crowdsec_connected: false }))).toBe(
        "CrowdSec isn't connected, so AresGate can't see what CrowdSec banned. What needs a response may already have been answered.",
      )
      expect(coverage(overview({}, { opnsense_connected: false }))).toContain(
        "OPNsense isn't connected, so AresGate can't see what the firewall or Suricata turned away.",
      )
    })

    it('says both together', () => {
      expect(coverage(overview({}, { crowdsec_connected: false, opnsense_connected: false }))).toBe(
        "CrowdSec and OPNsense aren't connected, so AresGate can't see any ban or block. What needs a response may already have been answered.",
      )
    })
  })

  describe('what was done', () => {
    it.each([
      [{ state: 'no_address' }, 'It names no address, so there is nothing to ban or block.'],
      [{ state: 'none' }, 'No ban, and nothing turned it away.'],
      [{ state: 'ban_ended' }, 'CrowdSec banned it, and the ban ended.'],
      [{ state: 'partly', banned_now: 1, attackers: 3 }, 'CrowdSec banned 1 of its 3 addresses.'],
      [
        { state: 'banned', banned_now: 1, ban_ends_at: '2026-11-14T15:12:00Z' },
        'CrowdSec banned it, with 3h 12m left.',
      ],
      [
        { state: 'banned', banned_now: 3, ban_ends_at: '2026-11-14T12:30:00Z' },
        'CrowdSec banned 3 addresses, with 30m left.',
      ],
      [
        { state: 'banned', banned_now: 1, ban_ends_at: null },
        "CrowdSec banned it. How long the ban lasts isn't known.",
      ],
      [{ state: 'blocked', blocked: 14, dropped: 0 }, 'The firewall turned it away 14 times.'],
      [{ state: 'blocked', blocked: 0, dropped: 1 }, 'Suricata stopped 1 alert.'],
      [
        { state: 'blocked', blocked: 1, dropped: 3 },
        'The firewall turned it away once and Suricata stopped 3 alerts.',
      ],
    ] as const)('says %j', (changes, words) => {
      expect(answer(item(changes), NOW)).toBe(words)
    })
  })
})
