import type { Locator, Page } from '@playwright/test'

/** The settings page that lists the verdicts that were given, to change or take back. */
export class VerdictsPage {
  readonly card: Locator
  readonly rows: Locator
  readonly empty: Locator
  readonly notice: Locator
  readonly failure: Locator
  readonly refresh: Locator
  /** Shown when the list could not be loaded. */
  readonly error: Locator
  /** The dialog that changes a verdict, and the question that comes before taking one back. */
  readonly dialog: Locator
  readonly note: Locator
  readonly save: Locator
  readonly cancel: Locator
  readonly confirmTitle: Locator
  readonly confirm: Locator

  constructor(private readonly page: Page) {
    this.card = page.getByTestId('verdicts-card')
    this.rows = page.getByTestId('verdict-row')
    this.empty = page.getByTestId('no-verdicts')
    this.notice = page.getByTestId('verdicts-notice')
    this.failure = page.getByTestId('verdicts-failure')
    this.refresh = page.getByTestId('refresh-verdicts')
    this.error = page.getByTestId('verdicts-error')
    this.dialog = page.getByTestId('verdict-dialog')
    this.note = page.getByTestId('dialog-note').locator('input')
    this.save = page.getByTestId('dialog-save')
    this.cancel = page.getByTestId('dialog-cancel')
    this.confirmTitle = page.getByTestId('confirm-title')
    this.confirm = page.getByTestId('confirm-accept')
  }

  /** What one verdict says (its chip), for each row, in order. */
  says(): Locator {
    return this.rows.getByTestId('verdict')
  }

  /** What each verdict is about, in order. */
  about(): Locator {
    return this.rows.getByTestId('verdict-about')
  }

  /** Chooses what the dialog says, such as `threat`. */
  say(verdict: string): Locator {
    return this.page.getByTestId(`say-${verdict}`).getByRole('radio')
  }

  async goto(): Promise<void> {
    await this.page.goto('/settings/verdicts')
  }
}
