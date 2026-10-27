import type { Problem } from '@/api/client'
import type { AiProvider, FoundModel, ModelChoice, Price, ProviderSettings } from '@/api/ai'
import { formatBytes, formatCount } from '@/format'

/** What reading one incident is assumed to take, in tokens: the incident and what surrounds it
 * go in, and a class, a confidence, a story and what to check come out. `fixed` is the part of
 * what goes in that is the same every time (the analyst's instructions), which a provider can
 * keep cached. It is a round guess to make prices comparable, not a measurement; the usage page
 * shows what was really used. */
export const ASSUMED_TOKENS = { input: 3000, fixed: 1500, output: 600 } as const

/** US dollars, with as many decimals as the price needs: $2.00, $0.10, $0.075, $0.0006. */
export function formatUsd(value: number, locale?: string): string {
  if (value > 0 && value < 0.0001) return 'less than $0.0001'
  return value.toLocaleString(locale, {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 2,
    maximumFractionDigits: 4,
  })
}

/** What a price is, in a line: "$0.10 in, $0.50 out per million tokens". */
export function describePrice(price: Price, locale?: string): string {
  return `${formatUsd(price.input, locale)} in, ${formatUsd(price.output, locale)} out per million tokens`
}

/** What reading one incident costs at a price, by the assumed tokens. With `cached`, the fixed
 * part of what goes in is read from the provider's cache. */
export function incidentCost(price: Price, cached = false): number {
  const { input, fixed, output } = ASSUMED_TOKENS
  const fromCache = cached ? fixed : 0
  const cachedRate = price.cached_input ?? price.input
  return (
    ((input - fromCache) * price.input + fromCache * cachedRate + output * price.output) / 1_000_000
  )
}

/** What reading one incident costs once the provider has the fixed part cached, or null for a
 * model that doesn't cache or has no price for reading from the cache. */
export function cachedIncidentCost(model: ModelChoice): number | null {
  if (model.caching === 'none' || model.price.cached_input === null) return null
  return incidentCost(model.price, true)
}

/** What reading one incident costs with a model, by the assumed tokens, and what it costs once
 * the cache is warm if the model caches. */
export function estimateNote(model: ModelChoice, locale?: string): string {
  const { input, fixed, output } = ASSUMED_TOKENS
  const plain = `Reading one incident is about ${formatUsd(incidentCost(model.price), locale)}, taking ${formatCount(input, locale)} tokens in and ${formatCount(output, locale)} out as a guess.`
  const warm = cachedIncidentCost(model)
  if (warm === null) return plain
  return `${plain} With the cache warm, so that the ${formatCount(fixed, locale)} tokens of instructions are read from it, about ${formatUsd(warm, locale)}.`
}

/** How a model is cached and what that costs, or null if it isn't. */
export function cachingNote(model: ModelChoice, locale?: string): string | null {
  const { cached_input: read, cache_write: write } = model.price
  if (model.caching === 'none' || read === null) return null
  if (model.caching === 'automatic')
    return `Caches the start of a long prompt by itself at no extra charge: input it already had cached costs ${formatUsd(read, locale)} per million tokens.`
  const kept = model.cache_minutes === null ? '' : ` for ${model.cache_minutes} minutes`
  const writing = write === null ? '' : ` and ${formatUsd(write, locale)} to write it`
  return `Caches the fixed start of each prompt${kept}: ${formatUsd(read, locale)} to read it back${writing}, per million tokens.`
}

/** The line under a model that says what it costs, to choose by. */
export function priceNote(model: ModelChoice, locale?: string): string {
  return `${describePrice(model.price, locale)} · about ${formatUsd(incidentCost(model.price), locale)} an incident`
}

