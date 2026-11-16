import type { VueWrapper } from '@vue/test-utils'
import * as denialsApi from '@/api/aiDenials'
import * as incidentsApi from '@/api/incidents'
import { ApiError } from '@/api/client'
import type { ChatAction } from '@/api/aiChat'
import ChatActions from '@/components/ChatActions.vue'
import { flushPromises, mountWithPlugins } from '@/test/mount'

const act = (over: Partial<ChatAction> = {}): ChatAction => ({
  kind: 'open',
  target_kind: 'incident',
  target_key: '3',
  value: null,
  note: null,
  label: 'Open incident 3',
  also: [],
  address: null,
  denied: false,
  ...over,
})

const undo = { statuses: { open: [3] }, rules: [] } as incidentsApi.BulkUndo
const result = (u: incidentsApi.BulkUndo | null) =>
  ({ undo: u }) as unknown as incidentsApi.BulkResult

async function show(actions: ChatAction[]) {
  const mounted = await mountWithPlugins(ChatActions, {
    props: { actions },
    signedIn: 'admin',
    withApp: true,
  })
  const push = vi.spyOn(mounted.router, 'push').mockResolvedValue(undefined)
  return { ...mounted, push }
}

describe('ChatActions', () => {
  it.each([
    [act(), { name: 'incident', params: { id: '3' } }],
    [
      act({ target_kind: 'device', target_key: '7' }),
      { name: 'asset', params: { key: 'device-7' } },
    ],
    [
      act({ target_kind: 'integration', target_key: 'wazuh' }),
      { name: 'integration', params: { key: 'wazuh' } },
    ],
    [
      act({ target_kind: 'logs', target_key: '', value: 'ssh' }),
      { name: 'logs', query: { q: 'ssh' } },
    ],
    [act({ target_kind: 'logs', target_key: '' }), { name: 'logs', query: { q: '' } }],
  ])('opens the page it names', async (action, to) => {
    const { wrapper, push } = await show([action])
    await wrapper.find('[data-test="action"]').trigger('click')
    await flushPromises()
    expect(push).toHaveBeenCalledWith(to)
    expect(wrapper.findComponent(ChatActions).emitted('opened')).toHaveLength(1)
  })

  it('goes nowhere for a page it does not know, but says it was pressed', async () => {
    const { wrapper, push } = await show([act({ target_kind: 'nowhere' })])
    await wrapper.find('[data-test="action"]').trigger('click')
    expect(push).not.toHaveBeenCalled()
    expect(wrapper.findComponent(ChatActions).emitted('opened')).toHaveLength(1)
  })

  describe('a proposal to change incidents', () => {
    const status = (over: Partial<ChatAction> = {}) =>
      act({ kind: 'status', value: 'resolved', label: 'Mark Incident 3 as resolved', ...over })
    const click = async (wrapper: Pick<VueWrapper, 'find'>, name: string) => {
      await wrapper.find(`[data-test="${name}"]`).trigger('click')
      await flushPromises()
    }

    it('waits for the owner, saying what it would do', async () => {
      const change = vi.spyOn(incidentsApi, 'changeIncidents')
      const { wrapper } = await show([status()])

      expect(wrapper.find('[data-test="proposal-label"]').text()).toBe(
        'Mark Incident 3 as resolved',
      )
      expect(wrapper.find('[data-test="proposal-effect"]').text()).toBe(
        'Changes this incident only.',
      )
      expect(wrapper.find('[data-test="proposal-approve"]').exists()).toBe(true)
      expect(wrapper.find('[data-test="proposal-deny"]').exists()).toBe(true)
      expect(change).not.toHaveBeenCalled()
    })

    it('changes the status when approved, and can take it back', async () => {
      const change = vi.spyOn(incidentsApi, 'changeIncidents').mockResolvedValue({
        ...result(undo),
        changed: 1,
      })
      const back = vi
        .spyOn(incidentsApi, 'undoChange')
        .mockResolvedValue({ incidents: 1, verdicts: 0 })
      const { wrapper } = await show([status()])

      await click(wrapper, 'proposal-approve')

      expect(change).toHaveBeenCalledWith({ ids: [3] }, { status: 'resolved' }, 'a-security-token')
      expect(wrapper.find('[data-test="action-done"]').text()).toContain(
        'Approved. 1 incident changed.',
      )
      expect(wrapper.find('[data-test="proposal-approve"]').exists()).toBe(false)

      await click(wrapper, 'action-undo')
      expect(back).toHaveBeenCalledWith(undo, 'a-security-token')
      expect(wrapper.find('[data-test="action-undone"]').exists()).toBe(true)
    })

    it('says so when what it was asked to change already is so', async () => {
      vi.spyOn(incidentsApi, 'changeIncidents').mockResolvedValue({
        ...result(null),
        changed: 0,
      })
      const { wrapper } = await show([status()])

      await click(wrapper, 'proposal-approve')

      expect(wrapper.find('[data-test="action-done"]').text()).toContain(
        'Nothing to change: they already are so.',
      )
      expect(wrapper.find('[data-test="action-undo"]').exists()).toBe(false)
    })

    it('changes nothing when denied, and remembers it', async () => {
      const change = vi.spyOn(incidentsApi, 'changeIncidents')
      const remember = vi.spyOn(denialsApi, 'denyProposal').mockResolvedValue({ recorded: 2 })
      const { wrapper } = await show([status({ also: ['4'] })])

      await click(wrapper, 'proposal-deny')

      expect(change).not.toHaveBeenCalled()
      expect(remember).toHaveBeenCalledWith(
        { kind: 'status', value: 'resolved', incident_ids: [3, 4] },
        expect.any(String),
      )
      expect(wrapper.find('[data-test="action-denied"]').text()).toBe(
        "Denied. Nothing was changed, and it won't be suggested again unless the incident changes.",
      )
      expect(wrapper.find('[data-test="proposal-approve"]').exists()).toBe(false)
    })

    it('remembers the denial of a verdict by its kind', async () => {
      const remember = vi.spyOn(denialsApi, 'denyProposal').mockResolvedValue({ recorded: 1 })
      const { wrapper } = await show([status({ kind: 'verdict', value: 'threat' })])

      await click(wrapper, 'proposal-deny')

      expect(remember).toHaveBeenCalledWith(
        { kind: 'verdict', value: 'threat', incident_ids: [3] },
        expect.any(String),
      )
    })

    it('says so when the denial could not be remembered, and can be tried again', async () => {
      vi.spyOn(denialsApi, 'denyProposal')
        .mockRejectedValueOnce(new ApiError(500, 'Broke.', 'server_error'))
        .mockResolvedValue({ recorded: 1 })
      const { wrapper } = await show([status()])

      await click(wrapper, 'proposal-deny')

      expect(wrapper.find('[data-test="action-failed"]').text()).toBe('Broke.')
      expect(wrapper.find('[data-test="proposal-deny"]').exists()).toBe(true)

      await click(wrapper, 'proposal-deny')

      expect(wrapper.find('[data-test="action-denied"]').exists()).toBe(true)
    })

    it('shows a proposal that was denied before as denied, without the buttons', async () => {
      const { wrapper } = await show([status({ denied: true })])

      expect(wrapper.find('[data-test="action-denied"]').exists()).toBe(true)
      expect(wrapper.find('[data-test="proposal-approve"]').exists()).toBe(false)
      expect(wrapper.find('[data-test="proposal-deny"]').exists()).toBe(false)
    })

    it('gives a verdict with its note, and says what was remembered', async () => {
      const change = vi.spyOn(incidentsApi, 'changeIncidents').mockResolvedValue({
        ...result(null),
        verdicts: 1,
        incidents: 4,
      })
      const { wrapper } = await show([
        act({
          kind: 'verdict',
          value: 'not_suspicious',
          note: 'The backup job',
          label: 'Call Incident 3 not suspicious',
          address: '93.184.216.34',
        }),
      ])
      expect(wrapper.find('[data-test="proposal-why"]').text()).toBe('Why: The backup job')
      expect(wrapper.find('[data-test="proposal-effect"]').text()).toContain(
        'everything about 93.184.216.34',
      )
      expect(wrapper.find('[data-test="proposal-earlier"]').exists()).toBe(false)

      await click(wrapper, 'proposal-approve')

      expect(change).toHaveBeenCalledWith(
        { ids: [3] },
        { verdict: 'not_suspicious', note: 'The backup job' },
        'a-security-token',
      )
      expect(wrapper.find('[data-test="action-done"]').text()).toContain(
        'Approved. Remembered 1 verdict, covering 4 incidents.',
      )
      // Nothing to take back where the change says nothing of how.
      expect(wrapper.find('[data-test="action-undo"]').exists()).toBe(false)
    })

    it('gives a verdict without a note where there is none, and says verdicts for many', async () => {
      const change = vi.spyOn(incidentsApi, 'changeIncidents').mockResolvedValue({
        ...result(null),
        verdicts: 2,
        incidents: 2,
      })
      const { wrapper } = await show([
        act({ kind: 'verdict', value: 'low_priority', also: ['4'], label: 'Call 2 incidents' }),
      ])
      expect(wrapper.find('[data-test="proposal-effect"]').text()).toContain(
        'what each of them is about',
      )

      await click(wrapper, 'proposal-approve')

      expect(change).toHaveBeenCalledWith(
        { ids: [3, 4] },
        { verdict: 'low_priority' },
        'a-security-token',
      )
      expect(wrapper.find('[data-test="action-done"]').text()).toContain('2 verdicts')
    })

    it('says a verdict about a rule is for every alert like it', async () => {
      const { wrapper } = await show([act({ kind: 'verdict', value: 'low_priority' })])

      expect(wrapper.find('[data-test="proposal-effect"]').text()).toContain('every alert like it')
    })

    it('is about all the incidents it names, approved as one', async () => {
      const change = vi.spyOn(incidentsApi, 'changeIncidents').mockResolvedValue({
        ...result(undo),
        changed: 3,
      })
      const { wrapper } = await show([
        status({ also: ['5', '8'], label: 'Mark 3 incidents as resolved' }),
      ])
      expect(wrapper.find('[data-test="proposal-effect"]').text()).toBe(
        'Changes these 3 incidents.',
      )

      await click(wrapper, 'proposal-approve')

      expect(change).toHaveBeenCalledWith(
        { ids: [3, 5, 8] },
        { status: 'resolved' },
        'a-security-token',
      )
      expect(wrapper.find('[data-test="action-done"]').text()).toContain('3 incidents changed.')
    })

    it('offers the earlier incidents about the same address only for a status of one incident', async () => {
      const one = await show([status({ address: '93.184.216.34' })])
      const many = await show([status({ address: null })])
      const verdict = await show([act({ kind: 'verdict', value: 'threat', address: '1.2.3.4' })])

      expect(one.wrapper.find('[data-test="proposal-earlier"]').exists()).toBe(true)
      expect(many.wrapper.find('[data-test="proposal-earlier"]').exists()).toBe(false)
      expect(verdict.wrapper.find('[data-test="proposal-earlier"]').exists()).toBe(false)
    })

    it('says what the earlier incidents come to before it is approved, then changes them too', async () => {
      const change = vi
        .spyOn(incidentsApi, 'changeIncidents')
        .mockResolvedValueOnce({ ...result(null), incidents: 12, changed: 9 })
        .mockResolvedValueOnce({ ...result(undo), incidents: 12, changed: 9 })
      const { wrapper } = await show([status({ address: '93.184.216.34' })])

      await wrapper.find('[data-test="proposal-earlier"] input').setValue(true)
      await flushPromises()

      const asked = {
        matching: {
          statuses: ['open', 'investigating', 'resolved', 'dismissed'],
          address: '93.184.216.34',
        },
      }
      expect(change).toHaveBeenNthCalledWith(
        1,
        asked,
        { status: 'resolved' },
        'a-security-token',
        true,
      )
      expect(wrapper.find('[data-test="proposal-look"]').text()).toBe(
        '12 incidents in all, and 9 would change.',
      )
      expect(wrapper.find('[data-test="proposal-effect"]').text()).toBe(
        'Changes every incident about 93.184.216.34, earlier ones too.',
      )

      await click(wrapper, 'proposal-approve')

      expect(change).toHaveBeenNthCalledWith(2, asked, { status: 'resolved' }, 'a-security-token')
      expect(wrapper.find('[data-test="action-done"]').text()).toContain('9 incidents changed.')
    })

    it('says none would change, and forgets the count when the box is cleared', async () => {
      vi.spyOn(incidentsApi, 'changeIncidents').mockResolvedValue({
        ...result(null),
        incidents: 1,
        changed: 0,
      })
      const { wrapper } = await show([status({ address: '93.184.216.34' })])
      const box = () => wrapper.find('[data-test="proposal-earlier"] input')

      await box().setValue(true)
      await flushPromises()
      expect(wrapper.find('[data-test="proposal-look"]').text()).toBe(
        '1 incident in all, and none would change.',
      )

      await box().setValue(false)
      await flushPromises()
      expect(wrapper.find('[data-test="proposal-look"]').exists()).toBe(false)
      expect(wrapper.find('[data-test="proposal-effect"]').text()).toBe(
        'Changes this incident only.',
      )
    })

    it('unticks the box and says why when the count cannot be had', async () => {
      vi.spyOn(incidentsApi, 'changeIncidents').mockRejectedValue(
        new ApiError(0, "Can't reach AresGate.", 'offline'),
      )
      const { wrapper } = await show([status({ address: '93.184.216.34' })])

      await wrapper.find('[data-test="proposal-earlier"] input').setValue(true)
      await flushPromises()

      expect(wrapper.find('[data-test="action-failed"]').text()).toBe("Can't reach AresGate.")
      expect(
        (wrapper.find('[data-test="proposal-earlier"] input').element as HTMLInputElement).checked,
      ).toBe(false)
    })

    it('says why a change failed, offers it again, and says why taking it back failed', async () => {
      vi.spyOn(incidentsApi, 'changeIncidents').mockRejectedValueOnce(
        new ApiError(0, "Can't reach AresGate.", 'offline'),
      )
      const { wrapper } = await show([status()])
      await click(wrapper, 'proposal-approve')
      expect(wrapper.find('[data-test="action-failed"]').text()).toBe("Can't reach AresGate.")
      expect(wrapper.find('[data-test="proposal-approve"]').exists()).toBe(true)

      vi.spyOn(incidentsApi, 'changeIncidents').mockResolvedValue(result(undo))
      vi.spyOn(incidentsApi, 'undoChange').mockRejectedValue(
        new ApiError(409, 'It changed since.', 'conflict'),
      )
      await click(wrapper, 'proposal-approve')
      await click(wrapper, 'action-undo')
      expect(wrapper.find('[data-test="action-failed"]').text()).toBe('It changed since.')
    })
  })
})
