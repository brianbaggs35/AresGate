import { VSelect } from 'vuetify/components'

import * as aiApi from '@/api/ai'
import { ApiError } from '@/api/client'
import AiProviderForm from '@/components/AiProviderForm.vue'
import { UNCACHED, anthropic, ollama, ollamaCloud, openai } from '@/test/ai'
import { flushPromises, mountWithPlugins } from '@/test/mount'

const offline = () => new ApiError(0, "Can't reach AresGate.", 'offline')
const refused = (...problems: { path: string[]; message: string }[]) =>
  new ApiError(422, 'AresGate could not use that.', 'invalid', problems)

async function open(provider: aiApi.AiProvider = anthropic()) {
  const save = vi.spyOn(aiApi, 'saveProvider')
  const test = vi.spyOn(aiApi, 'testProvider')
  const models = vi.spyOn(aiApi, 'fetchProviderModels')
  const remove = vi.spyOn(aiApi, 'removeProvider').mockResolvedValue(undefined)
  const mounted = await mountWithPlugins(AiProviderForm, {
    signedIn: 'admin',
    withApp: true,
    props: { provider, pricedAsOf: '2026-10-27', freeModelsAsOf: '2026-10-25' },
  })
  const find = (selector: string) => mounted.wrapper.find(`[data-test="${selector}"]`)
  const text = (selector: string) => find(selector).text()
  const input = (selector: string) => find(selector).find('input')
  const card = () => mounted.wrapper.findComponent(AiProviderForm)
  const changed = () => card().emitted('changed') ?? []
  const removed = () => card().emitted('removed') ?? []
  const pickModel = async (model: string | null) => {
    const field = mounted.wrapper.findComponent(VSelect)
    field.vm.$emit('update:modelValue', model)
    await flushPromises()
  }
  const press = async (selector: string) => {
    await find(selector).trigger('click')
    await flushPromises()
  }
  const inDialog = (selector: string) =>
    document.querySelector<HTMLButtonElement>(`[data-test="${selector}"]`)
  return {
    ...mounted,
    save,
    test,
    models,
    remove,
    find,
    text,
    input,
    changed,
    removed,
    pickModel,
    press,
    inDialog,
  }
}

const kept = (overrides: Partial<aiApi.AiProvider> = {}) =>
  anthropic({
    configured: true,
    key_saved: true,
    model: 'claude-haiku-5-5',
    status: 'untested',
    ...overrides,
  })

