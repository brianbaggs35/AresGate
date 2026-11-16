import type { Incident } from '@/api/incidents'
import IncidentTable from '@/components/IncidentTable.vue'
import { incident } from '@/test/incidents'
import { mountWithPlugins } from '@/test/mount'

const MINUTE = 60_000

const rows = [
  incident({ id: 1, title: 'Port scan', subject: '10.0.0.1', severity: 'low', signal_count: 2 }),
  incident({
    id: 2,
    title: 'Brute force',
    subject: '10.0.0.2',
    severity: 'critical',
    status: 'investigating',
    verdict: 'threat',
    signal_count: 9,
    last_seen_at: new Date(Date.now() - 90 * MINUTE).toISOString(),
  }),
  incident({ id: 3, title: 'Probe', subject: '10.0.0.1', severity: 'high', signal_count: 5 }),
  incident({ id: 4, title: 'Alert', subject: 'rule:crowdsec:ssh-bf', severity: 'info' }),
]

async function open(
  props: { incidents?: Incident[]; grouped?: boolean; picked?: number[]; more?: number } = {},
) {
  const picked = new Set(props.picked ?? [])
  const mounted = await mountWithPlugins(IncidentTable, {
    withApp: true,
    signedIn: 'admin',
    props: {
      incidents: props.incidents ?? rows,
      grouped: props.grouped ?? false,
      has: (id: number) => picked.has(id),
      more: props.more ?? 0,
    },
  })
  const ids = () =>
    mounted.wrapper
      .findAll('[data-test="incident-card"] [data-test="incident-title"]')
      .map((title) => title.text())
  return { ...mounted, ids }
}

