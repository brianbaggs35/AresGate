import type { Locator, Page } from '@playwright/test'

/** The Devices page: every address that took part in a connection the connected programs
 * reported over the last week, with the search and the choices that narrow it. */
export class DevicesPage {
  readonly heading: Locator
  readonly description: Locator
  readonly search: Locator
  readonly views: Locator
  readonly direction: Locator
  readonly order: Locator
  readonly flagged: Locator
  readonly clear: Locator
  readonly list: Locator
  readonly cards: Locator
  readonly addresses: Locator
  readonly empty: Locator
  readonly emptyTitle: Locator
  readonly note: Locator

  constructor(private readonly page: Page) {
    this.heading = page.getByRole('heading', { level: 1 })
    this.description = page.getByTestId('page-description')
    this.search = page.getByRole('searchbox', { name: 'Search devices' })
    this.views = page.getByTestId('views')
    this.direction = page.getByTestId('filter-direction')
    this.order = page.getByTestId('filter-sort')
    this.flagged = page.getByTestId('filter-flagged')
    this.clear = page.getByTestId('clear-filters')
    this.list = page.getByTestId('device-list')
    this.cards = page.getByTestId('device-card')
    this.addresses = page.getByTestId('device-address')
    this.empty = page.getByTestId('devices-empty')
    this.emptyTitle = this.empty.getByTestId('empty-title')
    this.note = page.getByTestId('devices-note')
  }

  /** The button for a scope: "all", "yours", "local" or "outside". */
  view(scope: 'all' | 'yours' | 'local' | 'outside'): Locator {
    return this.page.getByTestId(`view-${scope}`)
  }

  /** How many devices a scope's button says it has. */
  count(scope: 'all' | 'yours' | 'local' | 'outside'): Locator {
    return this.page.getByTestId(`count-${scope}`)
  }

  /** The card of the device with this address. */
  card(address: string): Locator {
    return this.cards.filter({
      has: this.page.getByRole('heading', { name: address, exact: true }),
    })
  }

  /** Types in the search box and presses Enter, so it applies at once. */
  async find(text: string): Promise<void> {
    await this.search.fill(text)
    await this.search.press('Enter')
  }

  async goto(query = ''): Promise<void> {
    await this.page.goto(`/devices${query}`)
  }

  /** Opens the device with this address from its card, as someone who clicks it would. */
  async open(address: string): Promise<void> {
    await this.card(address).getByTestId('device-link').click()
  }
}

/** The page of one device: whose it is, the connections to it and from it, the events it was in,
 * and the incidents and what is known of it. */
export class DevicePage {
  readonly heading: Locator
  readonly description: Locator
  readonly back: Locator
  readonly incomingTile: Locator
  readonly outgoingTile: Locator
  readonly connections: Locator
  readonly connectionRows: Locator
  readonly events: Locator
  readonly incidents: Locator
  readonly noIncidents: Locator
  readonly assetLink: Locator
  readonly missing: Locator

  constructor(page: Page) {
    this.heading = page.getByRole('heading', { level: 1 })
    this.description = page.getByTestId('page-description')
    this.back = page.getByRole('link', { name: 'Devices' }).first()
    this.incomingTile = page.getByTestId('device-tile-incoming')
    this.outgoingTile = page.getByTestId('device-tile-outgoing')
    this.connections = page.getByTestId('connections')
    this.connectionRows = page.getByTestId('connection')
    this.events = page.getByTestId('asset-event')
    this.incidents = page.getByTestId('device-incident')
    this.noIncidents = page.getByTestId('device-no-incidents')
    this.assetLink = page.getByTestId('device-asset-link')
    this.missing = page.getByTestId('device-missing')
  }
}
