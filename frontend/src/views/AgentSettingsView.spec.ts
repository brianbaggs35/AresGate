import * as agentsApi from '@/api/agents'
import type { AgentSettings } from '@/api/agents'
import * as aiApi from '@/api/ai'
import { ApiError } from '@/api/client'
import AiProviderForm from '@/components/AiProviderForm.vue'
import AiProviderPicker from '@/components/AiProviderPicker.vue'
import { limits, settings } from '@/test/agents'
import { ai, anthropic, ollama, openai } from '@/test/ai'
import { flushPromises, mountWithPlugins } from '@/test/mount'
import AgentSettingsView from '@/views/AgentSettingsView.vue'

/** What the tests use of a select. */
interface Select {
  props(name: string): unknown
  vm: { $emit(event: string, value: unknown): void }
}

const offline = () => new ApiError(0, "Can't reach AresGate.", 'offline')

const READY = anthropic({
  configured: true,
  key_saved: true,
  model: 'claude-haiku-5-5',
  status: 'connected',
})
const LOCAL = ollama({
  configured: true,
  model: 'llama3',
  base_url: 'http://192.168.1.50:11434',
  found: [{ name: 'qwen3:8b', size: null, family: null, parameters: null, quantization: null }],
})
const TOKEN = 'a-security-token'

async function open(
  kept: AgentSettings | Error = settings(),
  providers: aiApi.Ai | Error = ai({ providers: [LOCAL, READY, openai()] }),
) {
  const read = vi.spyOn(agentsApi, 'fetchAgentSettings')
  if (kept instanceof Error) read.mockRejectedValue(kept)
  else read.mockResolvedValue(kept)
  const providersRead = vi.spyOn(aiApi, 'fetchAi')
  if (providers instanceof Error) providersRead.mockRejectedValue(providers)
  else providersRead.mockResolvedValue(providers)
  const save = vi.spyOn(agentsApi, 'saveAgentSettings').mockImplementation((choices) =>
    Promise.resolve(
      settings({
        ai_source: choices.ai_source,
        provider: choices.provider,
        model: choices.model,
        limits: limits([
          { limit_micros: choices.daily ? Number(choices.daily) * 1e6 : null },
          { period: 'month', limit_micros: choices.monthly ? Number(choices.monthly) * 1e6 : null },
        ]),
      }),
    ),
  )
  const mounted = await mountWithPlugins(AgentSettingsView, { signedIn: 'admin', withApp: true })
  await flushPromises()
  const find = (selector: string) => mounted.wrapper.find(`[data-test="${selector}"]`)
  const forms = () => mounted.wrapper.findAllComponents(AiProviderForm)
  const click = async (selector: string) => {
    await find(selector).trigger('click')
    await flushPromises()
    await flushPromises()
  }
  const choose = async (source: string) => {
    await find(`source-${source}`).find('input').setValue(true)
    await flushPromises()
  }
  const pick = async (key: string) => {
    await find(`pick-${key}`).find('input').setValue(true)
    await flushPromises()
  }
  const select = () =>
    mounted.wrapper
      .findAllComponents({ name: 'VSelect' })
      .find((each) => each.props('label') === 'Model for the agents') as unknown as Select
  return { ...mounted, read, save, find, forms, click, choose, pick, select }
}

