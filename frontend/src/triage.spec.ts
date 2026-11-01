import { CLASSIFICATIONS } from '@/api/incidents'
import { detail, reading } from '@/test/incidents'
import { CLASSIFICATION, needsReading, newSignals, newSince, readBy } from '@/triage'

describe('triage', () => {
  it('has a look for every kind of thing the AI can make of an incident', () => {
    expect(Object.keys(CLASSIFICATION).sort()).toEqual([...CLASSIFICATIONS].sort())
    for (const look of Object.values(CLASSIFICATION)) {
      expect(look.label).not.toBe('')
      expect(look.meaning).not.toBe('')
    }
  })

  it('says who read it and when', () => {
    expect(readBy(reading({ read_at: new Date(Date.now() - 180_000).toISOString() }))).toBe(
      'Read by Anthropic (claude-haiku-5-5) 3 minutes ago.',
    )
  })

  describe('what came in since', () => {
    it('counts the signals the reading has not seen', () => {
      expect(newSince(detail({ signal_count: 10, reading: reading({ signals_read: 4 }) }))).toBe(6)
    })

    it('counts none for an incident that was not read, or that lost signals', () => {
      expect(newSince(detail({ signal_count: 10 }))).toBe(0)
      expect(newSince(detail({ signal_count: 2, reading: reading({ signals_read: 4 }) }))).toBe(0)
    })

    it('says it in words', () => {
      expect(newSignals(1)).toBe('1 new signal has come in since.')
      expect(newSignals(5)).toBe('5 new signals have come in since.')
    })
  })

  describe('whether to read it', () => {
    it('is wanted for one that was not read, and for one that has grown', () => {
      expect(needsReading(detail())).toBe(true)
      expect(needsReading(detail({ signal_count: 9, reading: reading({ signals_read: 3 }) }))).toBe(
        true,
      )
    })

    it('is not wanted for one that was read in full', () => {
      expect(needsReading(detail({ signal_count: 3, reading: reading({ signals_read: 3 }) }))).toBe(
        false,
      )
    })
  })
})
