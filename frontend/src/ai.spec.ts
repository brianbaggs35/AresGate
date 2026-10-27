import {
  ASSUMED_TOKENS,
  canTest,
  describeFound,
  cachedIncidentCost,
  cachingNote,
  describePrice,
  estimateNote,
  draftFrom,
  foundHint,
  foundItems,
  formatUsd,
  hasPlans,
  incidentCost,
  isChanged,
  isReady,
  longPromptNote,
  modelHint,
  modelItems,
  priceNote,
  problemsByField,
  providerFieldId,
  settingsFrom,
  useNote,
} from '@/ai'
import {
  HAIKU,
  LUNA,
  NANO,
  SONNET,
  UNCACHED,
  anthropic,
  ollama,
  ollamaCloud,
  openai,
} from '@/test/ai'

describe('prices', () => {
  it('writes dollars with the decimals a price needs', () => {
    expect(formatUsd(2, 'en-US')).toBe('$2.00')
    expect(formatUsd(0.1, 'en-US')).toBe('$0.10')
    expect(formatUsd(4.5, 'en-US')).toBe('$4.50')
    expect(formatUsd(0.075, 'en-US')).toBe('$0.075')
    expect(formatUsd(0.0006, 'en-US')).toBe('$0.0006')
    expect(formatUsd(0, 'en-US')).toBe('$0.00')
  })

  it('does not round something small to nothing', () => {
    expect(formatUsd(0.00004, 'en-US')).toBe('less than $0.0001')
  })

  it('says what a model costs in and out', () => {
    expect(describePrice(HAIKU.price, 'en-US')).toBe('$0.10 in · $0.50 out per million tokens')
  })

  it('works out a reading of one incident from the tokens it is assumed to take', () => {
    expect(ASSUMED_TOKENS).toEqual({ input: 3000, fixed: 1500, output: 600 })
    expect(incidentCost(HAIKU.price)).toBeCloseTo(0.0006)
    expect(incidentCost(SONNET.price)).toBeCloseTo(0.012)
  })

  it('works out a reading with the fixed part of what goes in already cached', () => {
    expect(incidentCost(HAIKU.price, true)).toBeCloseTo(0.000465)
    expect(incidentCost(SONNET.price, true)).toBeCloseTo(0.00915)
    // A price without a cached rate reads the fixed part at the full rate.
    expect(incidentCost(UNCACHED.price, true)).toBeCloseTo(incidentCost(UNCACHED.price))
  })

  it('has a cached reading only for a model that caches and has a price for reading the cache', () => {
    expect(cachedIncidentCost(HAIKU)).toBeCloseTo(0.000465)
    expect(cachedIncidentCost(NANO)).toBeCloseTo(0.00108)
    expect(cachedIncidentCost(UNCACHED)).toBeNull()
    expect(
      cachedIncidentCost({ ...HAIKU, price: { ...HAIKU.price, cached_input: null } }),
    ).toBeNull()
  })

  it('says what reading an incident costs, and what it costs with the cache warm', () => {
    expect(estimateNote(HAIKU, 'en-US')).toBe(
      'Reading one incident is about $0.0006, taking 3,000 tokens in and 600 out as a guess. With the cache warm, so that the 1,500 tokens of instructions are read from it, about $0.0005.',
    )
    expect(estimateNote(UNCACHED, 'en-US')).toBe(
      'Reading one incident is about $0.0042, taking 3,000 tokens in and 600 out as a guess.',
    )
  })

  it('says how a model is cached and what that costs', () => {
    expect(cachingNote(HAIKU, 'en-US')).toBe(
      'Caches the fixed start of each prompt for 5 minutes: $0.01 to read it back and $0.125 to write it, per million tokens.',
    )
    expect(cachingNote(LUNA, 'en-US')).toContain('for 30 minutes')
    expect(cachingNote(NANO, 'en-US')).toBe(
      'Caches the start of a long prompt by itself at no extra charge: input it already had cached costs $0.02 per million tokens.',
    )
  })

  it('leaves out what a cached model has no price or time for, and says nothing for one that is not cached', () => {
    const bare = { ...HAIKU, cache_minutes: null, price: { ...HAIKU.price, cache_write: null } }

    expect(cachingNote(bare, 'en-US')).toBe(
      'Caches the fixed start of each prompt: $0.01 to read it back, per million tokens.',
    )
    expect(cachingNote(UNCACHED, 'en-US')).toBeNull()
    expect(
      cachingNote({ ...HAIKU, price: { ...HAIKU.price, cached_input: null } }, 'en-US'),
    ).toBeNull()
  })

  it('puts the price and the estimate under a model', () => {
    expect(priceNote(LUNA, 'en-US')).toBe(
      '$0.10 in · $0.50 out per million tokens · about $0.0006 an incident',
    )
  })

  it('says what a long prompt costs, if it costs more', () => {
    expect(longPromptNote(HAIKU.price, 'en-US')).toBe(
      'A prompt over 100,000 tokens costs $0.50 in and $2.50 out, and $0.05 for input already cached.',
    )
    expect(longPromptNote({ ...HAIKU.price, long_cached_input: null }, 'en-US')).toBe(
      'A prompt over 100,000 tokens costs $0.50 in and $2.50 out.',
    )
    expect(longPromptNote(SONNET.price, 'en-US')).toBeNull()
    expect(longPromptNote({ ...HAIKU.price, long_input: null }, 'en-US')).toBeNull()
  })

  it('lists the models to choose from with what each is for and costs', () => {
    expect(modelItems(anthropic(), 'en-US')).toEqual([
      {
        value: 'claude-haiku-5-5',
        title: 'Claude Haiku 5.5',
        props: {
          subtitle:
            'Fast and cheap: a good fit for reading every incident · $0.10 in · $0.50 out per million tokens · about $0.0006 an incident',
        },
      },
      expect.objectContaining({ value: 'claude-sonnet-5-5' }),
    ])
  })
})

