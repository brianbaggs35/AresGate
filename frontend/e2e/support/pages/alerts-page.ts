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
  /** The sheet that sets what a destination is told about, and when. */
  readonly rules: Locator
  readonly rulesTitle: Locator
  readonly rulesSave: Locator
  readonly rulesCancel: Locator
  readonly rulesClose: Locator
  readonly rulesFailure: Locator
  readonly severity: Locator
  readonly confidence: Locator
  readonly sources: Locator
  readonly activities: Locator
  readonly quiet: Locator
  readonly quietFrom: Locator
  readonly quietUntil: Locator
  readonly quietCritical: Locator
  readonly rate: Locator
  readonly again: Locator
  /** What the rules in the sheet would have done in the last day. */
  readonly previewSummary: Locator
  readonly previewLeftOut: Locator
  readonly previewExamples: Locator
  readonly previewFailure: Locator

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
    this.rules = page.getByTestId('rules-dialog')
    this.rulesTitle = page.getByTestId('rules-title')
    this.rulesSave = page.getByTestId('rules-save')
    this.rulesCancel = page.getByTestId('rules-cancel')
    this.rulesClose = page.getByTestId('rules-close')
    this.rulesFailure = page.getByTestId('rules-failure')
    this.severity = page.getByTestId('rules-severity')
    this.confidence = page.getByTestId('rules-confidence')
    this.sources = page.getByTestId('rules-sources')
    this.activities = page.getByTestId('rules-activities')
    this.quiet = page.getByTestId('rules-quiet').getByRole('checkbox')
    this.quietFrom = page.getByTestId('rules-from').locator('input')
    this.quietUntil = page.getByTestId('rules-until').locator('input')
    this.quietCritical = page.getByTestId('rules-critical').getByRole('checkbox')
    this.rate = page.getByTestId('rules-rate')
    this.again = page.getByTestId('rules-again').getByRole('checkbox')
    this.previewSummary = page.getByTestId('preview-summary')
    this.previewLeftOut = page.getByTestId('preview-left-out')
    this.previewExamples = page.getByTestId('preview-examples')
    this.previewFailure = page.getByTestId('preview-failure')
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

  /** Opens the rules of the destination with this name. */
  async openRules(name: string): Promise<void> {
    await this.destination(name).getByTestId('destination-rules-edit').click()
    await this.rules.waitFor()
  }

  /** Chooses from one of the menus in the rules sheet, by what the choice is called. */
  async choose(menu: Locator, label: string): Promise<void> {
    await menu.locator('.v-field').click()
    await this.page.getByRole('option', { name: label }).click()
  }

  /** Picks how much a message says. */
  detail(label: string): Locator {
    return this.page.getByRole('radio', { name: new RegExp(`^${label}`) })
  }

  /** Adds a destination through the dialog. */
  async addDestination(name: string, url: string): Promise<void> {
    await this.add.click()
    await this.name.fill(name)
    await this.url.fill(url)
    await this.save.click()
  }
}
