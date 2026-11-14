import type { Locator, Page } from '@playwright/test'

/** The settings page for how long data is kept and how big the database may get. */
export class RetentionSettingsPage {
  readonly managed: Locator
  readonly builtIn: Locator
  readonly timeCard: Locator
  readonly keepForDays: Locator
  readonly keepForever: Locator
  readonly days: Locator
  readonly limited: Locator
  readonly quota: Locator
  readonly save: Locator
  readonly discard: Locator
  readonly saved: Locator
  readonly usageTotal: Locator

  constructor(private readonly page: Page) {
    this.managed = page.getByTestId('retention-managed').getByRole('checkbox')
    this.builtIn = page.getByTestId('retention-built-in')
    this.timeCard = page.getByTestId('retention-time-card')
    this.keepForDays = page.getByTestId('retention-mode-time').getByRole('radio')
    this.keepForever = page.getByTestId('retention-mode-forever').getByRole('radio')
    this.days = page.getByTestId('retention-days').locator('input')
    this.limited = page.getByTestId('retention-limited').getByRole('checkbox')
    this.quota = page.getByTestId('retention-quota').locator('input')
    this.save = page.getByTestId('retention-save')
    this.discard = page.getByTestId('retention-discard')
    this.saved = page.getByTestId('retention-saved')
    this.usageTotal = page.getByTestId('retention-usage-total')
  }

  async goto(): Promise<void> {
    await this.page.goto('/settings/retention')
  }
}