/** Prices that depend on the size of the prompt: what it costs past the threshold. */
export function longPromptNote(price: Price, locale?: string): string | null {
  if (price.long_over === null || price.long_input === null || price.long_output === null)
    return null
  const cached =
    price.long_cached_input === null
      ? ''
      : `, and ${formatUsd(price.long_cached_input, locale)} for input already cached`
  return `A prompt over ${price.long_over.toLocaleString(locale)} tokens costs ${formatUsd(price.long_input, locale)} in and ${formatUsd(price.long_output, locale)} out${cached}.`
}

/** What is being filled in for a provider, as the form holds it. */
export interface ProviderDraft {
  model: string
  baseUrl: string
  /** Only what was typed: a key that is kept is never here. */
  apiKey: string
}

/** The form for a provider, starting from how it is saved. A model that was never chosen is the
 * default one, for the providers that have one. */
export function draftFrom(provider: AiProvider): ProviderDraft {
  return {
    model: provider.model ?? provider.default_model ?? '',
    baseUrl: provider.base_url ?? '',
    apiKey: '',
  }
}

/** What to send: the address only for a provider that takes one, and the key only if one was
 * typed, since the one that is kept stays. */
export function settingsFrom(provider: AiProvider, draft: ProviderDraft): ProviderSettings {
  const settings: ProviderSettings = { model: draft.model.trim() }
  if (provider.takes_url) settings.base_url = draft.baseUrl.trim()
  const typed = draft.apiKey.trim()
  if (typed !== '') settings.api_key = typed
  return settings
}

/** Whether the form differs from what is saved, so a test has to save it first. */
export function isChanged(provider: AiProvider, draft: ProviderDraft): boolean {
  if (!provider.configured) return true
  const saved = draftFrom(provider)
  return (
    draft.model.trim() !== saved.model ||
    draft.baseUrl.trim() !== saved.baseUrl ||
    draft.apiKey.trim() !== ''
  )
}

/** Whether there is enough to test: the address of one on the owner's computer, and the key of
 * one that takes a key (typed now or kept). */
export function canTest(provider: AiProvider, draft: ProviderDraft): boolean {
  if (provider.takes_url && draft.baseUrl.trim() === '') return false
  return !provider.needs_key || provider.key_saved || draft.apiKey.trim() !== ''
}

/** What was wrong with each field of a save, by field name. The first problem for a field is the
 * one kept. */
export function problemsByField(problems: readonly Problem[]): Record<string, string> {
  const byField: Record<string, string> = {}
  for (const { path, message } of problems) {
    const field = path[0]
    if (field !== undefined && !(field in byField)) byField[field] = message
  }
  return byField
}

/** The line under a model an Ollama has: what it is and how big. */
export function describeFound(model: FoundModel): string {
  const parts = [
    model.family,
    model.parameters,
    model.quantization,
    model.size === null ? null : formatBytes(model.size),
  ]
  return parts.filter((part) => part !== null).join(' · ')
}

/** Whether a provider can be asked: it is set up, has a model and, if it takes a key, has one. */
export function isReady(provider: AiProvider): provider is AiProvider & { model: string } {
  return provider.configured && !!provider.model && (!provider.needs_key || provider.key_saved)
}

/** The models a hosted provider offers, to choose from: the name, and under it what it is for
 * and what it costs. */
export function modelItems(provider: AiProvider, locale?: string) {
  return provider.models.map((model) => ({
    value: model.id,
    title: model.label,
    props: { subtitle: `${model.note} · ${priceNote(model, locale)}` },
  }))
}

/** The models an Ollama said it has, to choose from. */
export function foundItems(provider: AiProvider) {
  return provider.found.map((model) => ({
    value: model.name,
    title: model.name,
    props: { subtitle: describeFound(model) },
  }))
}

/** The fields of a provider in the order they are on the page, which is where a problem moves
 * the keyboard to. */
export const FIELD_ORDER = ['base_url', 'api_key', 'model'] as const

/** The id of a provider's field, which is what a problem with it moves the keyboard to. */
export const providerFieldId = (provider: string, field: string) => `${provider}-${field}`
