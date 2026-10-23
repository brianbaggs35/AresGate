import type { Locator, Page } from '@playwright/test'

/** The settings page that lists what happened on the account lately. */
export class ActivityPage {
  /** One entry for each thing that happened, newest first. */
  readonly entries: Locator
  readonly noActivity: Locator
  readonly error: Locator
  readonly refresh: Locator

  constructor(private readonly page: Page) {
    this.entries = page.getByTestId('activity')
    this.noActivity = page.getByTestId('no-activity')
    this.error = page.getByTestId('activity-error')
    this.refresh = page.getByTestId('refresh-activity')
  }

  async goto(): Promise<void> {
    await this.page.goto('/settings/activity')
  }
}