describe('IncidentTable', () => {
  it('is a table with a row for each incident, in the order it was given', async () => {
    const { wrapper, ids } = await open()

    expect(wrapper.find('table').exists()).toBe(true)
    expect(ids()).toEqual(['Port scan', 'Brute force', 'Probe', 'Alert'])
    expect(wrapper.find('caption').text()).toBe('4 incidents')
  })

  it('shows what each incident is, with a link to it', async () => {
    const { wrapper } = await open()
    const second = wrapper.findAll('[data-test="incident-card"]')[1]!

    expect(second.find('[data-test="incident"]').attributes('href')).toBe('/incidents/2')
    expect(second.find('[data-test="severity"]').text()).toBe('Critical')
    expect(second.find('[data-test="row-subject"]').text()).toBe('10.0.0.2')
    expect(second.find('[data-test="row-confidence"]').text()).toBe('70 of 100')
    expect(second.find('[data-test="row-signals"]').text()).toBe('9')
    expect(second.find('[data-test="verdict"]').exists()).toBe(true)
    expect(second.text()).toContain('Investigating')
    expect(wrapper.findAll('[data-test="incident-card"]')[0]!.text()).toContain('Open')
  })

  it('says a rule with no address in words', async () => {
    const { wrapper } = await open()

    expect(wrapper.findAll('[data-test="row-subject"]')[3]!.text()).toBe('A rule with no address')
  })

  describe('sorting', () => {
    it('sorts by a column on a press, reverses it on the next and goes back on the third', async () => {
      const { wrapper, ids } = await open()

      await wrapper.find('[data-test="sort-severity"]').trigger('click')
      expect(ids()).toEqual(['Brute force', 'Probe', 'Port scan', 'Alert'])
      expect(wrapper.find('[data-test="column-severity"]').attributes('aria-sort')).toBe(
        'descending',
      )
      expect(wrapper.find('caption').text()).toBe('4 incidents, in the order you chose')

      await wrapper.find('[data-test="sort-severity"]').trigger('click')
      expect(ids()).toEqual(['Alert', 'Port scan', 'Probe', 'Brute force'])
      expect(wrapper.find('[data-test="column-severity"]').attributes('aria-sort')).toBe(
        'ascending',
      )

      await wrapper.find('[data-test="sort-severity"]').trigger('click')
      expect(ids()).toEqual(['Port scan', 'Brute force', 'Probe', 'Alert'])
      expect(wrapper.find('[data-test="column-severity"]').attributes('aria-sort')).toBe('none')
    })

    it('sorts the words from A to Z first', async () => {
      const { wrapper, ids } = await open()

      await wrapper.find('[data-test="sort-title"]').trigger('click')

      expect(ids()).toEqual(['Alert', 'Brute force', 'Port scan', 'Probe'])
      expect(wrapper.find('[data-test="column-title"]').attributes('aria-sort')).toBe('ascending')
    })

    it('says the sort leaves out what is not loaded yet', async () => {
      const { wrapper } = await open({ more: 1200 })
      expect(wrapper.find('caption').text()).toBe('4 incidents')

      await wrapper.find('[data-test="sort-signals"]').trigger('click')

      expect(wrapper.find('caption').text()).toBe(
        '4 incidents, in the order you chose. Sorting covers only these: 1,200 more are not loaded yet',
      )
    })
  })

  describe('picking', () => {
    it('marks the rows that are picked, and tells which one was ticked, and with shift', async () => {
      const { wrapper } = await open({ picked: [3] })
      const boxes = wrapper.findAll('[data-test="incident-select"]')

      expect(boxes[2]!.element).toHaveProperty('checked', true)
      expect(boxes[0]!.element).toHaveProperty('checked', false)
      expect(wrapper.findAll('.incident-table__row--selected')).toHaveLength(1)
      expect(boxes[0]!.attributes('aria-label')).toBe('Select: Port scan')

      await boxes[0]!.trigger('click')
      await boxes[1]!.trigger('click', { shiftKey: true })

      expect(wrapper.findComponent(IncidentTable).emitted('select')).toEqual([
        [1, false],
        [2, true],
      ])
    })
  })

  describe('grouped by address', () => {
    it('gathers the incidents about one address under it and leaves the others alone', async () => {
      const { wrapper, ids } = await open({ grouped: true })

      expect(ids()).toEqual(['Port scan', 'Probe', 'Brute force', 'Alert'])
      const group = wrapper.find('[data-test="incident-group"]')
      expect(group.text()).toContain('10.0.0.1')
      expect(wrapper.find('[data-test="group-count"]').text()).toBe('2 incidents, worst high')
      expect(wrapper.findAll('[data-test="incident-group"]')).toHaveLength(1)
      expect(wrapper.findAll('.incident-table__row--member')).toHaveLength(2)
    })

    it('folds a group away and opens it again', async () => {
      const { wrapper, ids } = await open({ grouped: true })
      const fold = () => wrapper.find('[data-test="group-fold"]')

      expect(fold().attributes('aria-expanded')).toBe('true')

      await fold().trigger('click')
      expect(fold().attributes('aria-expanded')).toBe('false')
      expect(ids()).toEqual(['Brute force', 'Alert'])

      await fold().trigger('click')
      expect(fold().attributes('aria-expanded')).toBe('true')
      expect(ids()).toHaveLength(4)
    })

    it('ticks a whole group, or takes it off, by its own box', async () => {
      const { wrapper } = await open({ grouped: true })
      const box = wrapper.find('[data-test="group-select"]')

      expect(box.attributes('aria-label')).toBe('Select all 2 about 10.0.0.1')

      await box.setValue(true)
      await box.setValue(false)

      expect(wrapper.findComponent(IncidentTable).emitted('select-many')).toEqual([
        [[1, 3], true],
        [[1, 3], false],
      ])
    })

    it('shows a group as half ticked when only some of it is, and as ticked when all is', async () => {
      const some = await open({ grouped: true, picked: [1] })
      const box = some.wrapper.find('[data-test="group-select"]').element as HTMLInputElement
      expect([box.checked, box.indeterminate]).toEqual([false, true])

      const all = await open({ grouped: true, picked: [1, 3] })
      const whole = all.wrapper.find('[data-test="group-select"]').element as HTMLInputElement
      expect([whole.checked, whole.indeterminate]).toEqual([true, false])
    })

    it('keeps the groups together when it is sorted', async () => {
      const { wrapper, ids } = await open({ grouped: true })

      await wrapper.find('[data-test="sort-severity"]').trigger('click')

      expect(ids()).toEqual(['Brute force', 'Probe', 'Port scan', 'Alert'])
    })

    it('names a group of a rule in words', async () => {
      const { wrapper } = await open({
        grouped: true,
        incidents: [
          incident({ id: 1, subject: 'rule:crowdsec:x' }),
          incident({ id: 2, subject: 'rule:crowdsec:x' }),
        ],
      })

      expect(wrapper.find('[data-test="incident-group"]').text()).toContain(
        'A rule with no address',
      )
    })
  })
})