describe('the form for a provider', () => {
  it('starts from what is kept, or from the default model', () => {
    expect(draftFrom(anthropic())).toEqual({
      model: 'claude-haiku-5-5',
      baseUrl: '',
      apiKey: '',
      plan: 'free',
    })
    expect(draftFrom(openai({ model: 'gpt-6-luna', configured: true }))).toEqual({
      model: 'gpt-6-luna',
      baseUrl: '',
      apiKey: '',
      plan: 'free',
    })
    expect(
      draftFrom(ollama({ configured: true, base_url: 'http://192.168.1.50:11434', model: 'a:1b' })),
    ).toEqual({ model: 'a:1b', baseUrl: 'http://192.168.1.50:11434', apiKey: '', plan: 'free' })
    expect(draftFrom(ollamaCloud())).toEqual({ model: '', baseUrl: '', apiKey: '', plan: 'free' })
  })

  it('starts from the plan the owner said the account has', () => {
    expect(draftFrom(ollamaCloud({ configured: true, plan: 'paid' })).plan).toBe('paid')
  })

  it('sends the key only if one was typed, and the address only if it takes one', () => {
    const draft = { model: 'claude-haiku-5-5', baseUrl: '', apiKey: '', plan: 'free' } as const

    expect(
      settingsFrom(anthropic(), { ...draft, model: ' claude-haiku-5-5 ', baseUrl: 'x' }),
    ).toEqual({ model: 'claude-haiku-5-5' })
    expect(settingsFrom(anthropic(), { ...draft, apiKey: ' sk-new ' })).toEqual({
      model: 'claude-haiku-5-5',
      api_key: 'sk-new',
    })
    expect(
      settingsFrom(ollama(), { ...draft, model: '', baseUrl: ' http://192.168.1.50:11434 ' }),
    ).toEqual({ model: '', base_url: 'http://192.168.1.50:11434' })
  })

  it('sends the plan only for a provider whose models depend on it', () => {
    const draft = { model: 'gpt-oss:20b', baseUrl: '', apiKey: '', plan: 'paid' } as const

    expect(settingsFrom(ollamaCloud(), draft)).toEqual({ model: 'gpt-oss:20b', plan: 'paid' })
    expect(settingsFrom(anthropic(), draft)).toEqual({ model: 'gpt-oss:20b' })
  })

  it('is changed when it is not kept yet, or differs from what is', () => {
    const kept = anthropic({ configured: true, key_saved: true, model: 'claude-haiku-5-5' })

    expect(isChanged(anthropic(), draftFrom(anthropic()))).toBe(true)
    expect(isChanged(kept, draftFrom(kept))).toBe(false)
    expect(isChanged(kept, { ...draftFrom(kept), model: 'claude-sonnet-5-5' })).toBe(true)
    expect(isChanged(kept, { ...draftFrom(kept), baseUrl: 'http://x' })).toBe(true)
    expect(isChanged(kept, { ...draftFrom(kept), apiKey: 'sk-new' })).toBe(true)
    expect(isChanged(kept, { ...draftFrom(kept), apiKey: '   ' })).toBe(false)
  })

  it('is changed when the plan differs, but only where the plan matters', () => {
    const cloud = ollamaCloud({ configured: true, key_saved: true, model: 'gpt-oss:20b' })
    const hosted = anthropic({ configured: true, key_saved: true, model: 'claude-haiku-5-5' })

    expect(isChanged(cloud, draftFrom(cloud))).toBe(false)
    expect(isChanged(cloud, { ...draftFrom(cloud), plan: 'paid' })).toBe(true)
    expect(isChanged(hosted, { ...draftFrom(hosted), plan: 'paid' })).toBe(false)
  })

  it('can be tested once it has what it needs', () => {
    expect(canTest(anthropic(), draftFrom(anthropic()))).toBe(false)
    expect(canTest(anthropic(), { ...draftFrom(anthropic()), apiKey: 'sk-a' })).toBe(true)
    expect(canTest(anthropic({ key_saved: true }), draftFrom(anthropic()))).toBe(true)
    expect(canTest(ollama(), draftFrom(ollama()))).toBe(false)
    expect(canTest(ollama(), { ...draftFrom(ollama()), baseUrl: ' http://10.0.0.5:11434' })).toBe(
      true,
    )
    expect(canTest(ollamaCloud(), draftFrom(ollamaCloud()))).toBe(false)
  })

  it('is ready to be asked when it has a model and, if it takes one, a key', () => {
    expect(isReady(anthropic())).toBe(false)
    expect(isReady(anthropic({ configured: true, model: 'claude-haiku-5-5' }))).toBe(false)
    expect(
      isReady(anthropic({ configured: true, model: 'claude-haiku-5-5', key_saved: true })),
    ).toBe(true)
    expect(isReady(ollama({ configured: true, model: '' }))).toBe(false)
    expect(isReady(ollama({ configured: true, model: 'a:1b' }))).toBe(true)
  })

  it('sorts what was wrong by field, keeping the first problem of each', () => {
    expect(
      problemsByField([
        { path: ['model'], message: 'Choose one of the models in the list.' },
        { path: ['api_key'], message: 'Enter the API key.' },
        { path: ['model'], message: 'Another.' },
        { path: [], message: 'No field.' },
      ]),
    ).toEqual({ model: 'Choose one of the models in the list.', api_key: 'Enter the API key.' })
  })

  it('names a field for the keyboard to move to', () => {
    expect(providerFieldId('ollama_cloud', 'api_key')).toBe('ollama_cloud-api_key')
  })
})

