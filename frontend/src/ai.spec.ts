import {
  ASSUMED_TOKENS,
  canTest,
  describeFound,
  describePrice,
  draftFrom,
  foundItems,
  formatUsd,
  incidentCost,
  isChanged,
  isReady,
  longPromptNote,
  modelItems,
  priceNote,
  problemsByField,
  providerFieldId,
  settingsFrom,
} from '@/ai'
import { HAIKU, LUNA, SONNET, anthropic, ollama, ollamaCloud, openai } from '@/test/ai'

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
    expect(describePrice(HAIKU.price, 'en-US')).toBe('$0.10 in, $0.50 out per million tokens')
  })

  it('works out a reading of one incident from the tokens it is assumed to take', () => {
    expect(ASSUMED_TOKENS).toEqual({ input: 3000, output: 600 })
    expect(incidentCost(HAIKU.price)).toBeCloseTo(0.0006)
    expect(incidentCost(SONNET.price)).toBeCloseTo(0.012)
  })

  it('puts the price and the estimate under a model', () => {
    expect(priceNote(LUNA, 'en-US')).toBe(
      '$0.10 in, $0.50 out per million tokens · about $0.0006 an incident',
    )
  })

  it('says what a long prompt costs, if it costs more', () => {
    expect(longPromptNote(HAIKU.price, 'en-US')).toBe(
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
            'Fast and cheap: a good fit for reading every incident · $0.10 in, $0.50 out per million tokens · about $0.0006 an incident',
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
    })
    expect(draftFrom(openai({ model: 'gpt-6-luna', configured: true }))).toEqual({
      model: 'gpt-6-luna',
      baseUrl: '',
      apiKey: '',
    })
    expect(
      draftFrom(ollama({ configured: true, base_url: 'http://192.168.1.50:11434', model: 'a:1b' })),
    ).toEqual({ model: 'a:1b', baseUrl: 'http://192.168.1.50:11434', apiKey: '' })
    expect(draftFrom(ollamaCloud())).toEqual({ model: '', baseUrl: '', apiKey: '' })
  })

  it('sends the key only if one was typed, and the address only if it takes one', () => {
    expect(
      settingsFrom(anthropic(), { model: ' claude-haiku-5-5 ', baseUrl: 'x', apiKey: '' }),
    ).toEqual({
      model: 'claude-haiku-5-5',
    })
    expect(
      settingsFrom(anthropic(), { model: 'claude-haiku-5-5', baseUrl: '', apiKey: ' sk-new ' }),
    ).toEqual({ model: 'claude-haiku-5-5', api_key: 'sk-new' })
    expect(
      settingsFrom(ollama(), { model: '', baseUrl: ' http://192.168.1.50:11434 ', apiKey: '' }),
    ).toEqual({ model: '', base_url: 'http://192.168.1.50:11434' })
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

  it('says what each is', () => {
    expect(describeFound(found[0]!)).toBe('qwen3 · 8.2B · Q4_K_M · 4.8 GB')
    expect(describeFound(found[1]!)).toBe('')
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
})
