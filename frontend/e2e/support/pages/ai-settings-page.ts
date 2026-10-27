import type { Locator, Page } from '@playwright/test'

/** The settings page for AI: whether it is used, and a card for each provider that can be asked. */
export class AiSettingsPage {
  readonly useCard: Locator
  /** The switch that turns AI on, and the choice of which provider it asks. */
  readonly enabled: Locator
  readonly provider: Locator
  readonly useFailure: Locator
  readonly cards: Locator
  /** Shown when the page could not be loaded. */
  readonly error: Locator

  constructor(private readonly page: Page) {
    this.useCard = page.getByTestId('ai-use-card')
    this.enabled = page.getByTestId('ai-enabled').getByRole('checkbox')
    this.provider = page.getByTestId('ai-provider')
    this.useFailure = page.getByTestId('ai-use-failure')
    this.cards = page.getByRole('heading', { level: 2 })
    this.error = page.getByTestId('ai-error')
  }

  /** The card of one provider, by its key such as `anthropic` or `ollama_cloud`. */
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

  /** Chooses an option of a provider's model list (a hosted provider's, or an Ollama's models
   * that were fetched). */
  async chooseModel(key: string, option: string | RegExp): Promise<void> {
    await this.model(key).locator('.v-field').click()
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
