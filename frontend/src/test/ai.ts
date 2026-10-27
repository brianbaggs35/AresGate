import type { Ai, AiProvider, ModelChoice } from '@/api/ai'

/** AI providers as the API describes them, for tests of pages that show them. */

export const HAIKU: ModelChoice = {
  id: 'claude-haiku-5-5',
  label: 'Claude Haiku 5.5',
  note: 'Fast and cheap: a good fit for reading every incident',
  price: {
    input: 0.1,
    output: 0.5,
    cached_input: 0.01,
    cache_write: 0.125,
    long_over: 100_000,
    long_input: 0.5,
    long_output: 2.5,
    long_cached_input: 0.05,
    long_cache_write: 0.625,
  },
  caching: 'marked',
  cache_minutes: 5,
  deprecated: false,
}

export const SONNET: ModelChoice = {
  id: 'claude-sonnet-5-5',
  label: 'Claude Sonnet 5.5',
  note: 'Better reasoning for harder incidents',
  price: {
    input: 2,
    output: 10,
    cached_input: 0.1,
    cache_write: 2.5,
    long_over: null,
    long_input: null,
    long_output: null,
    long_cached_input: null,
    long_cache_write: null,
  },
  caching: 'marked',
  cache_minutes: 5,
  deprecated: false,
}

export const LUNA: ModelChoice = {
  id: 'gpt-6-luna',
  label: 'GPT-6 Luna',
  note: 'Fast and cheap: a good fit for reading every incident',
  price: {
    input: 0.1,
    output: 0.5,
    cached_input: 0.01,
    cache_write: 0.125,
    long_over: 272_000,
    long_input: 0.2,
    long_output: 0.75,
    long_cached_input: 0.02,
    long_cache_write: 0.25,
  },
  caching: 'marked',
  cache_minutes: 30,
  deprecated: false,
}

/** An older model: cached by the provider by itself, and being retired. */
export const NANO: ModelChoice = {
  id: 'gpt-5.4-nano',
  label: 'GPT-5.4 nano',
  note: 'Small and cheap, from the previous generation. OpenAI lists it as deprecated',
  price: {
    input: 0.2,
    output: 1.25,
    cached_input: 0.02,
    cache_write: null,
    long_over: null,
    long_input: null,
    long_output: null,
    long_cached_input: null,
    long_cache_write: null,
  },
  caching: 'automatic',
  cache_minutes: null,
  deprecated: true,
}

/** A model that isn't cached. */
export const UNCACHED: ModelChoice = {
  id: 'plain-model',
  label: 'A plain model',
  note: 'No cache',
  price: {
    input: 1,
    output: 2,
    cached_input: null,
    cache_write: null,
    long_over: null,
    long_input: null,
    long_output: null,
    long_cached_input: null,
    long_cache_write: null,
  },
  caching: 'none',
  cache_minutes: null,
  deprecated: false,
}

const NOT_SET_UP: Pick<
  AiProvider,
  | 'configured'
  | 'base_url'
  | 'model'
  | 'key_saved'
  | 'status'
  | 'last_attempt_at'
  | 'last_success_at'
  | 'last_error'
  | 'found'
  | 'found_at'
  | 'free_models'
  | 'plan'
> = {
  configured: false,
  base_url: null,
  model: null,
  key_saved: false,
  status: 'not_connected',
  last_attempt_at: null,
  last_success_at: null,
  last_error: null,
  found: [],
  found_at: null,
  free_models: [],
  plan: null,
}

export const anthropic = (overrides: Partial<AiProvider> = {}): AiProvider => ({
  key: 'anthropic',
  label: 'Anthropic',
  summary: 'Claude, with an API key from the Claude Console.',
  kind: 'hosted',
  needs_key: true,
  takes_url: false,
  key_url: 'https://platform.claude.com/settings/keys',
  pricing_url: 'https://platform.claude.com/docs/en/about-claude/pricing',
  models_url: 'https://platform.claude.com/docs/en/about-claude/models/overview',
  models: [HAIKU, SONNET],
  default_model: HAIKU.id,
  ...NOT_SET_UP,
  ...overrides,
})

export const openai = (overrides: Partial<AiProvider> = {}): AiProvider => ({
  key: 'openai',
  label: 'OpenAI',
  summary: 'GPT, with an API key from the OpenAI platform.',
  kind: 'hosted',
  needs_key: true,
  takes_url: false,
  key_url: 'https://platform.openai.com/api-keys',
  pricing_url: 'https://developers.openai.com/api/docs/pricing',
  models_url: 'https://developers.openai.com/api/docs/models',
  models: [LUNA, NANO],
  default_model: LUNA.id,
  ...NOT_SET_UP,
  ...overrides,
})

export const ollama = (overrides: Partial<AiProvider> = {}): AiProvider => ({
  key: 'ollama',
  label: 'Ollama (on your computer)',
  summary:
    'Runs models on your own hardware, so nothing leaves your network and nothing is billed.',
  kind: 'local',
  needs_key: false,
  takes_url: true,
  key_url: null,
  pricing_url: null,
  models_url: 'https://docs.ollama.com/api/tags',
  models: [],
  default_model: null,
  ...NOT_SET_UP,
  ...overrides,
})

/** The cloud models free usage covers. */
export const FREE_MODELS = ['gemma4:31b', 'gpt-oss:120b', 'gpt-oss:20b']

export const ollamaCloud = (overrides: Partial<AiProvider> = {}): AiProvider => ({
  key: 'ollama_cloud',
  label: 'Ollama Cloud',
  summary: "Ollama's hosted models (ollama.com), with a key from your Ollama account.",
  kind: 'cloud',
  needs_key: true,
  takes_url: false,
  key_url: 'https://ollama.com/settings/keys',
  pricing_url: null,
  models_url: 'https://docs.ollama.com/cloud',
  models: [],
  default_model: null,
  ...NOT_SET_UP,
  free_models: FREE_MODELS,
  ...overrides,
})

export const ai = (overrides: Partial<Ai> = {}): Ai => ({
  enabled: false,
  provider: null,
  priced_as_of: '2026-10-27',
  free_models_as_of: '2026-10-27',
  providers: [ollama(), ollamaCloud(), anthropic(), openai()],
  ...overrides,
})
