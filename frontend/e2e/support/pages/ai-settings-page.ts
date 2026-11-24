import { expect, type Locator, type Page } from '@playwright/test'

/** The settings page for AI: a card to choose where it runs, and the settings of the one chosen. */
export class AiSettingsPage {
  /** The switch that turns AI on, for the provider that is chosen. */
  readonly enabled: Locator
  /** "Off", or "On" with the model that is asked. */
  readonly state: Locator
  readonly useHint: Locator
  readonly useFailure: Locator
  readonly headings: Locator
  /** What is said while no provider is chosen yet. */
  readonly choosePrompt: Locator
  /** Shown when the page could not be loaded. */
  readonly error: Locator

  constructor(private readonly page: Page) {
    this.enabled = page.getByTestId('ai-enabled').getByRole('checkbox')
    this.state = page.getByTestId('ai-state')
    this.useHint = page.getByTestId('ai-use-hint')
    this.useFailure = page.getByTestId('ai-use-failure')
    this.headings = page.getByRole('heading', { level: 2 })
    this.choosePrompt = page.getByTestId('ai-choose')
    this.error = page.getByTestId('ai-error')
  }

  /**
   * Turns AI on and waits until the switch says so. The switch shows what AresGate last answered,
   * so it stays off until the answer comes: `check()` would fail, as it looks right after the click.
   */
  async turnOn(): Promise<void> {
    await this.enabled.click()
    await expect(this.enabled).toBeChecked()
  }

  /** The radio button of one level of what the provider is shown: strict, balanced or local. */
  level(key: string): Locator {
    return this.page.getByTestId(`privacy-${key}`).getByRole('radio')
  }

  /** What a provider would read of the same event at a level. */
  example(key: string): Locator {
    return this.page.getByTestId(`privacy-example-${key}`)
  }

  /** The line under the levels that says why one can't be chosen. */
  get privacyNote(): Locator {
    return this.page.getByTestId('privacy-note')
  }

  /** The option of one provider in the choice at the top, by its key such as `anthropic` or
   * `ollama_cloud`. */
  option(key: string): Locator {
    return this.page.getByTestId(`pick-${key}`)
  }

  /** Chooses a provider, which shows its settings. */
  async choose(key: string): Promise<void> {
    await this.option(key).click()
    await this.card(key).waitFor()
  }

  /** The settings of the provider that is chosen. */
  card(key: string): Locator {
    return this.page.getByTestId(`provider-${key}`)
  }

  /** What is inside a provider's card. */
  status(key: string): Locator {
    return this.card(key).getByTestId('provider-status')
  }

  apiKey(key: string): Locator {
    return this.card(key).getByTestId('provider-key').locator('input')
  }

  address(key: string): Locator {
    return this.card(key).getByTestId('provider-url').locator('input')
  }

  model(key: string): Locator {
    return this.card(key).getByTestId('provider-model')
  }

  /** The box of the model field that is typed in and clicked, not the hidden one with the value. */
  modelInput(key: string): Locator {
    return this.model(key).getByRole('combobox', { name: 'Model' })
  }

  price(key: string): Locator {
    return this.card(key).getByTestId('provider-price')
  }

  /** The choice between a free and a paid Ollama account. */
  plan(key: string): Locator {
    return this.card(key).getByTestId('provider-plan')
  }

  planOption(key: string, plan: 'free' | 'paid'): Locator {
    return this.card(key).getByTestId(`provider-plan-${plan}`).getByRole('radio')
  }

  freeModels(key: string): Locator {
    return this.card(key).getByTestId('provider-free-models')
  }

  notice(key: string): Locator {
    return this.card(key).getByTestId('provider-notice')
  }

  /** The note that a model has no price, shown for a model that isn't in AresGate's list. */
  unlisted(key: string): Locator {
    return this.card(key).getByTestId('provider-unlisted')
  }

  failure(key: string): Locator {
    return this.card(key).getByTestId('provider-failure')
  }

  lastError(key: string): Locator {
    return this.card(key).getByTestId('provider-last-error')
  }

  save(key: string): Locator {
    return this.card(key).getByTestId('provider-save')
  }

  test(key: string): Locator {
    return this.card(key).getByTestId('provider-test')
  }

  fetchModels(key: string): Locator {
    return this.card(key).getByTestId('provider-models-fetch')
  }

  remove(key: string): Locator {
    return this.card(key).getByTestId('provider-remove')
  }

  /** Opens a provider's model list (a hosted provider's, or an Ollama's models that were
   * fetched). */
  async openModels(key: string): Promise<void> {
    await this.model(key).locator('.v-field').click()
  }

  /** The models the open list offers. */
  get modelOptions(): Locator {
    return this.page.getByRole('option')
  }

  /** Chooses an option of a provider's model list. */
  async chooseModel(key: string, option: string | RegExp): Promise<void> {
    await this.openModels(key)
    await this.page.getByRole('option', { name: option }).click()
  }

  get confirmTitle(): Locator {
    return this.page.getByTestId('confirm-title')
  }

  get confirm(): Locator {
    return this.page.getByTestId('confirm-accept')
  }

  async goto(): Promise<void> {
    await this.page.goto('/settings/ai')
  }

  // The Clearing card: what the AI may clear as a false positive, and on what terms.

  get clearing(): Locator {
    return this.page.getByTestId('clearing-card')
  }

  /** The radio button of one mode: off, suggest or automatic. */
  mode(key: 'off' | 'suggest' | 'automatic'): Locator {
    return this.page.getByTestId(`clearing-mode-${key}`).getByRole('radio')
  }

  /** One way of being careful: careful, balanced or thorough. */
  preset(key: 'careful' | 'balanced' | 'thorough'): Locator {
    return this.page.getByTestId(`clearing-preset-${key}`)
  }

  /** What the chosen way of being careful comes to, in words. */
  get presetWords(): Locator {
    return this.page.getByTestId('clearing-preset-words')
  }

  /** "80% sure". */
  get minimum(): Locator {
    return this.page.getByTestId('clearing-minimum')
  }

  get minimumSlider(): Locator {
    return this.page.getByRole('slider', {
      name: 'How sure the AI has to be to clear an incident',
    })
  }

  /** The checkbox of one kind of reading: noise, probe or unclear. */
  kind(key: 'noise' | 'probe' | 'unclear'): Locator {
    return this.page.getByTestId(`clearing-kind-${key}`).getByRole('checkbox')
  }

  /** The choice of how serious an incident the AI may clear: low, medium or high. */
  ceiling(key: 'low' | 'medium' | 'high'): Locator {
    return this.page.getByTestId(`clearing-ceiling-${key}`)
  }

  get ceilingWords(): Locator {
    return this.page.getByTestId('clearing-ceiling-words')
  }

  /** The most it clears a day, shown when it clears by itself. */
  get cap(): Locator {
    return this.page.getByTestId('clearing-cap').locator('input')
  }

  /** What the settings would have cleared of what the AI read in the last 7 days. */
  get clearingPreview(): Locator {
    return this.page.getByTestId('clearing-preview')
  }

  get clearingSave(): Locator {
    return this.page.getByTestId('clearing-save')
  }

  get clearingSaved(): Locator {
    return this.page.getByTestId('clearing-saved')
  }

  get clearingDiscard(): Locator {
    return this.page.getByTestId('clearing-discard')
  }
}
