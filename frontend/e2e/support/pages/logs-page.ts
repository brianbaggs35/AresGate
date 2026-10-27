import type { Locator, Page } from '@playwright/test'

/** The Logs page: every event that was collected, a table of them on a computer and cards on a
 * phone, and the sheet that opens one whole. */
export class LogsPage {
  readonly heading: Locator
  /** The search box, the terms of it that were understood, the panel of ways to search and the
   * summary of what was found, with a button for each severity, integration and kind in it. */
  readonly searchBox: Locator
  readonly searchField: Locator
  readonly terms: Locator
  readonly searchHelp: Locator
  readonly searchPanel: Locator
  readonly recent: Locator
  readonly facets: Locator
  /** The chart of how many events there were when, and how many were found. */
  readonly volume: Locator
  readonly bars: Locator
  readonly matched: Locator
  /** The switch that follows along as new events come, and the line that says when it last did. */
  readonly live: Locator
  readonly updated: Locator
  readonly newEvents: Locator
  /** The table (a computer), its rows and its day headings, and the cards (a phone). */
  readonly table: Locator
  readonly rows: Locator
  readonly days: Locator
  readonly cards: Locator
  readonly empty: Locator
  readonly emptyClear: Locator
  readonly emptyIntegrations: Locator
  /** The line under the list that says how many are shown, and the button for the older ones. */
  readonly more: Locator
  readonly showOlder: Locator
  readonly refresh: Locator
  /** Shown when the page could not load at all, and when only a refresh failed. */
  readonly error: Locator
  readonly retry: Locator
  readonly stale: Locator
  readonly searchStale: Locator
  /** The menu of columns and of how time is shown. */
  readonly view: Locator
  readonly viewPanel: Locator
  readonly timeExact: Locator
  readonly timeRelative: Locator
  readonly columnsReset: Locator
  /** The menu of files the events can be downloaded as. */
  readonly export: Locator
  readonly exportCsv: Locator
  readonly exportJson: Locator
  /** The sheet that opens one event, and what is in it. */
  readonly drawer: Locator
  readonly drawerTitle: Locator
  readonly drawerClose: Locator
  readonly drawerOlder: Locator
  readonly drawerNewer: Locator
  readonly drawerIncident: Locator
  readonly drawerNoIncident: Locator
  readonly drawerAddresses: Locator
  readonly drawerError: Locator
  readonly rawRecord: Locator
  readonly rawText: Locator
  readonly rawNone: Locator

  constructor(private readonly page: Page) {
    this.heading = page.getByTestId('page-heading')
    this.searchField = page.getByTestId('search')
    this.searchBox = page.getByRole('textbox', { name: 'Search logs' })
    this.terms = page.getByTestId('search-term')
    this.searchHelp = page.getByTestId('search-help')
    this.searchPanel = page.getByTestId('search-panel')
    this.recent = page.getByTestId('search-recent')
    this.facets = page.getByTestId('facets')
    this.volume = page.getByTestId('volume-card')
    this.bars = page.getByTestId('bar-slot')
    this.matched = page.getByTestId('matched')
    this.live = page.getByTestId('live')
    this.updated = page.getByTestId('updated')
    this.newEvents = page.getByTestId('new-events')
    this.table = page.getByTestId('log-table')
    this.rows = page.getByTestId('log-row')
    this.days = page.getByTestId('log-day')
    this.cards = page.getByTestId('log-card')
    this.empty = page.getByTestId('logs-empty')
    this.emptyClear = page.getByTestId('empty-clear')
    this.emptyIntegrations = page.getByTestId('empty-integrations')
    this.more = page.getByTestId('more')
    this.showOlder = page.getByTestId('show-older')
    this.refresh = page.getByTestId('refresh')
    this.error = page.getByTestId('logs-error')
    this.retry = page.getByTestId('retry')
    this.stale = page.getByTestId('logs-stale')
    this.searchStale = page.getByTestId('search-stale')
    this.view = page.getByTestId('log-view')
    this.viewPanel = page.getByTestId('log-view-panel')
    this.timeExact = page.getByTestId('time-exact')
    this.timeRelative = page.getByTestId('time-relative')
    this.columnsReset = page.getByTestId('columns-reset')
    this.export = page.getByTestId('export')
    this.exportCsv = page.getByTestId('export-csv')
    this.exportJson = page.getByTestId('export-json')
    this.drawer = page.getByTestId('log-drawer')
    this.drawerTitle = page.getByTestId('drawer-title')
    this.drawerClose = page.getByTestId('drawer-close')
    this.drawerOlder = page.getByTestId('drawer-older')
    this.drawerNewer = page.getByTestId('drawer-newer')
    this.drawerIncident = page.getByTestId('drawer-incident')
    this.drawerNoIncident = page.getByTestId('drawer-no-incident')
    this.drawerAddresses = page.getByTestId('drawer-addresses')
    this.drawerError = page.getByTestId('drawer-error')
    this.rawRecord = page.getByTestId('raw-record')
    this.rawText = page.getByTestId('raw-text')
    this.rawNone = page.getByTestId('raw-none')
  }

  /** The events listed, whichever way the page draws them. */
  get events(): Locator {
    return this.page.getByTestId(/^log-(row|card)$/)
  }

  /** Searches for something: types it into the box and presses Enter, which does it at once. */
  async search(text: string): Promise<void> {
    await this.searchBox.fill(text)
    await this.searchBox.press('Enter')
  }

  /** The button of the summary for a severity, an integration or a kind, such as `kind:alert`. */
  facet(term: string): Locator {
    return this.page.getByTestId(`facet-${term}`)
  }

  /** The button that opens the event whose line says this, in the table or among the cards. */
  open(summary: string): Locator {
    return this.events.filter({ hasText: summary }).first()
  }

  /** The box of a column in the View menu, by the name of the column, such as `Protocol`. */
  columnBox(label: string): Locator {
    return this.page.getByRole('checkbox', { name: label })
  }

  /** A field of the sheet (`severity`, `from`, `signature`...), and its copy and find buttons. */
  field(id: string): Locator {
    return this.page.getByTestId(`field-${id}`)
  }

  find(id: string): Locator {
    return this.page.getByTestId(`find-${id}`)
  }

  async goto(query = ''): Promise<void> {
    await this.page.goto(`/logs${query}`)
  }
}
