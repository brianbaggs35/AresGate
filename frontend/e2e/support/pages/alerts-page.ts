import type { Locator, Page } from '@playwright/test'

/** The Alerts page: the places AresGate sends word of threats, and the dialog that adds or
 * changes one. */
export class AlertsPage {
  readonly heading: Locator
  readonly add: Locator
  readonly list: Locator
  readonly destinations: Locator
  readonly empty: Locator
  readonly emptyAdd: Locator
  readonly full: Locator
  /** What was done, and what went wrong. */
  readonly notice: Locator
  readonly failure: Locator
  /** Shown when the list could not be loaded. */
  readonly error: Locator
  readonly retry: Locator
  /** The dialog that adds a destination or changes one. */
  readonly dialog: Locator
  readonly dialogTitle: Locator
  readonly name: Locator
  readonly url: Locator
  readonly showUrl: Locator
  readonly save: Locator
  readonly cancel: Locator
  readonly dialogFailure: Locator
  /** The question that comes before removing one. */
  readonly confirmTitle: Locator
  readonly confirm: Locator
  readonly confirmCancel: Locator

  constructor(private readonly page: Page) {
    this.heading = page.getByTestId('page-heading')
    this.add = page.getByTestId('destination-add')
    this.list = page.getByTestId('destination-list')
    this.destinations = page.getByTestId('destination')
    this.empty = page.getByTestId('no-destinations')
    this.emptyAdd = page.getByTestId('empty-add')
    this.full = page.getByTestId('alerts-full')
    this.notice = page.getByTestId('alerts-notice')
    this.failure = page.getByTestId('alerts-failure')
    this.error = page.getByTestId('alerts-error')
    this.retry = page.getByTestId('alerts-retry')
    this.dialog = page.getByTestId('destination-dialog')
    this.dialogTitle = page.getByTestId('dialog-title')
    this.name = page.getByTestId('dialog-name').locator('input')
    this.url = page.getByTestId('dialog-url').locator('input')
    this.showUrl = page.getByTestId('dialog-url').getByTestId('show-secret')
    this.save = page.getByTestId('dialog-save')
    this.cancel = page.getByTestId('dialog-cancel')
    this.dialogFailure = page.getByTestId('dialog-failure')
    this.confirmTitle = page.getByTestId('confirm-title')
    this.confirm = page.getByTestId('confirm-accept')
    this.confirmCancel = page.getByTestId('confirm-cancel')
  }

  async goto(): Promise<void> {
    await this.page.goto('/alerts')
  }

  /** The card of the destination with this name. */
  destination(name: string): Locator {
    return this.destinations.filter({
      has: this.page.getByTestId('destination-name').getByText(name, { exact: true }),
    })
  }

  /** The switch on a card that turns sending to it on or off. */
  switchOf(card: Locator): Locator {
    return card.getByTestId('destination-enabled').getByRole('checkbox')
  }

  /** Adds a destination through the dialog. */
  async addDestination(name: string, url: string): Promise<void> {
    await this.add.click()
    await this.name.fill(name)
    await this.url.fill(url)
    await this.save.click()
  }
}
