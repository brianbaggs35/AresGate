import type { Locator, Page } from '@playwright/test'

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
}
