import type { Locator, Page } from '@playwright/test'

/** The overview, which is the landing page. */
export class OverviewPage {
  readonly card: Locator
  readonly apiStatus: Locator
  readonly databaseStatus: Locator
  readonly refresh: Locator

  constructor(private readonly page: Page) {
    this.card = page.getByTestId('status-card')
    this.apiStatus = page.getByTestId('api-status')
    this.databaseStatus = page.getByTestId('database-status')
    this.refresh = page.getByTestId('refresh')
  }

  async goto(): Promise<void> {
    await this.page.goto('/')
  }
}
