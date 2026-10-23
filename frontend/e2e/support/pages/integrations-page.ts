import type { Locator, Page } from '@playwright/test'

/** The list of integrations: a card for each, which opens the integration's own page. */
export class IntegrationsPage {
  readonly heading: Locator
  /** "1 of 4 set up". */
  readonly count: Locator
  /** The name on each card, in order. */
  readonly names: Locator
  readonly loadError: Locator
  readonly retry: Locator

  constructor(private readonly page: Page) {
    this.heading = page.getByRole('heading', { level: 1, name: 'Integrations' })
    this.count = page.getByTestId('integrations-count')
    this.names = page.getByTestId('integration-name')
    this.loadError = page.getByTestId('integrations-error')
    this.retry = page.getByTestId('integrations-retry')
  }

  async goto(): Promise<void> {
    await this.page.goto('/integrations')
  }

  /** An integration's card, which is a link to its page. */
  card(key: string): Locator {
    return this.page.getByTestId(`integration-${key}`)
  }

  status(key: string): Locator {
    return this.card(key).getByTestId('status')
  }

  lastCall(key: string): Locator {
    return this.card(key).getByTestId('integration-last-call')
  }

  /** The services listed on a card. */
  services(key: string): Locator {
    return this.card(key).getByTestId('integration-service')
  }
}
