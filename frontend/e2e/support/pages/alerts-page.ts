import { expect, type Locator, type Page } from '@playwright/test'

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
  /** The choice of Discord or email when adding, and the email address. */
  readonly kindEmail: Locator
  readonly recipient: Locator
  /** The mail server email destinations send through, and the dialog that sets it up. */
  readonly mail: Locator
  readonly mailName: Locator
  readonly mailEdit: Locator
  readonly mailRemove: Locator
  readonly mailDialog: Locator
  readonly mailHost: Locator
  readonly mailPort: Locator
  readonly mailSecurity: Locator
  readonly mailUsername: Locator
  readonly mailPassword: Locator
  readonly mailForget: Locator
  readonly mailSender: Locator
  readonly mailSave: Locator
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
  /** The three cards for what a channel is for, and what the sheet shows under the one chosen. */
  readonly purposes: Locator
  readonly floors: Locator
  readonly threatsNote: Locator
  readonly threatsLink: Locator
  /** The message as Discord will show it, and the choice of which message of the story. */
  readonly discord: Locator
  readonly discordTitle: Locator
  readonly discordDescription: Locator
  readonly discordFields: Locator
  readonly discordFooter: Locator
  readonly sampleFailure: Locator
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
  /** The log of messages sent, and the filters on it. */
  readonly log: Locator
  readonly logTotals: Locator
  readonly deliveries: Locator
  readonly logEmpty: Locator
  readonly logState: Locator
  readonly logRefresh: Locator

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
    this.kindEmail = page.getByTestId('dialog-kind-email')
    this.recipient = page.getByTestId('dialog-recipient').locator('input')
    this.mail = page.getByTestId('mail-server')
    this.mailName = page.getByTestId('mail-name')
    this.mailEdit = page.getByTestId('mail-edit')
    this.mailRemove = page.getByTestId('mail-remove')
    this.mailDialog = page.getByTestId('mail-dialog')
    this.mailHost = page.getByTestId('mail-host').locator('input')
    this.mailPort = page.getByTestId('mail-port').locator('input')
    this.mailSecurity = page.getByTestId('mail-security')
    this.mailUsername = page.getByTestId('mail-username').locator('input')
    this.mailPassword = page.getByTestId('mail-password').locator('input')
    this.mailForget = page.getByTestId('mail-forget').getByRole('checkbox')
    this.mailSender = page.getByTestId('mail-sender').locator('input')
    this.mailSave = page.getByTestId('mail-save')
    this.confirmTitle = page.getByTestId('confirm-title')
    this.confirm = page.getByTestId('confirm-accept')
    this.confirmCancel = page.getByTestId('confirm-cancel')
    this.rules = page.getByTestId('rules-dialog')
    this.rulesTitle = page.getByTestId('rules-title')
    this.rulesSave = page.getByTestId('rules-save')
    this.rulesCancel = page.getByTestId('rules-cancel')
    this.rulesClose = page.getByTestId('rules-close')
    this.rulesFailure = page.getByTestId('rules-failure')
    this.purposes = page.getByTestId('purposes')
    this.floors = page.getByTestId('rules-floors')
    this.threatsNote = page.getByTestId('rules-threats-note')
    this.threatsLink = page.getByTestId('rules-threat-link')
    this.discord = page.getByTestId('discord-preview')
    this.discordTitle = page.getByTestId('discord-title')
    this.discordDescription = page.getByTestId('discord-description')
    this.discordFields = page.getByTestId('discord-fields')
    this.discordFooter = page.getByTestId('discord-footer')
    this.sampleFailure = page.getByTestId('sample-failure')
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
    this.log = page.getByTestId('delivery-log')
    this.logTotals = page.getByTestId('delivery-totals')
    this.deliveries = page.getByTestId('delivery')
    this.logEmpty = page.getByTestId('delivery-empty')
    this.logState = page.getByTestId('delivery-filter-state')
    this.logRefresh = page.getByTestId('delivery-refresh')
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

  /**
   * Makes a change to the rules and waits for the preview to answer for it. The sheet asks 400 ms
   * after the last change and dims the preview while it waits, so a check made too soon sees
   * faint text. Several changes can be made in one go: the sheet asks once, after the last.
   */
  async changeRules(change: () => Promise<void>): Promise<void> {
    const answered = this.page.waitForResponse(
      (response) =>
        response.request().method() === 'POST' &&
        new URL(response.url()).pathname.endsWith('/preview'),
    )
    await change()
    await answered
    await expect(this.page.getByTestId('rules-preview')).toHaveAttribute('aria-busy', 'false')
  }

  /** The card for what a channel is for: `threats`, `serious` or `custom`. */
  purpose(key: 'threats' | 'serious' | 'custom'): Locator {
    return this.page.getByTestId(`purpose-${key}`)
  }

  /** Its radio button, which says whether it is the one chosen. */
  purposeChosen(key: 'threats' | 'serious' | 'custom'): Locator {
    return this.purpose(key).getByRole('radio')
  }

  /** The button that shows the first message of the story of an incident, or what is sent if it
   * gets worse. */
  story(which: 'new' | 'worse'): Locator {
    return this.page.getByTestId(`rules-story-${which}`)
  }

  /** Chooses from one of the menus in the rules sheet, by exactly what the choice is called ("Sent"
   * is also in "Not sent" and "Waiting to be sent"). */
  async choose(menu: Locator, label: string): Promise<void> {
    await menu.locator('.v-field').click()
    await this.page.getByRole('option', { name: label, exact: true }).click()
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

  /** Adds an email destination through the dialog. */
  async addEmailDestination(name: string, recipient: string): Promise<void> {
    await this.add.click()
    await this.kindEmail.click()
    await this.name.fill(name)
    await this.recipient.fill(recipient)
    await this.save.click()
  }

  /** Sets up the mail server through its dialog, with the usual way to connect. */
  async setUpMail(host: string, sender: string, password: string): Promise<void> {
    await this.mailEdit.click()
    await this.mailHost.fill(host)
    await this.mailUsername.fill(sender)
    await this.mailPassword.fill(password)
    await this.mailSender.fill(sender)
    await this.mailSave.click()
  }
}
