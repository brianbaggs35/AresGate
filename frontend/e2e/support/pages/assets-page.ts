import type { Locator, Page } from '@playwright/test'

/** The Assets page: every device the connected programs can see, as one list, with the search
 * and the choices that narrow it, and where the assets come from. */
export class AssetsPage {
  readonly heading: Locator
  readonly description: Locator
  /** The search box, and the choices of which state to list, one button for each. */
  readonly search: Locator
  readonly views: Locator
  /** The choices that narrow the list besides its state. */
  readonly newOnly: Locator
  readonly unidentified: Locator
  readonly clear: Locator
  readonly interfaceChoice: Locator
  readonly order: Locator
  /** The list, and a card for each asset in it. */
  readonly list: Locator
  readonly cards: Locator
  readonly names: Locator
  /** What the list says when there is nothing in it, and how to go on. */
  readonly empty: Locator
  readonly emptyTitle: Locator
  readonly showMore: Locator
  readonly refresh: Locator
  /** The panel of the programs that list devices, and the line about what new means. */
  readonly suppliers: Locator
  readonly note: Locator
  readonly stale: Locator
  readonly failure: Locator

  constructor(private readonly page: Page) {
    this.heading = page.getByRole('heading', { level: 1 })
    this.description = page.getByTestId('page-description')
    this.search = page.getByRole('searchbox', { name: 'Search assets' })
    this.views = page.getByTestId('views')
    this.newOnly = page.getByTestId('filter-new')
    this.unidentified = page.getByTestId('filter-unidentified')
    this.clear = page.getByTestId('clear-filters')
    this.interfaceChoice = page.getByTestId('filter-interface')
    this.order = page.getByTestId('filter-sort')
    this.list = page.getByTestId('asset-list')
    this.cards = page.getByTestId('asset-card')
    this.names = page.getByTestId('asset-name')
    this.empty = page.getByTestId('assets-empty')
    this.emptyTitle = this.empty.getByTestId('empty-title')
    this.showMore = page.getByTestId('show-more')
    this.refresh = page.getByTestId('refresh')
    this.suppliers = page.getByTestId('suppliers')
    this.note = page.getByTestId('assets-note')
    this.stale = page.getByTestId('assets-stale')
    this.failure = page.getByTestId('assets-error')
  }

  /** The button for a state: "all", "online", "recent" or "away". */
  view(state: 'all' | 'online' | 'recent' | 'away'): Locator {
    return this.page.getByTestId(`view-${state}`)
  }

  /** How many assets a state's button says it has. */
  count(state: 'all' | 'online' | 'recent' | 'away'): Locator {
    return this.page.getByTestId(`count-${state}`)
  }

  /** The button that narrows the list to what one program lists. */
  source(key: string): Locator {
    return this.page.getByTestId(`filter-source-${key}`)
  }

  /** The card of the asset with this name. */
  card(name: string): Locator {
    return this.cards.filter({ has: this.page.getByRole('heading', { name, exact: true }) })
  }

  /** What one program says it lists, in the panel at the bottom. */
  supplier(key: string): Locator {
    return this.page.getByTestId(`supplier-${key}`)
  }

  /** Types in the search box and presses Enter, so it applies at once. */
  async find(text: string): Promise<void> {
    await this.search.fill(text)
    await this.search.press('Enter')
  }

  async goto(query = ''): Promise<void> {
    await this.page.goto(`/assets${query}`)
  }
}
