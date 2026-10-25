import type { Locator, Page } from '@playwright/test'

/** What the settings pages share: the heading, and the list (or tabs, on a phone) of pages. */
export class SettingsPage {
  readonly heading: Locator
  readonly nav: Locator
  readonly accountLink: Locator
  readonly signInsLink: Locator
  readonly activityLink: Locator
  readonly dataLink: Locator

  constructor(private readonly page: Page) {
    this.heading = page.getByTestId('page-heading')
    this.nav = page.getByRole('navigation', { name: 'Settings' })
    this.accountLink = page.getByTestId('settings-nav-account')
    this.signInsLink = page.getByTestId('settings-nav-sign-ins')
    this.activityLink = page.getByTestId('settings-nav-activity')
    this.dataLink = page.getByTestId('settings-nav-data')
  }

  async goto(): Promise<void> {
    await this.page.goto('/settings')
  }
}
