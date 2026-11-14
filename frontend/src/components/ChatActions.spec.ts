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

  it('changes the status when pressed, and can take it back', async () => {
    const change = vi.spyOn(incidentsApi, 'changeIncidents').mockResolvedValue(result(undo))
    const back = vi
      .spyOn(incidentsApi, 'undoChange')
      .mockResolvedValue({ incidents: 1, verdicts: 0 })
    const { wrapper } = await show([act({ kind: 'status', value: 'resolved', label: 'Resolve' })])

    await wrapper.find('[data-test="action"]').trigger('click')
    await flushPromises()
    expect(change).toHaveBeenCalledWith({ ids: [3] }, { status: 'resolved' }, 'a-security-token')
    expect(wrapper.find('[data-test="action-done"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="action"]').attributes('disabled')).toBeDefined()

    await wrapper.find('[data-test="action-undo"]').trigger('click')
    await flushPromises()
    expect(back).toHaveBeenCalledWith(undo, 'a-security-token')
    expect(wrapper.find('[data-test="action-undone"]').exists()).toBe(true)
  })

  it('gives a verdict with its note', async () => {
    const change = vi.spyOn(incidentsApi, 'changeIncidents').mockResolvedValue(result(null))
    const { wrapper } = await show([
      act({ kind: 'verdict', value: 'not_suspicious', note: 'The backup job', label: 'Mute' }),
    ])
    await wrapper.find('[data-test="action"]').trigger('click')
    await flushPromises()
    expect(change).toHaveBeenCalledWith(
      { ids: [3] },
      { verdict: 'not_suspicious', note: 'The backup job' },
      'a-security-token',
    )
    // Nothing to take back where the change says nothing of how.
    expect(wrapper.find('[data-test="action-done"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="action-undo"]').exists()).toBe(false)
  })

  it('gives a verdict without a note where there is none', async () => {
    const change = vi.spyOn(incidentsApi, 'changeIncidents').mockResolvedValue(result(null))
    const { wrapper } = await show([act({ kind: 'verdict', value: 'false_positive' })])
    await wrapper.find('[data-test="action"]').trigger('click')
    await flushPromises()
    expect(change).toHaveBeenCalledWith(
      { ids: [3] },
      { verdict: 'false_positive' },
      'a-security-token',
    )
  })

  it('says why a change failed, and why taking it back did', async () => {
    vi.spyOn(incidentsApi, 'changeIncidents').mockRejectedValueOnce(
      new ApiError(0, "Can't reach AresGate.", 'offline'),
    )
    const { wrapper } = await show([act({ kind: 'status', value: 'resolved' })])
    await wrapper.find('[data-test="action"]').trigger('click')
    await flushPromises()
    expect(wrapper.find('[data-test="action-failed"]').text()).toBe("Can't reach AresGate.")

    vi.spyOn(incidentsApi, 'changeIncidents').mockResolvedValue(result(undo))
    vi.spyOn(incidentsApi, 'undoChange').mockRejectedValue(
      new ApiError(409, 'It changed since.', 'conflict'),
    )
    await wrapper.find('[data-test="action"]').trigger('click')
    await flushPromises()
    await wrapper.find('[data-test="action-undo"]').trigger('click')
    await flushPromises()
    expect(wrapper.find('[data-test="action-failed"]').text()).toBe('It changed since.')
  })
})
