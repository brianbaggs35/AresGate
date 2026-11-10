import * as agentsApi from '@/api/agents'
import type { Overview } from '@/api/agents'
import { ApiError } from '@/api/client'
import AgentCard from '@/components/AgentCard.vue'
import AgentDialog from '@/components/AgentDialog.vue'
import { agent, overview } from '@/test/agents'
import { flushPromises, mountWithPlugins } from '@/test/mount'
import AgentsView from '@/views/AgentsView.vue'

const TOKEN = 'a-security-token'

async function open(result: Overview | Error = overview()) {
  const list = vi.spyOn(agentsApi, 'fetchAgents')
  if (result instanceof Error) list.mockRejectedValue(result)
  else list.mockResolvedValue(result)
  const start = vi.spyOn(agentsApi, 'startRun').mockResolvedValue({} as agentsApi.Run)
  const mounted = await mountWithPlugins(AgentsView, { signedIn: 'admin', withApp: true })
  await flushPromises()
  const find = (selector: string) => mounted.wrapper.find(`[data-test="${selector}"]`)
  const click = async (selector: string) => {
    await find(selector).trigger('click')
    await flushPromises()
    await flushPromises()
  }
  return { ...mounted, list, start, find, click }
}

describe('AgentsView', () => {
  it('shows placeholders while it loads', async () => {
    vi.spyOn(agentsApi, 'fetchAgents').mockReturnValue(new Promise(() => {}))
    const { wrapper } = await mountWithPlugins(AgentsView, { signedIn: 'admin', withApp: true })

    expect(wrapper.find('[data-test="agents-loading"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="agents-make"]').attributes('disabled')).toBeDefined()
  })

  it('says why it could not load, and tries again', async () => {
    const { find, click, list } = await open(new ApiError(0, "Can't reach AresGate.", 'offline'))

    expect(find('agents-error').text()).toContain("Can't reach AresGate.")
    expect(find('agents-list').exists()).toBe(false)
    list.mockResolvedValue(overview())

    await click('agents-retry')

    expect(find('agents-error').exists()).toBe(false)
    expect(find('agents-list').exists()).toBe(true)
  })

  it('shows each agent as a card', async () => {
    const { wrapper } = await open(
      overview({ agents: [agent({ id: 1, name: 'First' }), agent({ id: 2, name: 'Second' })] }),
    )

    const cards = wrapper.findAllComponents(AgentCard)
    expect(cards.map((card) => card.find('[data-test="agent-open"]').text())).toEqual([
      'First',
      'Second',
    ])
  })

  it('offers the kinds there are when there are no agents, and makes one from the one picked', async () => {
    const { wrapper, find } = await open(overview({ agents: [] }))

    expect(find('agents-empty').exists()).toBe(true)
    expect(wrapper.findAll('[data-test="agents-kind"]')).toHaveLength(2)

    await wrapper.findAll('[data-test="agents-kind-make"]')[1]!.trigger('click')
    await flushPromises()

    expect(wrapper.findComponent(AgentDialog).props('starter')).toBe('exposure_scanner')
    expect(
      document.body.querySelector<HTMLInputElement>(
        '.v-overlay--active input[value="exposure_scanner"]',
      )!.checked,
    ).toBe(true)
    expect(find('agents-list').exists()).toBe(false)
  })

  it('makes an agent from the button at the top, and shows it', async () => {
    const { wrapper, find, click, list } = await open()
    const made = vi.spyOn(agentsApi, 'createAgent').mockResolvedValue(agent({ id: 9 }))
    list.mockResolvedValue(overview({ agents: [agent(), agent({ id: 9, name: 'Made' })] }))

    await click('agents-make')
    expect(wrapper.findComponent(AgentDialog).props('starter')).toBeNull()
    document.body
      .querySelector<HTMLElement>('.v-overlay--active [data-test="dialog-save"]')!
      .click()
    await flushPromises()
    await flushPromises()

    expect(made).toHaveBeenCalledOnce()
    expect(find('agents-list').text()).toContain('Made')
    expect(document.body.querySelector('[data-test="undo-notice-text"]')!.textContent).toContain(
      'is ready.',
    )
  })

  it('says the AI is not set up and links to where it is', async () => {
    const { find } = await open(overview({ ai: 'No AI provider is set up.' }))

    expect(find('agents-ai').text()).toContain('No AI provider is set up.')
    expect(find('agents-ai').text()).toContain('still collect')
    expect(find('agents-ai-link').attributes('href')).toBe('/settings/ai')
  })

  it('says nothing about the AI when it would be asked', async () => {
    const { find } = await open()

    expect(find('agents-ai').exists()).toBe(false)
  })

  it('asks for a run of the agent whose button was pressed, and looks again', async () => {
    const { wrapper, start, list } = await open()

    await wrapper.find('[data-test="agent-run"]').trigger('click')
    await flushPromises()
    await flushPromises()

    expect(start).toHaveBeenCalledWith(3, TOKEN)
    expect(list).toHaveBeenCalledTimes(2)
  })

  it('says why a run was refused, and clears it with the next one', async () => {
    const { wrapper, find, start } = await open()
    start.mockRejectedValueOnce(
      new ApiError(409, 'This agent already has a run waiting or going.', 'x'),
    )

    await wrapper.find('[data-test="agent-run"]').trigger('click')
    await flushPromises()
    expect(find('agents-problem').text()).toContain('already has a run')

    await wrapper.find('[data-test="agent-run"]').trigger('click')
    await flushPromises()
    expect(find('agents-problem').exists()).toBe(false)
  })

  it('looks again every few seconds, leaving what is on screen if that fails', async () => {
    vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval'] })
    try {
      const { find, list } = await open()
      list.mockRejectedValue(new ApiError(0, 'Gone.', 'offline'))

      vi.advanceTimersByTime(4000)
      await flushPromises()

      expect(list).toHaveBeenCalledTimes(2)
      expect(find('agents-list').exists()).toBe(true)
      expect(find('agents-error').exists()).toBe(false)
    } finally {
      vi.useRealTimers()
    }
  })

  it('keeps saying why the first look failed when a refresh fails too', async () => {
    vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval'] })
    try {
      vi.spyOn(agentsApi, 'fetchAgents').mockRejectedValue(new ApiError(0, 'Gone.', 'offline'))
      const { wrapper } = await mountWithPlugins(AgentsView, { signedIn: 'admin', withApp: true })
      await flushPromises()
      vi.advanceTimersByTime(4000)
      await flushPromises()

      expect(wrapper.find('[data-test="agents-error"]').text()).toContain('Gone.')
    } finally {
      vi.useRealTimers()
    }
  })
})
