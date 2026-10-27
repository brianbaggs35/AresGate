import type { Locator, Page } from '@playwright/test'

/** The searches kept under a name, in the panel of a search box: they are the same on every page
 * that has a search, so the pages share this. */
export class SavedSearchesPanel {
  readonly section: Locator
  /** One button for each, which uses it. */
  readonly rows: Locator
  readonly none: Locator
  /** The name field, and the button that keeps what is in the search box under it. */
  readonly form: Locator
  readonly name: Locator
  readonly save: Locator
  /** The button of each that forgets it. */
  readonly forget: Locator
  readonly notice: Locator
  readonly failure: Locator

  constructor(page: Page) {
    this.section = page.getByTestId('saved-searches')
    this.rows = page.getByTestId('saved-use')
    this.none = page.getByTestId('saved-none')
    this.form = page.getByTestId('saved-form')
    this.name = page.getByRole('textbox', { name: 'Name this search' })
    this.save = page.getByTestId('saved-save')
    this.forget = page.getByTestId('saved-forget')
    this.notice = page.getByTestId('saved-notice')
    this.failure = page.getByTestId('saved-failure')
  }

  /** Keeps what is in the search box under a name. */
  async keep(name: string): Promise<void> {
    await this.name.fill(name)
    await this.save.click()
  }
}
