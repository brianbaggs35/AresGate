import { apiDelete, apiGet, apiPost, apiPut } from '@/api/client'
import type { Status } from '@/api/integrations'

/** Where a provider runs: the internet with an API key, a computer of the owner's, or the
 * internet as Ollama's own cloud. */
export type ProviderKind = 'hosted' | 'local' | 'cloud'

/** What a model costs, in US dollars per million tokens. */
export interface Price {
  input: number
  output: number
  /** What input costs when the provider already had it cached, if it says. */
  cached_input: number | null
  /** What input costs to have the provider cache it, for the model's `cache_minutes`. */
  cache_write: number | null
  /** Some models cost more for a prompt longer than this many tokens, and what that costs. */
  long_over: number | null
  long_input: number | null
  long_output: number | null
  long_cached_input: number | null
  long_cache_write: number | null
}

/** How the start of a prompt is cached: AresGate marks where it ends and the provider keeps it
 * for a while (`marked`), the provider does it by itself (`automatic`), or it isn't cached. */
export type Caching = 'none' | 'automatic' | 'marked'

/** A model that can be chosen, by the name the provider's API knows it by. */
export interface ModelChoice {
  id: string
  label: string
  /** What it is for, in a few words. */
  note: string
  price: Price
  caching: Caching
  /** How long the provider keeps what it was asked to cache, for a model that is marked. */
  cache_minutes: number | null
  /** The provider has said it will retire the model. */
  deprecated: boolean
}

/** A model an Ollama said it has. */
export interface FoundModel {
  name: string
  size: number | null
  family: string | null
  parameters: string | null
  quantization: string | null
}

/** A provider AresGate can ask, with what it offers and how it is set up. A key that is kept is
 * never sent back, only that one is kept. */
export interface AiProvider {
  key: string
  label: string
  summary: string
  kind: ProviderKind
  needs_key: boolean
  takes_url: boolean
  key_url: string | null
  pricing_url: string | null
  models_url: string
  /** The models it offers: none for one whose models are whatever it has. */
  models: ModelChoice[]
  default_model: string | null
  configured: boolean
  base_url: string | null
  model: string | null
  key_saved: boolean
  status: Status
  last_attempt_at: string | null
  last_success_at: string | null
  last_error: string | null
  found: FoundModel[]
  found_at: string | null
}

export interface Ai {
  enabled: boolean
  /** The provider that is asked. */
  provider: string | null
  /** When the prices were read from the providers' pages. */
  priced_as_of: string
  providers: AiProvider[]
}

/** How to reach a provider. A key left out keeps the one that is kept. */
export interface ProviderSettings {
  model: string
  base_url?: string | null
  api_key?: string
}

/** How a test or a look for models went, and the provider as it is now. */
export interface AiCheck {
  ok: boolean
  message: string
  provider: AiProvider
}

export function fetchAi(): Promise<Ai> {
  return apiGet<Ai>('/ai')
}

/** Keeps how to reach a provider, replacing what was kept. It is not tested yet. */
export function saveProvider(
  key: string,
  settings: ProviderSettings,
  csrfToken: string,
): Promise<AiProvider> {
  return apiPut<AiProvider>(`/ai/providers/${key}`, settings, csrfToken)
}

/** Forgets a provider and its key. */
export function removeProvider(key: string, csrfToken: string): Promise<undefined> {
  return apiDelete(`/ai/providers/${key}`, csrfToken)
}

/** Asks a provider for the least that proves the key, the model and the address work. */
export function testProvider(key: string, csrfToken: string): Promise<AiCheck> {
  return apiPost<AiCheck>(`/ai/providers/${key}/test`, undefined, csrfToken)
}

/** Asks an Ollama which models it has. */
export function fetchProviderModels(key: string, csrfToken: string): Promise<AiCheck> {
  return apiPost<AiCheck>(`/ai/providers/${key}/models`, undefined, csrfToken)
}

/** Turns AI on or off, and says which provider it asks. */
export function useAi(
  choice: { enabled: boolean; provider: string | null },
  csrfToken: string,
): Promise<Ai> {
  return apiPut<Ai>('/ai/use', choice, csrfToken)
}
