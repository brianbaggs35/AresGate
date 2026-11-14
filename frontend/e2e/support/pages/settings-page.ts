import type { Locator, Page } from '@playwright/test'

/** What the settings pages share: the heading, and the list (or tabs, on a phone) of pages. */
export class SettingsPage {
  readonly heading: Locator
  readonly nav: Locator
  readonly accountLink: Locator
  readonly signInsLink: Locator
  readonly activityLink: Locator
  readonly verdictsLink: Locator
  readonly noiseFiltersLink: Locator
  readonly threatDetectionLink: Locator
  readonly aiLink: Locator
  readonly agentsLink: Locator
  readonly dataLink: Locator
  readonly retentionLink: Locator

  constructor(private readonly page: Page) {
    this.heading = page.getByTestId('page-heading')
    this.nav = page.getByRole('navigation', { name: 'Settings' })
    this.accountLink = page.getByTestId('settings-nav-account')
    this.signInsLink = page.getByTestId('settings-nav-sign-ins')
    this.activityLink = page.getByTestId('settings-nav-activity')
    this.verdictsLink = page.getByTestId('settings-nav-verdicts')
    this.noiseFiltersLink = page.getByTestId('settings-nav-noise-filters')
    this.threatDetectionLink = page.getByTestId('settings-nav-threat-detection')
    this.aiLink = page.getByTestId('settings-nav-ai')
    this.agentsLink = page.getByTestId('settings-nav-agents')
    this.dataLink = page.getByTestId('settings-nav-data')
    this.retentionLink = page.getByTestId('settings-nav-retention')
  }

  async goto(): Promise<void> {
    await this.page.goto('/settings')
  }
}
