import { askedAs, didDo, incidentsOf, labelOf, nothingToDo, wouldDo } from '@/bulk'
import { bulkResult } from '@/test/incidents'

describe('saying what a change to many does', () => {
  it('counts incidents', () => {
    expect([incidentsOf(1), incidentsOf(12), incidentsOf(1500)]).toEqual([
      '1 incident',
      '12 incidents',
      '1,500 incidents',
    ])
  })

  it('names a change by what it does', () => {
    expect(labelOf({ status: 'resolved' })).toBe('Resolve')
    expect(labelOf({ status: 'open' })).toBe('Reopen')
    expect(labelOf({ verdict: 'threat' })).toBe('Real threat')
  })

  it('asks what it is asked to do', () => {
    expect(askedAs({ status: 'resolved' }, 12)).toBe('Resolve 12 incidents?')
    expect(askedAs({ status: 'investigating' }, 1)).toBe('Start investigating 1 incident?')
    expect(askedAs({ verdict: 'not_suspicious' }, 12)).toBe('Say 12 incidents are not suspicious?')
    expect(askedAs({ verdict: 'threat' }, 1)).toBe('Say 1 incident is a real threat?')
  })

  describe('before a status is changed', () => {
    it('says how many it would change and how many already are so', () => {
      const result = bulkResult({ incidents: 12, signals: 31, changed: 9 })

      expect(wouldDo({ status: 'resolved' }, result)).toEqual([
        '12 incidents, with 31 signals.',
        '9 will be marked as resolved; 3 already are.',
      ])
    })

    it('says one that already is so in the singular', () => {
      const result = bulkResult({ incidents: 3, signals: 4, changed: 2 })

      expect(wouldDo({ status: 'dismissed' }, result)[1]).toBe(
        '2 will be marked as dismissed; 1 already is.',
      )
    })

    it('says all of them will be, when none is so already', () => {
      const result = bulkResult({ incidents: 2, signals: 1, changed: 2 })

      expect(wouldDo({ status: 'open' }, result)).toEqual([
        '2 incidents, with 1 signal.',
        'All will be reopened.',
      ])
    })

    it('says there is nothing to change when all are so already', () => {
      const all = bulkResult({ incidents: 4, changed: 0 })
      const one = bulkResult({ incidents: 1, changed: 0 })

      expect(wouldDo({ status: 'resolved' }, all)[1]).toBe(
        'Nothing to change: all already are resolved.',
      )
      expect(wouldDo({ status: 'resolved' }, one)[1]).toBe(
        'Nothing to change: it already is resolved.',
      )
      expect(nothingToDo({ status: 'resolved' }, all)).toBe(true)
      expect(nothingToDo({ status: 'resolved' }, bulkResult())).toBe(false)
    })
  })

  describe('before a verdict is given', () => {
    it('says how many verdicts it makes, which hold for more than the incidents picked', () => {
      const result = bulkResult({ incidents: 12, signals: 31, changed: 12, verdicts: 5 })

      const lines = wouldDo({ verdict: 'not_suspicious' }, result)

      expect(lines[0]).toBe('12 incidents, with 31 signals.')
      expect(lines[1]).toBe(
        '5 verdicts will be remembered as not suspicious, one for each address or alert. A verdict holds for everything about it, so incidents you did not pick can change too.',
      )
      expect(lines).toHaveLength(2)
    })

    it('says one verdict in the singular', () => {
      const result = bulkResult({ verdicts: 1 })

      expect(wouldDo({ verdict: 'threat' }, result)[1]).toMatch(/^One verdict will be remembered/)
    })

    it('says which are left out for having nothing to judge by', () => {
      const several = bulkResult({ skipped: 2, verdicts: 1 })
      const one = bulkResult({ skipped: 1, verdicts: 1 })

      expect(wouldDo({ verdict: 'threat' }, several).at(-1)).toBe(
        '2 incidents name no address and have no alert to judge by, so they are left out.',
      )
      expect(wouldDo({ verdict: 'threat' }, one).at(-1)).toBe(
        '1 incident names no address and has no alert to judge by, so it is left out.',
      )
    })

    it('says there is nothing to change when it is already said', () => {
      const result = bulkResult({ verdicts: 0, changed: 0 })

      expect(wouldDo({ verdict: 'threat' }, result)[1]).toBe(
        'Nothing to change: it is already said of all of them.',
      )
      expect(nothingToDo({ verdict: 'threat' }, result)).toBe(true)
      expect(nothingToDo({ verdict: 'threat' }, bulkResult({ verdicts: 1 }))).toBe(false)
    })
  })

  describe('afterwards', () => {
    it('says a status change, and how many already were so', () => {
      expect(didDo({ status: 'resolved' }, bulkResult({ incidents: 5, changed: 3 }))).toBe(
        'Marked 3 incidents as resolved. 2 already were.',
      )
      expect(didDo({ status: 'dismissed' }, bulkResult({ incidents: 3, changed: 2 }))).toBe(
        'Marked 2 incidents as dismissed. 1 already was.',
      )
      expect(didDo({ status: 'resolved' }, bulkResult({ incidents: 1, changed: 1 }))).toBe(
        'Marked 1 incident as resolved.',
      )
    })

    it('says a reopening', () => {
      expect(didDo({ status: 'open' }, bulkResult({ incidents: 4, changed: 4 }))).toBe(
        'Reopened 4 incidents.',
      )
    })

    it('says when it changed nothing', () => {
      expect(didDo({ status: 'resolved' }, bulkResult({ incidents: 3, changed: 0 }))).toBe(
        'Nothing changed: all already are resolved.',
      )
      expect(didDo({ status: 'resolved' }, bulkResult({ incidents: 1, changed: 0 }))).toBe(
        'Nothing changed: it already is resolved.',
      )
    })

    it('says a verdict, how many it made and what they cover', () => {
      const result = bulkResult({ incidents: 12, changed: 12, verdicts: 5 })

      expect(didDo({ verdict: 'low_priority' }, result)).toBe(
        'Remembered 5 verdicts as low priority, for 12 incidents.',
      )
      expect(didDo({ verdict: 'threat' }, bulkResult({ changed: 1, verdicts: 1 }))).toBe(
        'Remembered one verdict as real threat, for 1 incident.',
      )
    })

    it('says which were left out, and when nothing was said', () => {
      expect(
        didDo(
          { verdict: 'threat' },
          bulkResult({ incidents: 3, changed: 2, verdicts: 1, skipped: 1 }),
        ),
      ).toBe(
        'Remembered one verdict as real threat, for 2 incidents. 1 incident left out: nothing to judge by.',
      )
      expect(
        didDo({ verdict: 'threat' }, bulkResult({ incidents: 3, changed: 0, verdicts: 0 })),
      ).toBe('Nothing changed: it is already said of 3 incidents.')
    })
  })
})
