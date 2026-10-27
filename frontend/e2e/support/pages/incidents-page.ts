import type { Locator, Page } from '@playwright/test'

import { SavedSearchesPanel } from './saved-searches'

/** The list of incidents. */
export class IncidentsPage {
  readonly heading: Locator
  /** The choice of which statuses to list, and one button for each. */
  readonly views: Locator
  /** The ways to narrow the list. */
  readonly severity: Locator
  readonly confidence: Locator
  readonly clear: Locator
  /** The search box, the terms of it that were understood, the panel of ways to search and the
   * summary of what was found, with a button for each severity and integration in it. */
  readonly searchBox: Locator
  readonly searchField: Locator
  readonly terms: Locator
  readonly searchHelp: Locator
  readonly searchPanel: Locator
  /** The searches kept under a name, in that panel. */
  readonly saved: SavedSearchesPanel
  readonly recent: Locator
  readonly facets: Locator
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
  /** The box on each card, and the row above the list that changes the incidents picked. */
  readonly picks: Locator
  readonly bulk: Locator
  readonly pickPage: Locator
  readonly picked: Locator
  readonly pickEverything: Locator
  readonly pickedEverything: Locator
  readonly letGo: Locator
  readonly bulkStatus: Locator
  /** What the page says after many were changed, and the button to take the change back. */
  readonly changed: Locator
  readonly takeBack: Locator
  /** The dialog that looks a change over, and what is in it. */
  readonly dialog: Locator
  readonly dialogTitle: Locator
  readonly dialogLines: Locator
  readonly dialogNote: Locator
  readonly dialogAccept: Locator
  readonly dialogCancel: Locator

  constructor(private readonly page: Page) {
    this.heading = page.getByTestId('page-heading')
    this.views = page.getByTestId('views')
    this.severity = page.getByTestId('filter-severity')
    this.confidence = page.getByTestId('filter-confidence')
    this.searchField = page.getByTestId('search')
    this.searchBox = page.getByRole('textbox', { name: 'Search incidents' })
    this.terms = page.getByTestId('search-term')
    this.searchHelp = page.getByTestId('search-help')
    this.searchPanel = page.getByTestId('search-panel')
    this.saved = new SavedSearchesPanel(page)
    this.recent = page.getByTestId('search-recent')
    this.facets = page.getByTestId('facets')
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
    this.picks = page.getByTestId('incident-select')
    this.bulk = page.getByTestId('bulk')
    this.pickPage = page.getByTestId('bulk-page')
    this.picked = page.getByTestId('bulk-count')
    this.pickEverything = page.getByTestId('bulk-everything')
    this.pickedEverything = page.getByTestId('bulk-all')
    this.letGo = page.getByTestId('bulk-clear')
    this.bulkStatus = page.getByTestId('bulk-status')
    this.changed = page.getByTestId('bulk-notice-text')
    this.takeBack = page.getByTestId('bulk-undo')
    this.dialog = page.getByTestId('confirm-dialog')
    this.dialogTitle = page.getByTestId('confirm-title')
    this.dialogLines = page.getByTestId('bulk-would')
    this.dialogNote = page.getByTestId('bulk-note').locator('textarea')
    this.dialogAccept = page.getByTestId('confirm-accept')
    this.dialogCancel = page.getByTestId('confirm-cancel')
  }

  /** The box of the incident whose card says this, such as an address. */
  pickOf(text: string): Locator {
    return this.page
      .getByTestId('incident-card')
      .filter({ hasText: text })
      .getByTestId('incident-select')
  }

  /** One of the three verdict buttons of the row that changes many, such as `not_suspicious`. */
  bulkVerdict(verdict: string): Locator {
    return this.page.getByTestId(`bulk-${verdict}`)
  }

  /** A choice in the menu of statuses that many can be changed to, such as `resolved`. */
  bulkTo(status: string): Locator {
    return this.page.getByTestId(`bulk-status-${status}`)
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

  /** Searches for something: types it into the box and presses Enter, which does it at once. */
  async search(text: string): Promise<void> {
    await this.searchBox.fill(text)
    await this.searchBox.press('Enter')
  }

  /** The button of the summary for a severity or an integration, such as `severity:high`. */
  facet(term: string): Locator {
    return this.page.getByTestId(`facet-${term}`)
  }

  async goto(query = ''): Promise<void> {
    await this.page.goto(`/incidents${query}`)
  }
}
