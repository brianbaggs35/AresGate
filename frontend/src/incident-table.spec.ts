import { COLUMNS, groupedByAddress, nextSort, sortedBy } from '@/incident-table'
import { incident } from '@/test/incidents'

const MINUTE = 60_000

describe('sorting the incident table', () => {
  it('starts each column the way that is most useful, then reverses it, then lets go', () => {
    expect(nextSort(null, 'severity')).toEqual({ key: 'severity', direction: 'desc' })
    expect(nextSort({ key: 'severity', direction: 'desc' }, 'severity')).toEqual({
      key: 'severity',
      direction: 'asc',
    })
    expect(nextSort({ key: 'severity', direction: 'asc' }, 'severity')).toBeNull()

    expect(nextSort(null, 'title')).toEqual({ key: 'title', direction: 'asc' })
    expect(nextSort({ key: 'title', direction: 'asc' }, 'title')).toEqual({
      key: 'title',
      direction: 'desc',
    })
    expect(nextSort({ key: 'title', direction: 'desc' }, 'title')).toBeNull()
  })

  it('starts again with another column', () => {
    expect(nextSort({ key: 'severity', direction: 'asc' }, 'seen')).toEqual({
      key: 'seen',
      direction: 'desc',
    })
  })

  it('has a column for each way to sort', () => {
    expect(COLUMNS.map(({ key }) => key)).toEqual([
      'severity',
      'title',
      'subject',
      'confidence',
      'status',
      'seen',
      'signals',
    ])
  })

  const rows = [
    incident({
      id: 1,
      title: 'B',
      subject: '10.0.0.2',
      severity: 'low',
      confidence: 20,
      status: 'open',
      signal_count: 5,
      last_seen_at: new Date(1_000 * MINUTE).toISOString(),
    }),
    incident({
      id: 2,
      title: 'A',
      subject: '10.0.0.9',
      severity: 'critical',
      confidence: 90,
      status: 'investigating',
      signal_count: 1,
      last_seen_at: new Date(3_000 * MINUTE).toISOString(),
    }),
    incident({
      id: 3,
      title: 'C',
      subject: '10.0.0.1',
      severity: 'low',
      confidence: 50,
      status: 'resolved',
      signal_count: 9,
      last_seen_at: new Date(2_000 * MINUTE).toISOString(),
    }),
  ]
  const order = (key: Parameters<typeof nextSort>[1], direction: 'asc' | 'desc') =>
    sortedBy(rows, { key, direction }).map(({ id }) => id)

  it('keeps the order it was sent when there is no sort, without changing the list', () => {
    const sorted = sortedBy(rows, null)

    expect(sorted.map(({ id }) => id)).toEqual([1, 2, 3])
    expect(sorted).not.toBe(rows)
  })

  it('sorts by every column, either way', () => {
    expect(order('severity', 'desc')).toEqual([2, 1, 3])
    expect(order('title', 'asc')).toEqual([2, 1, 3])
    expect(order('title', 'desc')).toEqual([3, 1, 2])
    expect(order('subject', 'asc')).toEqual([3, 1, 2])
    expect(order('confidence', 'desc')).toEqual([2, 3, 1])
    expect(order('status', 'asc')).toEqual([2, 1, 3])
    expect(order('seen', 'desc')).toEqual([2, 3, 1])
    expect(order('signals', 'desc')).toEqual([3, 1, 2])
    expect(order('signals', 'asc')).toEqual([2, 1, 3])
  })

  it('keeps ties as they came, whichever way it is sorted', () => {
    expect(order('severity', 'asc')).toEqual([1, 3, 2])
    expect(order('severity', 'desc')).toEqual([2, 1, 3])
  })
})

describe('gathering incidents by address', () => {
  it('puts the incidents about one address under it, where the first of them was', () => {
    const sections = groupedByAddress([
      incident({ id: 1, subject: 'a', severity: 'low' }),
      incident({ id: 2, subject: 'b' }),
      incident({ id: 3, subject: 'a', severity: 'critical' }),
      incident({ id: 4, subject: 'a', severity: 'medium' }),
    ])

    expect(sections.map((section) => section.kind)).toEqual(['group', 'alone'])
    const [group, alone] = sections
    expect(group).toMatchObject({ subject: 'a', worst: 'critical' })
    expect(group?.kind === 'group' && group.members.map(({ id }) => id)).toEqual([1, 3, 4])
    expect(alone?.kind === 'alone' && alone.incident.id).toBe(2)
  })

  it('leaves an address with one incident alone, and has nothing for no incidents', () => {
    expect(groupedByAddress([incident({ id: 1, subject: 'a' })])).toEqual([
      { kind: 'alone', incident: expect.objectContaining({ id: 1 }) },
    ])
    expect(groupedByAddress([])).toEqual([])
  })

  it('takes the worst severity of the group, even when that is the lowest there is', () => {
    const [group] = groupedByAddress([
      incident({ id: 1, subject: 'a', severity: 'info' }),
      incident({ id: 2, subject: 'a', severity: 'info' }),
    ])

    expect(group).toMatchObject({ kind: 'group', worst: 'info' })
  })
})
