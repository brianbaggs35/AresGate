import type { Locator, Page } from '@playwright/test'

/** The page of one asset: what it is and how it has been listed, the traffic ntopng measured for
 * it, its addresses, the events they were in, what it talked to, and the incidents and verdicts
 * about it. */
export class AssetPage {
  readonly heading: Locator
  readonly description: Locator
  readonly back: Locator
  readonly status: Locator
  /** The four figures across the top: when it was last listed, the traffic it sent and received in
   * the last day, and how many events it was in. */
  readonly listedTile: Locator
  readonly sentTile: Locator
  readonly receivedTile: Locator
  readonly eventsTile: Locator
  /** The choice of how far back the chart looks, and the chart itself. */
  readonly windows: Locator
  readonly chart: Locator
  /** The addresses it has had, and the ones it has now. */
  readonly addresses: Locator
  readonly currentAddresses: Locator
  readonly noAddresses: Locator
  /** The programs that listed it, and how each one did. */
  readonly listedBy: Locator
  /** The events its addresses were in, newest first, and what the page says of how many there were. */
  readonly eventsNote: Locator
  readonly eventItems: Locator
  readonly eventFlows: Locator
  /** What it talked to, and what talked to it, in the last week. */
  readonly talksTo: Locator
  readonly contactedBy: Locator
  readonly peers: Locator
  readonly talksToNone: Locator
  readonly contactedByNone: Locator
  /** The incidents its addresses are in, and the verdicts given about it. */
  readonly incidents: Locator
  readonly noIncidents: Locator
  readonly verdicts: Locator
  readonly noVerdicts: Locator
  /** The packet capture: its card, the button, what it says of the packets, each packet, and why
   * it couldn't. */
  readonly capture: Locator
  readonly captureStart: Locator
  readonly captureSummary: Locator
  readonly capturePackets: Locator
  readonly captureFailure: Locator
  /** What the page says when there is no such asset, when it cannot be read, and while it loads. */
  readonly missing: Locator
  readonly failure: Locator
  readonly retry: Locator
  readonly loading: Locator

  constructor(private readonly page: Page) {
    this.heading = page.getByRole('heading', { level: 1 })
    this.description = page.getByTestId('page-description')
    this.back = page.getByTestId('back')
    this.status = page.getByTestId('asset-status')
    this.listedTile = page.getByTestId('asset-tile-listed')
    this.sentTile = page.getByTestId('asset-tile-sent')
    this.receivedTile = page.getByTestId('asset-tile-received')
    this.eventsTile = page.getByTestId('asset-tile-events')
    this.windows = page.getByTestId('asset-window')
    this.chart = page.getByTestId('asset-chart')
    this.addresses = page.getByTestId('asset-address')
    this.currentAddresses = page.getByTestId('asset-address-now')
    this.noAddresses = page.getByTestId('asset-no-addresses')
    this.listedBy = page.getByTestId('asset-listed-by')
    this.eventsNote = page.getByTestId('asset-events-note')
    this.eventItems = page.getByTestId('asset-event')
    this.eventFlows = page.getByTestId('asset-event-flow')
    this.talksTo = page.getByTestId('asset-talks-to')
    this.contactedBy = page.getByTestId('asset-contacted-by')
    this.peers = page.getByTestId('asset-peer')
    this.talksToNone = page.getByTestId('asset-talks-to-none')
    this.contactedByNone = page.getByTestId('asset-contacted-by-none')
    this.incidents = page.getByTestId('asset-incident')
    this.noIncidents = page.getByTestId('asset-no-incidents')
    this.verdicts = page.getByTestId('asset-verdict')
    this.noVerdicts = page.getByTestId('asset-no-verdicts')
    this.capture = page.getByTestId('asset-capture-section')
    this.captureStart = page.getByTestId('capture-start')
    this.captureSummary = page.getByTestId('capture-summary')
    this.capturePackets = page.getByTestId('capture-packet')
    this.captureFailure = page.getByTestId('capture-failure')
    this.missing = page.getByTestId('asset-missing')
    this.failure = page.getByTestId('asset-error')
    this.retry = page.getByTestId('asset-retry')
    this.loading = page.getByTestId('asset-loading')
  }

  /** The button for how far back the chart looks: "24 hours" or "7 days". */
  window(label: '24 hours' | '7 days'): Locator {
    return this.windows.getByRole('button', { name: label })
  }

  /** Opens the page of the asset with this key, such as `device-3`. */
  async goto(key: string): Promise<void> {
    await this.page.goto(`/assets/${key}`)
  }
}