describe('AgentSettingsView', () => {
  it('shows a placeholder while it asks', async () => {
    vi.spyOn(agentsApi, 'fetchAgentSettings').mockReturnValue(new Promise(() => {}))
    vi.spyOn(aiApi, 'fetchAi').mockReturnValue(new Promise(() => {}))
    const { wrapper } = await mountWithPlugins(AgentSettingsView, { signedIn: 'admin' })

    expect(wrapper.find('.v-skeleton-loader').exists()).toBe(true)
  })

  it('says why it could not load, and tries again', async () => {
    const { find, click, read } = await open(offline())

    expect(find('agent-settings-error').text()).toContain("Can't reach AresGate.")
    read.mockResolvedValue(settings())

    await click('agent-settings-retry')

    expect(find('agent-settings-error').exists()).toBe(false)
    expect(find('agent-ai-card').exists()).toBe(true)
  })

  it('says it could not load when the providers could not be read', async () => {
    const { find } = await open(settings(), offline())

    expect(find('agent-settings-error').exists()).toBe(true)
  })

  it('starts with the agents on what Settings > AI chose, and says who they ask', async () => {
    const { find, forms } = await open()

    expect(find('agent-ai-card').find('h2').text()).toBe('Which AI the agents use')
    expect(find('source-shared').find('input').element).toHaveProperty('checked', true)
    expect(find('agent-ai-state').text()).toBe('Anthropic, claude-haiku-5-5')
    expect(find('agent-own').exists()).toBe(false)
    expect(forms()).toHaveLength(0)
    expect(find('agent-ai-reason').exists()).toBe(false)
  })

  it('says why no AI is asked, with a link to where to turn it on', async () => {
    const { find } = await open(
      settings({
        asking: null,
        reason: 'AI is turned off. Turn it on under Settings > AI to use it.',
      }),
    )

    expect(find('agent-ai-state').text()).toBe('Not asking an AI')
    expect(find('agent-ai-reason').text()).toContain('AI is turned off.')
    expect(find('agent-ai-link').attributes('href')).toBe('/settings/ai')
  })

  it('does not say why while what is chosen has not been saved', async () => {
    const { find, choose } = await open(
      settings({
        asking: null,
        reason: 'AI is turned off. Turn it on under Settings > AI to use it.',
      }),
    )

    await choose('off')

    expect(find('agent-ai-reason').exists()).toBe(false)
  })

  it('has no link to Settings > AI when the reason is about the agents', async () => {
    const { find } = await open(
      settings({
        ai_source: 'off',
        asking: null,
        reason: 'AI is turned off for the agents. Turn it on under Settings > Agents.',
      }),
    )

    expect(find('agent-ai-reason').exists()).toBe(true)
    expect(find('agent-ai-link').exists()).toBe(false)
  })

  it('keeps that the agents ask none', async () => {
    const { find, choose, click, save } = await open()

    await choose('off')
    await click('agent-ai-save')

    expect(save).toHaveBeenCalledWith(
      { ai_source: 'off', provider: null, model: null, daily: null, monthly: null },
      expect.any(String),
    )
    expect(find('agent-ai-saved').text()).toBe('Saved.')
  })

  it('offers the providers for a provider of their own, starting on one that is set up', async () => {
    const { find, forms, choose, wrapper } = await open()

    await choose('own')

    expect(wrapper.findComponent(AiProviderPicker).props('providers')).toHaveLength(3)
    expect(forms()).toHaveLength(1)
    expect(forms()[0]?.props('provider').key).toBe('ollama')
    expect(find('agent-choose').exists()).toBe(false)
  })

  it('starts on the provider Settings > AI asks, if there is one', async () => {
    const { forms, choose } = await open(
      settings(),
      ai({ provider: 'anthropic', providers: [LOCAL, READY] }),
    )

    await choose('own')

    expect(forms()[0]?.props('provider').key).toBe('anthropic')
  })

  it('asks to choose one when none is set up', async () => {
    const { find, forms, choose } = await open(settings(), ai({ providers: [openai()] }))

    await choose('own')

    expect(forms()).toHaveLength(0)
    expect(find('agent-choose').text()).toContain('Choose one to set it up.')
  })

  it('keeps a provider and a model for the agents', async () => {
    const { find, choose, pick, click, save, select } = await open()

    await choose('own')
    await pick('anthropic')
    select().vm.$emit('update:modelValue', 'claude-sonnet-5-5')
    await flushPromises()
    await click('agent-ai-save')

    expect(save).toHaveBeenCalledWith(
      {
        ai_source: 'own',
        provider: 'anthropic',
        model: 'claude-sonnet-5-5',
        daily: null,
        monthly: null,
      },
      expect.any(String),
    )
    expect(find('agent-ai-saved').exists()).toBe(true)
  })

  it('offers the models of a hosted provider, and the one it was set up with', async () => {
    const { select, choose, pick } = await open()

    await choose('own')
    await pick('anthropic')

    const items = select().props('items') as {
      value: string | null
      title: string
    }[]
    expect(items[0]).toEqual({ value: null, title: 'As set up (claude-haiku-5-5)' })
    expect(items.map((item) => item.value)).toEqual([null, 'claude-haiku-5-5', 'claude-sonnet-5-5'])
  })

  it('offers the models an Ollama has, and starts again from the provider when it is changed', async () => {
    const { select, pick } = await open(
      settings({ ai_source: 'own', provider: 'anthropic', model: 'claude-sonnet-5-5' }),
    )

    expect(select().props('modelValue')).toBe('claude-sonnet-5-5')

    await pick('ollama')

    expect(select().props('modelValue')).toBeNull()
    expect(
      (select().props('items') as { value: string | null }[]).map((item) => item.value),
    ).toEqual([null, 'llama3', 'qwen3:8b'])
  })

  it('says a provider that is not saved yet has to be before it is chosen', async () => {
    const { find, choose, pick, select } = await open(settings(), ai({ providers: [openai()] }))

    await choose('own')
    await pick('openai')

    expect(find('agent-ai-notready').text()).toContain('Save the provider first')
    expect(find('agent-ai-save').attributes('disabled')).toBeDefined()
    expect(select().props('disabled')).toBe(true)
  })

  it('shows the provider as it is after it is saved or tested, and looks again when it is removed', async () => {
    const { find, forms, choose, pick, read, wrapper } = await open(
      settings(),
      ai({ providers: [openai(), READY] }),
    )
    await choose('own')
    await pick('openai')
    expect(find('agent-ai-notready').exists()).toBe(true)

    forms()[0]?.vm.$emit(
      'changed',
      openai({ configured: true, key_saved: true, model: 'gpt-6-luna' }),
    )
    await flushPromises()

    expect(find('agent-ai-notready').exists()).toBe(false)
    read.mockClear()
    forms()[0]?.vm.$emit('removed', 'openai')
    await flushPromises()
    expect(read).toHaveBeenCalledTimes(1)
    expect(wrapper.exists()).toBe(true)
  })

  it('says why keeping the choice was refused, and keeps what was on screen', async () => {
    const { find, choose, click, save } = await open()
    save.mockRejectedValue(
      new ApiError(422, 'Set that provider up under Settings > AI first.', 'x'),
    )

    await choose('off')
    await click('agent-ai-save')

    expect(find('agent-ai-failure').text()).toContain('Set that provider up')
    expect(find('agent-ai-saved').exists()).toBe(false)
  })

  it('starts from the choice that is kept', async () => {
    const { find } = await open(
      settings({ ai_source: 'own', provider: 'anthropic', model: 'claude-sonnet-5-5' }),
    )

    expect(find('source-own').find('input').element).toHaveProperty('checked', true)
    expect(find('agent-own').exists()).toBe(true)
  })

  describe('what they may spend', () => {
    it('shows how much of each limit is gone', async () => {
      const { find } = await open(
        settings({
          limits: limits([
            { limit_micros: 2_000_000, spent_micros: 1_000_000, state: 'ok' },
            { period: 'month', limit_micros: null, spent_micros: 300_000 },
          ]),
        }),
      )

      expect(find('agent-limit-day').text()).toContain('Daily limit')
      expect(find('agent-limit-day').text()).toContain('$1.00 of $2.00')
      expect(find('agent-limit-day').find('[role="progressbar"]').exists()).toBe(true)
      expect(find('agent-limit-month').text()).toContain('$0.30 spent, with no limit')
      expect(find('agent-limit-month').find('[role="progressbar"]').exists()).toBe(false)
      expect(find('agent-limit-daily-field').find('input').element).toHaveProperty('value', '2')
    })

    it('keeps the limits, and what is kept of the choice of AI with them', async () => {
      const { find, click, save } = await open(
        settings({ ai_source: 'own', provider: 'anthropic', model: 'claude-sonnet-5-5' }),
      )

      await find('agent-limit-daily-field').find('input').setValue('1.50')
      await find('agent-limit-monthly-field').find('input').setValue('20')
      await click('agent-limits-save')

      expect(save).toHaveBeenCalledWith(
        {
          ai_source: 'own',
          provider: 'anthropic',
          model: 'claude-sonnet-5-5',
          daily: '1.50',
          monthly: '20',
        },
        expect.any(String),
      )
      expect(find('agent-limits-saved').text()).toBe('The limits are saved.')
      expect(find('agent-limit-daily-field').find('input').element).toHaveProperty('value', '1.5')
    })

    it('lets the cleanup agent do the surest itself, keeping the rest as it was', async () => {
      const { find, click, save } = await open(
        settings({ ai_source: 'own', provider: 'anthropic', model: 'claude-sonnet-5-5' }),
      )
      expect(find('cleanup-suggest').find('input').element).toHaveProperty('checked', true)

      await find('cleanup-auto').find('input').setValue(true)
      await click('agent-cleanup-save')

      expect(save).toHaveBeenCalledWith(
        {
          ai_source: 'own',
          provider: 'anthropic',
          model: 'claude-sonnet-5-5',
          daily: null,
          monthly: null,
          cleanup_mode: 'auto',
        },
        expect.any(String),
      )
      expect(find('agent-cleanup-saved').text()).toBe('Saved.')
    })

    it('says why the cleanup choice was refused', async () => {
      const { find, click, save } = await open()
      save.mockRejectedValueOnce(new ApiError(422, 'Choose suggest or auto.'))

      await click('agent-cleanup-save')

      expect(find('agent-cleanup-failure').text()).toBe('Choose suggest or auto.')
    })

    it('keeps the choice of AI without the limits that were typed and not saved', async () => {
      const { find, choose, click, save } = await open()

      await find('agent-limit-daily-field').find('input').setValue('9')
      await choose('off')
      await click('agent-ai-save')

      expect(save).toHaveBeenCalledWith(
        { ai_source: 'off', provider: null, model: null, daily: null, monthly: null },
        expect.any(String),
      )
    })

    it('does not save an amount that is not dollars and cents, or nothing', async () => {
      const { find, save } = await open()

      await find('agent-limit-daily-field').find('input').setValue('a lot')
      await flushPromises()
      expect(find('agent-limits-save').attributes('disabled')).toBeDefined()
      expect(find('agent-limit-daily-field').text()).toContain('Use dollars and cents')

      await find('agent-limit-daily-field').find('input').setValue('0')
      await flushPromises()
      expect(find('agent-limit-daily-field').text()).toContain('Use more than nothing')

      await find('agent-limit-daily-field').find('input').setValue('')
      await flushPromises()
      expect(find('agent-limits-save').attributes('disabled')).toBeUndefined()
      expect(save).not.toHaveBeenCalled()
    })

    it('says why keeping them was refused', async () => {
      const { find, click, save } = await open()
      save.mockRejectedValue(offline())

      await find('agent-limit-daily-field').find('input').setValue('3')
      await click('agent-limits-save')

      expect(find('agent-limits-failure').text()).toContain("Can't reach AresGate.")
      expect(find('agent-limits-saved').exists()).toBe(false)
    })
  })

  it('sends the sign-in token with a change', async () => {
    const { choose, click, save } = await open()

    await choose('off')
    await click('agent-ai-save')

    expect(typeof save.mock.calls[0]?.[1]).toBe('string')
    expect(TOKEN).toBeTruthy()
  })
})
