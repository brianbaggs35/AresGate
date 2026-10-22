import type { Locator, Page } from '@playwright/test'

/** What the signed-in person can see about their account and its recent activity. */
export class SecurityPage {
  readonly accountName: Locator
  readonly signOut: Locator
  /** Why signing out from this page failed. */
  readonly signOutError: Locator
  /** One entry for each thing that happened. */
  readonly activities: Locator
  readonly activityError: Locator
  readonly refresh: Locator

  constructor(private readonly page: Page) {
    this.accountName = page.getByTestId('account-name')
    this.signOut = page.getByTestId('sign-out-here')
    this.signOutError = page.getByTestId('sign-out-here-error')
    this.activities = page.getByTestId('activity')
    this.activityError = page.getByTestId('activity-error')
    this.refresh = page.getByTestId('refresh-activity')
  }

  async goto(): Promise<void> {
    await this.page.goto('/security')
  }
}