describe('the models an Ollama has', () => {
  const found = [
    {
      name: 'qwen3:8b',
      size: 5_200_000_000,
      family: 'qwen3',
      parameters: '8.2B',
      quantization: 'Q4_K_M',
    },
    { name: 'tiny:1b', size: null, family: null, parameters: null, quantization: null },
  ]
  // What Ollama's cloud lists: no details, and a size that is 0 for some.
  const hosted = [
    { name: 'glm-5.2', size: 0, family: null, parameters: null, quantization: null },
    {
      name: 'gpt-oss:120b',
      size: 65_290_180_781,
      family: 'gptoss',
      parameters: '116.8B',
      quantization: 'MXFP4',
    },
  ]

  it('says what each is on the owner’s computer, with how big it is', () => {
    expect(describeFound(found[0]!, 'local')).toBe('qwen3 · 8.2B · Q4_K_M · 4.8 GB')
    expect(describeFound(found[1]!, 'local')).toBe('')
  })

  it('leaves out a size of nothing', () => {
    expect(describeFound({ ...found[0]!, size: 0 }, 'local')).toBe('qwen3 · 8.2B · Q4_K_M')
  })

  it('says only what a model in Ollama’s cloud is, never how big: it is not on this computer', () => {
    expect(describeFound(hosted[0]!, 'cloud')).toBe('')
    expect(describeFound(hosted[1]!, 'cloud')).toBe('gptoss · 116.8B')
  })

  it('lists them to choose from', () => {
    expect(foundItems(ollama({ found }))).toEqual([
      {
        value: 'qwen3:8b',
        title: 'qwen3:8b',
        props: { subtitle: 'qwen3 · 8.2B · Q4_K_M · 4.8 GB' },
      },
      { value: 'tiny:1b', title: 'tiny:1b', props: { subtitle: '' } },
    ])
    expect(foundItems(ollama())).toEqual([])
  })

  it('lists those of Ollama’s cloud with no size', () => {
    expect(foundItems(ollamaCloud({ found: hosted })).map((item) => item.props.subtitle)).toEqual([
      '',
      'gptoss · 116.8B',
    ])
  })

  it('lists only the free ones for a free account, and all of them for a paid one', () => {
    const cloud = ollamaCloud({ found: hosted })

    expect(foundItems(cloud, 'free').map((item) => item.value)).toEqual(['gpt-oss:120b'])
    expect(foundItems(cloud, 'paid').map((item) => item.value)).toEqual(['glm-5.2', 'gpt-oss:120b'])
    expect(foundItems(cloud).map((item) => item.value)).toEqual(['glm-5.2', 'gpt-oss:120b'])
    // Only a provider with plans keeps models out.
    expect(foundItems(ollama({ found }), 'free')).toHaveLength(2)
  })

  it('keeps a model the free plan does not cover in the list when it is the one chosen', () => {
    const cloud = ollamaCloud({ found: hosted, model: 'glm-5.2' })

    expect(foundItems(cloud, 'free')[0]).toEqual({
      value: 'glm-5.2',
      title: 'glm-5.2',
      props: { subtitle: 'Needs a paid plan' },
    })
    expect(foundItems({ ...cloud, model: 'gpt-oss:120b' }, 'free', 'glm-5.2')).toHaveLength(2)
  })

  it('says how many models there are to choose from, and how many the plan keeps out', () => {
    const cloud = ollamaCloud({ found: hosted })

    expect(foundHint(ollama())).toBe('Press Fetch models to list the ones it has.')
    expect(foundHint(ollama({ found }))).toBe('2 models found: choose one.')
    expect(foundHint(cloud, 'free')).toBe('1 model found: choose one. 1 more need a paid plan.')
    expect(foundHint(cloud, 'paid')).toBe('2 models found: choose one.')
  })

  it('knows which providers have plans', () => {
    expect(hasPlans(ollamaCloud())).toBe(true)
    expect(hasPlans(ollama())).toBe(false)
    expect(hasPlans(anthropic())).toBe(false)
  })

  it('always lists the model that is kept, saying so when it was not found', () => {
    const kept = ollama({ model: 'llama3.2:3b' })

    expect(foundItems(kept)).toEqual([
      { value: 'llama3.2:3b', title: 'llama3.2:3b', props: { subtitle: 'The model you saved' } },
    ])
    expect(foundItems({ ...kept, found })[0]).toEqual({
      value: 'llama3.2:3b',
      title: 'llama3.2:3b',
      props: { subtitle: 'Saved, but not among the models it has now' },
    })
    expect(foundItems({ ...kept, model: 'tiny:1b', found })).toHaveLength(2)
  })
})

