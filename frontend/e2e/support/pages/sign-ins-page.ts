import type { Locator, Page } from '@playwright/test'

/** The settings page that lists the browsers signed in to the account, and ends them. */
export class SignInsPage {
  readonly card: Locator
  readonly signIns: Locator
  readonly names: Locator
  readonly details: Locator
  /** The badge on the browser being used. */
  readonly thisBrowser: Locator
  /** Signs out one browser. The browser being used has none. */
  readonly endButtons: Locator
  readonly endOthers: Locator
  /** What came of a change: that it was done, or why not. */
  readonly notice: Locator
  readonly failure: Locator
  readonly loadError: Locator
  readonly retry: Locator
  /** The question asked before a browser is signed out. */
  readonly confirmTitle: Locator
  readonly confirm: Locator
  readonly cancel: Locator

  constructor(private readonly page: Page) {
    this.card = page.getByTestId('sign-ins-card')
    this.signIns = page.getByTestId('sign-in')
    this.names = page.getByTestId('sign-in-name')
    this.details = page.getByTestId('sign-in-details')
    this.thisBrowser = page.getByTestId('sign-in-current')
    this.endButtons = page.getByTestId('end-sign-in')
    this.endOthers = page.getByTestId('end-others')
    this.notice = page.getByTestId('sign-ins-notice')
    this.failure = page.getByTestId('sign-ins-failure')
    this.loadError = page.getByTestId('sign-ins-error')
    this.retry = page.getByTestId('sign-ins-retry')
    this.confirmTitle = page.getByTestId('confirm-title')
    this.confirm = page.getByTestId('confirm-accept')
    this.cancel = page.getByTestId('confirm-cancel')
  }

  async goto(): Promise<void> {
    await this.page.goto('/settings/sign-ins')
  }
}
