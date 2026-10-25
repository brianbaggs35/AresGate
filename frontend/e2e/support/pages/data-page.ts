import type { Locator, Page } from '@playwright/test'

/** The settings page that says how much is stored and for how long it is kept. */
export class DataPage {
  readonly eventsCard: Locator
  readonly metricsCard: Locator
  /** The dialog that asks for a number of days, and its parts. */
  readonly dialog: Locator
  readonly dialogTitle: Locator
  readonly useDefault: Locator
  readonly useDays: Locator
  readonly days: Locator
  readonly save: Locator
  readonly cancel: Locator
  /** The question that comes before removing what is stored. */
  readonly confirmTitle: Locator

  constructor(private readonly page: Page) {
    this.eventsCard = page.getByTestId('events-retention-card')
    this.metricsCard = page.getByTestId('metrics-retention-card')
    this.dialog = page.getByTestId('retention-dialog')
    this.dialogTitle = page.getByTestId('retention-title')
    this.useDefault = page.getByTestId('retention-default').getByRole('radio')
    this.useDays = page.getByTestId('retention-custom').getByRole('radio')
    this.days = page.getByTestId('retention-days').locator('input')
    this.save = page.getByTestId('retention-save')
    this.cancel = page.getByTestId('retention-cancel')
    this.confirmTitle = page.getByTestId('confirm-title')
  }

  /** The row of one integration in a card. */
  source(card: Locator, name: string): Locator {
    return card.getByTestId('retention-source').filter({ hasText: name })
  }

  async goto(): Promise<void> {
    await this.page.goto('/settings/data')
  }
}