describe('what is said of the model and of AI', () => {
  it('puts what a model is for beside what it costs', () => {
    expect(modelHint(HAIKU, 'en-US')).toBe(
      'Fast and cheap: a good fit for reading every incident · $0.10 in · $0.50 out per million tokens',
    )
  })

  it('says AI is off unless it is on with a provider that is there', () => {
    const providers = [anthropic({ configured: true, model: 'claude-haiku-5-5' }), ollama()]

    expect(useNote({ enabled: false, provider: 'anthropic', providers })).toBe('Off')
    expect(useNote({ enabled: true, provider: null, providers })).toBe('Off')
    expect(useNote({ enabled: true, provider: 'gone', providers })).toBe('Off')
  })

  it('names the model it is on with: its label, else its name, else the provider', () => {
    const named = anthropic({ configured: true, model: 'claude-haiku-5-5' })
    const local = ollama({ configured: true, model: 'qwen3:8b' })
    const bare = ollama({ configured: true, model: null })

    expect(useNote({ enabled: true, provider: 'anthropic', providers: [named] })).toBe(
      'On · Claude Haiku 5.5',
    )
    expect(useNote({ enabled: true, provider: 'ollama', providers: [local] })).toBe('On · qwen3:8b')
    expect(useNote({ enabled: true, provider: 'ollama', providers: [bare] })).toBe(
      'On · Ollama (on your computer)',
    )
  })
})