describe('AiProviderForm', () => {
  describe('a hosted provider', () => {
    it('takes a key and a model from its list', async () => {
      const { find, input } = await open()

      expect(input('provider-key').attributes('id')).toBe('anthropic-api_key')
      expect(find('provider-url').exists()).toBe(false)
      expect(find('provider-model').text()).toContain('Claude Haiku 5.5')
      expect(find('provider-models-fetch').exists()).toBe(false)
      expect(find('provider-status').exists()).toBe(false)
      expect(find('provider-remove').exists()).toBe(false)
    })

    it('says where to make a key, and that it is kept encrypted', async () => {
      const { find } = await open()

      const link = find('provider-key-help').find('a')
      expect(link.attributes('href')).toBe('https://platform.claude.com/settings/keys')
      expect(link.attributes('rel')).toBe('noopener noreferrer')
      expect(link.text()).toBe('platform.claude.com')
      expect(find('provider-key-help').text()).toContain('kept encrypted and never shown again')
    })

    it('says what the chosen model is for and costs, with where the price comes from', async () => {
      const { find, text } = await open()

      expect(find('provider-model').text()).toContain(
        'Fast and cheap: a good fit for reading every incident · $0.10 in · $0.50 out per million tokens',
      )
      expect(find('provider-price').text()).not.toContain('$0.10 in')
      expect(text('provider-caching')).toBe(
        'Caches the fixed start of each prompt for 5 minutes: $0.01 to read it back and $0.125 to write it, per million tokens.',
      )
      expect(find('provider-price').text()).toContain(
        'A prompt over 100,000 tokens costs $0.50 in and $2.50 out, and $0.05 for input already cached.',
      )
      expect(text('provider-estimate')).toBe(
        'Reading one incident is about $0.0006, taking 3,000 tokens in and 600 out as a guess. With the cache warm, so that the 1,500 tokens of instructions are read from it, about $0.0005.',
      )
      expect(find('provider-deprecated').exists()).toBe(false)
      const link = find('provider-price').find('a')
      expect(link.attributes('href')).toBe(
        'https://platform.claude.com/docs/en/about-claude/pricing',
      )
      expect(find('provider-price').text()).toContain('as of 2026-10-27')
    })

    it('shows the price of another model when it is chosen', async () => {
      const { pickModel, find, text } = await open()

      await pickModel('claude-sonnet-5-5')

      expect(find('provider-model').text()).toContain(
        'Better reasoning for harder incidents · $2.00 in · $10.00 out per million tokens',
      )
      expect(find('provider-price').text()).not.toContain('over 100,000')
      expect(text('provider-estimate')).toContain('about $0.012')
    })

    it('says a model OpenAI is retiring is, and that it caches by itself', async () => {
      const { pickModel, find, text } = await open(openai())

      await pickModel('gpt-5.4-nano')

      expect(text('provider-deprecated')).toBe(
        'OpenAI lists this model as deprecated, so it will be retired. Choose another when you can.',
      )
      expect(text('provider-caching')).toContain('by itself at no extra charge')
      expect(find('provider-estimate').text()).toContain('With the cache warm')
    })

    it('has no price for a model that is not in the list', async () => {
      const { pickModel, find } = await open()

      await pickModel('nothing')

      expect(find('provider-price').exists()).toBe(false)
    })

    it('leaves out what the page for the prices is when a provider has none', async () => {
      const { find } = await open(anthropic({ pricing_url: null }))

      expect(find('provider-price').find('a').exists()).toBe(false)
    })

    it('leaves out where to make a key when it is not known, and a cached price when there is none', async () => {
      const bare = anthropic({
        key_url: null,
        models: [
          {
            id: 'claude-haiku-5-5',
            label: 'Claude Haiku 5.5',
            note: 'n',
            price: UNCACHED.price,
            caching: 'none',
            cache_minutes: null,
            deprecated: false,
          },
        ],
      })
      const { find, text } = await open(bare)

      expect(find('provider-key-help').exists()).toBe(false)
      expect(find('provider-caching').exists()).toBe(false)
      expect(text('provider-estimate')).not.toContain('cache')
    })

    it('cannot be tested until it has a key', async () => {
      const { find, input } = await open()
      expect(find('provider-test').attributes('disabled')).toBeDefined()

      await input('provider-key').setValue('sk-a-key')

      expect(find('provider-test').attributes('disabled')).toBeUndefined()
    })

    it('shows a key that is kept as kept, and never what it is', async () => {
      const { input, find } = await open(kept())

      expect(input('provider-key').attributes('placeholder')).toBe('Saved')
      expect(input('provider-key').element.value).toBe('')
      expect(find('provider-test').attributes('disabled')).toBeUndefined()
    })
  })

  describe('how it is doing', () => {
    it('shows the status of one that is set up', async () => {
      const { find } = await open(kept({ status: 'connected' }))

      expect(find('provider-status').text()).toBe('Connected')
      expect(find('provider-remove').exists()).toBe(true)
    })

    it('says when it last worked', async () => {
      const { find } = await open(
        kept({ status: 'connected', last_success_at: '2026-10-27T12:00:00Z' }),
      )

      expect(find('provider-last-success').text()).toContain('Last worked')
      expect(find('provider-last-success').find('time').attributes('datetime')).toBe(
        '2026-10-27T12:00:00Z',
      )
    })

    it('says why the last test failed, in place of when it worked', async () => {
      const { find } = await open(
        kept({
          status: 'problem',
          last_error: "Anthropic didn't accept the API key (HTTP 401).",
          last_success_at: '2026-10-27T12:00:00Z',
        }),
      )

      expect(find('provider-last-error').text()).toContain("didn't accept the API key")
      expect(find('provider-last-success').exists()).toBe(false)
    })
  })

  describe('keeping it', () => {
    it('saves the model and a typed key, then clears the key', async () => {
      const { save, find, input, pickModel, press, changed, wrapper } = await open()
      const saved = kept()
      save.mockResolvedValue(saved)
      await input('provider-key').setValue(' sk-a-key ')
      await pickModel('claude-sonnet-5-5')

      await press('provider-save')

      expect(save).toHaveBeenCalledWith(
        'anthropic',
        { model: 'claude-sonnet-5-5', api_key: 'sk-a-key' },
        'a-security-token',
      )
      expect(changed()).toEqual([[saved]])
      expect(find('provider-notice').text()).toBe('Saved.')
      expect(input('provider-key').element.value).toBe('')
      expect(wrapper.find('[data-test="provider-failure"]').exists()).toBe(false)
    })

    it('keeps the key that is kept when none is typed', async () => {
      const { save, press } = await open(kept())
      save.mockResolvedValue(kept())

      await press('provider-save')

      expect(save.mock.calls[0]?.[1]).toEqual({ model: 'claude-haiku-5-5' })
    })

    it('shows what is wrong with each field, and puts the keyboard on the first', async () => {
      const { save, press, find, changed } = await open()
      save.mockRejectedValue(
        refused(
          { path: ['model'], message: 'Choose one of the models in the list.' },
          { path: ['api_key'], message: 'Enter the API key.' },
        ),
      )

      await press('provider-save')
      await flushPromises()

      expect(find('provider-key').text()).toContain('Enter the API key.')
      expect(find('provider-model').text()).toContain('Choose one of the models in the list.')
      expect(document.activeElement?.id).toBe('anthropic-api_key')
      expect(changed()).toEqual([])
      expect(find('provider-notice').exists()).toBe(false)
    })

    it('shows the address problem of one on the owner’s computer', async () => {
      const { save, press, find } = await open(ollama())
      save.mockRejectedValue(
        refused({ path: ['base_url'], message: "8.8.8.8 isn't a private network address." }),
      )

      await press('provider-save')
      await flushPromises()

      expect(find('provider-url').text()).toContain("isn't a private network address")
      expect(document.activeElement?.id).toBe('ollama-base_url')
    })

    it('keeps the keyboard where it is for a problem with no field of its own', async () => {
      const { save, press, find } = await open()
      save.mockRejectedValue(refused({ path: ['elsewhere'], message: 'Something else.' }))
      ;(find('provider-save').element as HTMLElement).focus()

      await press('provider-save')
      await flushPromises()

      expect(document.activeElement).toBe(find('provider-save').element)
    })

    it('says so when it could not be saved at all', async () => {
      const { save, press, find } = await open()
      save.mockRejectedValue(offline())

      await press('provider-save')

      expect(find('provider-failure').text()).toContain("Can't reach AresGate.")
    })

    it('forgets what was wrong when it is tried again', async () => {
      const { save, press, find } = await open()
      save.mockRejectedValueOnce(refused({ path: ['api_key'], message: 'Enter the API key.' }))
      await press('provider-save')
      save.mockResolvedValue(kept())

      await press('provider-save')

      expect(find('provider-key').text()).not.toContain('Enter the API key.')
      expect(find('provider-notice').text()).toBe('Saved.')
    })
  })

  describe('testing it', () => {
    const report = (overrides: Partial<aiApi.AiCheck> = {}): aiApi.AiCheck => ({
      ok: true,
      message: 'claude-haiku-5-5 answered. It counted 14 tokens in and 1 out.',
      provider: kept({ status: 'connected' }),
      ...overrides,
    })

    it('saves what was filled in first, then tests it', async () => {
      const { save, test, press, find, input, changed } = await open()
      save.mockResolvedValue(kept())
      test.mockResolvedValue(report())
      await input('provider-key').setValue('sk-a-key')

      await press('provider-test')

      expect(save).toHaveBeenCalledOnce()
      expect(test).toHaveBeenCalledWith('anthropic', 'a-security-token')
      expect(save.mock.invocationCallOrder[0]).toBeLessThan(test.mock.invocationCallOrder[0] ?? 0)
      expect(changed()).toHaveLength(2)
      expect(changed()[1]).toEqual([report().provider])
      expect(find('provider-notice').text()).toBe(report().message)
    })

    it('tests what is kept without saving it again', async () => {
      const { save, test, press } = await open(kept())
      test.mockResolvedValue(report())

      await press('provider-test')

      expect(save).not.toHaveBeenCalled()
      expect(test).toHaveBeenCalledOnce()
    })

    it('does not test what could not be saved', async () => {
      const { save, test, press, find, input } = await open()
      save.mockRejectedValue(refused({ path: ['model'], message: 'Nope.' }))
      await input('provider-key').setValue('sk-a-key')

      await press('provider-test')

      expect(test).not.toHaveBeenCalled()
      expect(find('provider-model').text()).toContain('Nope.')
    })

    it('leaves a failed test to the last error the answer carries', async () => {
      const { test, press, find, changed } = await open(kept())
      const failed = kept({ status: 'problem', last_error: 'It broke.' })
      test.mockResolvedValue(report({ ok: false, message: 'It broke.', provider: failed }))

      await press('provider-test')

      expect(changed()).toEqual([[failed]])
      expect(find('provider-notice').exists()).toBe(false)
    })

    it('says so when nothing answered', async () => {
      const { test, press, find } = await open(kept())
      test.mockRejectedValue(offline())

      await press('provider-test')

      expect(find('provider-failure').text()).toContain("Can't reach AresGate.")
    })

    it('shows it working, and keeps the other buttons from being pressed meanwhile', async () => {
      const { test, press, find } = await open(kept())
      let finish: (value: aiApi.AiCheck) => void = () => {}
      test.mockReturnValue(new Promise((resolve) => (finish = resolve)))

      await press('provider-test')

      expect(find('provider-test').classes()).toContain('v-btn--loading')
      expect(find('provider-save').attributes('disabled')).toBeDefined()
      expect(find('provider-remove').attributes('disabled')).toBeDefined()
      finish(report())
      await flushPromises()
      expect(find('provider-save').attributes('disabled')).toBeUndefined()
    })
  })

  describe('an Ollama on the owner’s computer', () => {
    it('takes an address, and says what to give', async () => {
      const { find, input } = await open(ollama())

      expect(input('provider-url').attributes('placeholder')).toBe('http://192.168.1.50:11434')
      expect(find('provider-url').text()).toContain('http://host.docker.internal:11434')
      expect(find('provider-url').text()).toContain('localhost is the container itself')
      expect(find('provider-key').exists()).toBe(false)
      expect(find('provider-free').text()).toContain('costs nothing to ask')
      expect(find('provider-price').exists()).toBe(false)
    })

    it('asks for the models once it has an address, and offers them', async () => {
      const { save, models, press, find, input, changed } = await open(ollama())
      expect(find('provider-models-fetch').attributes('disabled')).toBeDefined()
      await input('provider-url').setValue('http://192.168.1.50:11434')
      expect(find('provider-models-fetch').attributes('disabled')).toBeUndefined()
      const withUrl = ollama({
        configured: true,
        base_url: 'http://192.168.1.50:11434',
        model: '',
        status: 'untested',
      })
      save.mockResolvedValue(withUrl)
      const found = ollama({
        ...withUrl,
        status: 'connected',
        found: [
          {
            name: 'qwen3:8b',
            size: 5_200_000_000,
            family: 'qwen3',
            parameters: '8.2B',
            quantization: 'Q4_K_M',
          },
        ],
      })
      models.mockResolvedValue({ ok: true, message: 'It has 1 model.', provider: found })

      await press('provider-models-fetch')

      expect(save).toHaveBeenCalledWith(
        'ollama',
        { model: '', base_url: 'http://192.168.1.50:11434' },
        'a-security-token',
      )
      expect(models).toHaveBeenCalledWith('ollama', 'a-security-token')
      expect(changed()).toHaveLength(2)
      expect(find('provider-notice').text()).toBe('It has 1 model.')
    })

    it('says how many models were found, and lets one be chosen', async () => {
      const found = [
        { name: 'a:1b', size: null, family: null, parameters: null, quantization: null },
        { name: 'b:1b', size: null, family: null, parameters: null, quantization: null },
      ]
      const { find, pickModel, save, press } = await open(
        ollama({ configured: true, base_url: 'http://10.0.0.5:11434', model: '', found }),
      )
      save.mockResolvedValue(
        ollama({ configured: true, base_url: 'http://10.0.0.5:11434', model: 'b:1b' }),
      )

      expect(find('provider-model').text()).toContain('2 models found: choose one.')
      await pickModel('b:1b')
      await press('provider-save')

      expect(save.mock.calls[0]?.[1]).toEqual({ model: 'b:1b', base_url: 'http://10.0.0.5:11434' })
    })

    it('keeps no model when the one chosen is cleared', async () => {
      const { find, pickModel, press, save } = await open(
        ollama({ configured: true, base_url: 'http://10.0.0.5:11434', model: 'a:1b' }),
      )
      save.mockResolvedValue(ollama({ configured: true, base_url: 'http://10.0.0.5:11434' }))

      await pickModel(null)
      await press('provider-save')

      expect(save.mock.calls[0]?.[1]).toEqual({ model: '', base_url: 'http://10.0.0.5:11434' })
      expect(find('provider-model').exists()).toBe(true)
    })

    it('is a list to choose from, not a box to type in', async () => {
      const { wrapper } = await open(ollama())

      const field = wrapper.findComponent(VSelect)
      expect(field.exists()).toBe(true)
      expect(field.find('.v-field--variant-outlined').exists()).toBe(true)
      expect(wrapper.find('.v-combobox').exists()).toBe(false)
    })

    it('says there are none to choose from until the models are fetched', async () => {
      const { wrapper, find } = await open(ollama())

      expect(wrapper.findComponent(VSelect).props('noDataText')).toBe(
        'No models yet. Press Fetch models to list the ones it has.',
      )
      expect(find('provider-model').text()).toContain('Press Fetch models to list the ones it has.')
    })

    it('still offers the model that is kept when the models have not been fetched', async () => {
      const { wrapper, find } = await open(
        ollama({ configured: true, base_url: 'http://10.0.0.5:11434', model: 'llama3.2:3b' }),
      )

      expect(wrapper.findComponent(VSelect).props('items')).toEqual([
        { value: 'llama3.2:3b', title: 'llama3.2:3b', props: { subtitle: 'The model you saved' } },
      ])
      expect(find('provider-model').text()).toContain('llama3.2:3b')
    })

    it('says what the models are, with their size for one on the owner’s computer', async () => {
      const found = [
        {
          name: 'qwen3:8b',
          size: 5_200_000_000,
          family: 'qwen3',
          parameters: '8.2B',
          quantization: 'Q4_K_M',
        },
      ]
      const { wrapper } = await open(
        ollama({ configured: true, base_url: 'http://10.0.0.5:11434', model: 'qwen3:8b', found }),
      )

      expect(wrapper.findComponent(VSelect).props('items')).toEqual([
        {
          value: 'qwen3:8b',
          title: 'qwen3:8b',
          props: { subtitle: 'qwen3 · 8.2B · Q4_K_M · 4.8 GB' },
        },
      ])
    })

    it('says "model" when there is one', async () => {
      const found = [
        { name: 'a:1b', size: null, family: null, parameters: null, quantization: null },
      ]
      const { find } = await open(
        ollama({ configured: true, base_url: 'http://10.0.0.5:11434', found }),
      )

      expect(find('provider-model').text()).toContain('1 model found: choose one.')
    })

    it('can be tested with the address alone', async () => {
      const { find, input } = await open(ollama())
      expect(find('provider-test').attributes('disabled')).toBeDefined()

      await input('provider-url').setValue('http://10.0.0.5:11434')

      expect(find('provider-test').attributes('disabled')).toBeUndefined()
    })

    it('has no way to fetch models for a hosted provider', async () => {
      const { find } = await open(openai())

      expect(find('provider-models-fetch').exists()).toBe(false)
    })
  })

  describe('Ollama’s cloud', () => {
    it('takes a key, says it is not priced, and fetches models once there is a key', async () => {
      const { find, input } = await open(ollamaCloud())

      expect(find('provider-url').exists()).toBe(false)
      expect(find('provider-unpriced').text()).toContain("isn't priced per token")
      expect(find('provider-models-fetch').attributes('disabled')).toBeDefined()
      expect(find('provider-key-help').find('a').text()).toBe('ollama.com')

      await input('provider-key').setValue('sk-cloud')

      expect(find('provider-models-fetch').attributes('disabled')).toBeUndefined()
    })

    describe('free and paid accounts', () => {
      const found = [
        { name: 'glm-5.2', size: 0, family: null, parameters: null, quantization: null },
        { name: 'gpt-oss:120b', size: 0, family: null, parameters: null, quantization: null },
        { name: 'gpt-oss:20b', size: 0, family: null, parameters: null, quantization: null },
      ]
      const account = (overrides: Partial<aiApi.AiProvider> = {}) =>
        ollamaCloud({
          configured: true,
          key_saved: true,
          model: 'gpt-oss:20b',
          found,
          ...overrides,
        })
      const itemsOf = (wrapper: Awaited<ReturnType<typeof open>>['wrapper']) =>
        wrapper
          .findComponent(VSelect)
          .props('items')
          ?.map((item: { value: string }) => item.value)

      it('asks which account it is, free until it is said to be paid', async () => {
        const { find } = await open(ollamaCloud())

        expect(find('provider-plan').text()).toContain('Your Ollama account')
        expect(find('provider-plan-help').text()).toContain(
          'nothing Ollama answers says which account',
        )
        expect(find('provider-plan-free').find('input').element.checked).toBe(true)
        expect(find('provider-plan-paid').find('input').element.checked).toBe(false)
        expect(find('provider-free-models').text()).toBe(
          'Free usage covers gemma4:31b, gpt-oss:120b, gpt-oss:20b, as of 2026-10-25. Ollama can change this and names no page that lists it, so if one of these asks for payment, choose Paid.',
        )
      })

      it('offers only the models free usage covers to a free account, and says how many it leaves out', async () => {
        const { wrapper, find } = await open(account())

        expect(itemsOf(wrapper)).toEqual(['gpt-oss:120b', 'gpt-oss:20b'])
        expect(find('provider-model').text()).toContain(
          '2 models found: choose one. 1 more need a paid plan.',
        )
      })

      it('offers every model to a paid account, and drops the note about free usage', async () => {
        const { wrapper, find } = await open(account())

        await find('provider-plan-paid').find('input').setValue(true)

        expect(itemsOf(wrapper)).toEqual(['glm-5.2', 'gpt-oss:120b', 'gpt-oss:20b'])
        expect(find('provider-model').text()).toContain('3 models found: choose one.')
        expect(find('provider-free-models').exists()).toBe(false)
      })

      it('starts from the plan that is kept', async () => {
        const { wrapper, find } = await open(account({ plan: 'paid', model: 'glm-5.2' }))

        expect(find('provider-plan-paid').find('input').element.checked).toBe(true)
        expect(itemsOf(wrapper)).toContain('glm-5.2')
      })

      it('keeps a model free usage does not cover in the list when it is the one kept', async () => {
        const { wrapper } = await open(account({ model: 'glm-5.2' }))

        expect(itemsOf(wrapper)).toEqual(['glm-5.2', 'gpt-oss:120b', 'gpt-oss:20b'])
      })

      it('saves the plan with the rest', async () => {
        const { find, press, save } = await open(account())
        save.mockResolvedValue(account({ plan: 'paid' }))

        await find('provider-plan-paid').find('input').setValue(true)
        await press('provider-save')

        expect(save).toHaveBeenCalledWith(
          'ollama_cloud',
          { model: 'gpt-oss:20b', plan: 'paid' },
          'a-security-token',
        )
      })

      it('saves a change of plan before it asks for the models', async () => {
        const { find, press, save, models } = await open(account())
        save.mockResolvedValue(account({ plan: 'paid' }))
        models.mockResolvedValue({ ok: true, message: 'It has 3 models.', provider: account() })

        await find('provider-plan-paid').find('input').setValue(true)
        await press('provider-models-fetch')

        expect(save).toHaveBeenCalledTimes(1)
        expect(models).toHaveBeenCalledOnce()
      })

      it('has no account to choose for a provider whose models do not depend on it', async () => {
        for (const provider of [ollama(), anthropic()]) {
          const { find } = await open(provider)

          expect(find('provider-plan').exists()).toBe(false)
          expect(find('provider-free-models').exists()).toBe(false)
        }
      })
    })

    it('says what went wrong when the models could not be fetched', async () => {
      const { models, press, find } = await open(
        ollamaCloud({ configured: true, key_saved: true, model: '' }),
      )
      models.mockRejectedValue(offline())

      await press('provider-models-fetch')

      expect(find('provider-failure').text()).toContain("Can't reach AresGate.")
    })
  })

  describe('removing it', () => {
    it('asks first, and says what happens to the key', async () => {
      const { press, inDialog, remove } = await open(kept())

      await press('provider-remove')

      expect(inDialog('confirm-title')?.textContent).toBe('Remove Anthropic?')
      expect(inDialog('confirm-message')?.textContent).toContain(
        'The key still works at the provider until you delete it there.',
      )
      expect(remove).not.toHaveBeenCalled()
    })

    it('does nothing when it is cancelled', async () => {
      const { press, inDialog, remove, removed } = await open(kept())
      await press('provider-remove')

      inDialog('confirm-cancel')?.click()
      await flushPromises()

      expect(remove).not.toHaveBeenCalled()
      expect(removed()).toEqual([])
    })

    it('forgets it, and goes back to the defaults', async () => {
      const { press, inDialog, remove, removed, pickModel, find, input } = await open(kept())
      await pickModel('claude-sonnet-5-5')
      await press('provider-remove')

      inDialog('confirm-accept')?.click()
      await flushPromises()

      expect(remove).toHaveBeenCalledWith('anthropic', 'a-security-token')
      expect(removed()).toEqual([['anthropic']])
      expect(find('provider-model').text()).toContain('Claude Haiku 5.5')
      expect(input('provider-key').element.value).toBe('')
    })

    it('says what an Ollama on the owner’s computer loses', async () => {
      const { press, inDialog } = await open(ollama({ configured: true, model: 'a:1b' }))

      await press('provider-remove')

      expect(inDialog('confirm-message')?.textContent).toContain('Its settings are deleted')
      expect(inDialog('confirm-message')?.textContent).not.toContain('key')
    })

    it('leaves an Ollama with no model after it is forgotten', async () => {
      const { press, inDialog, find } = await open(
        ollama({ configured: true, base_url: 'http://10.0.0.5:11434', model: 'a:1b' }),
      )
      await press('provider-remove')

      inDialog('confirm-accept')?.click()
      await flushPromises()

      expect(find('provider-model').find('.v-select__selection').exists()).toBe(false)
      expect(find('provider-url').find('input').element.value).toBe('')
    })

    it('says so when it could not be removed', async () => {
      const { press, inDialog, remove, find, removed } = await open(kept())
      remove.mockRejectedValue(offline())
      await press('provider-remove')

      inDialog('confirm-accept')?.click()
      await flushPromises()

      expect(find('provider-failure').text()).toContain("Can't reach AresGate.")
      expect(removed()).toEqual([])
    })
  })
})
