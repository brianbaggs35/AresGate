import type { Locator, Page } from '@playwright/test'

/** The list of incidents. */
export class IncidentsPage {
  readonly heading: Locator
  /** The choice of which statuses to list, and one button for each. */
  readonly views: Locator
  /** The ways to narrow the list. */
  readonly severity: Locator
  readonly confidence: Locator
  readonly address: Locator
  readonly clear: Locator
  /** The switch that includes the incidents the owner's verdicts quiet, and the button in the
   * empty list that turns it on. */
  readonly quieted: Locator
  readonly showQuieted: Locator
  /** The incidents, and what is shown when there are none. */
  readonly list: Locator
  readonly cards: Locator
  readonly empty: Locator
  /** Asks for the next page. */
  readonly more: Locator
  readonly showMore: Locator
  readonly refresh: Locator
  readonly updated: Locator
  /** Shown when the page could not load at all, and when only a refresh failed. */
  readonly error: Locator
  readonly retry: Locator
  readonly stale: Locator
  /** What the page says after a verdict was given from a card, and the button to take it back. */
  readonly judged: Locator
  readonly undo: Locator

  constructor(private readonly page: Page) {
    this.heading = page.getByTestId('page-heading')
    this.views = page.getByTestId('views')
    this.severity = page.getByTestId('filter-severity')
    this.confidence = page.getByTestId('filter-confidence')
    this.address = page.getByTestId('filter-address')
    this.clear = page.getByTestId('clear-filters')
    this.quieted = page.getByTestId('filter-quieted')
    this.showQuieted = page.getByTestId('empty-quieted')
    this.list = page.getByTestId('incident-list')
    this.cards = page.getByTestId('incident')
    this.empty = page.getByTestId('incidents-empty')
    this.more = page.getByTestId('more')
    this.showMore = page.getByTestId('show-more')
    this.refresh = page.getByTestId('refresh')
    this.updated = page.getByTestId('updated')
    this.error = page.getByTestId('incidents-error')
    this.retry = page.getByTestId('retry')
    this.stale = page.getByTestId('incidents-stale')
    this.judged = page.getByTestId('judged-text')
    this.undo = page.getByTestId('undo')
  }

  /** One of the three verdict buttons on a card of the list, by the verdict, such as
   * `not_suspicious`, and the card's place in the list. */
  quick(verdict: string, index = 0): Locator {
    return this.page.getByTestId('incident-card').nth(index).getByTestId(`quick-${verdict}`)
  }

  /** The button that shows the incidents of one view, such as `resolved`. */
  view(key: string): Locator {
    return this.page.getByTestId(`view-${key}`)
  }

  /** The number on a view's button. */
  count(key: string): Locator {
    return this.page.getByTestId(`count-${key}`)
  }

  /** The titles of the incidents listed, in order. */
  titles(): Locator {
    return this.page.getByTestId('incident-title')
  }

  /** Chooses from the severity or confidence menu, by what the choice is called. */
  async choose(menu: Locator, label: string): Promise<void> {
    await menu.click()
    await this.page.getByRole('option', { name: label }).click()
  }

  /** Types into the address field, which looks for it once it is a whole address. */
  async search(address: string): Promise<void> {
    await this.address.getByRole('textbox').fill(address)
  }

  async goto(query = ''): Promise<void> {
    await this.page.goto(`/incidents${query}`)
  }
}
