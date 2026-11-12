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
  /** The search above the cards. */
  readonly search: Locator
  /** What the list says when nothing matches the search and the kind. */
  readonly none: Locator
  readonly clear: Locator

  constructor(private readonly page: Page) {
    this.heading = page.getByRole('heading', { level: 1, name: 'Integrations' })
    this.count = page.getByTestId('integrations-count')
    this.names = page.getByTestId('integration-name')
    this.loadError = page.getByTestId('integrations-error')
    this.retry = page.getByTestId('integrations-retry')
    this.search = page.getByTestId('integrations-search').getByRole('searchbox')
    this.none = page.getByTestId('integrations-none')
    this.clear = page.getByTestId('integrations-clear')
  }

  async goto(): Promise<void> {
    await this.page.goto('/integrations')
  }

  /** The button that shows the integrations of one kind, or all of them ("All"). */
  kind(name: string): Locator {
    return this.page.getByTestId('integrations-kinds').getByRole('button', { name })
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
