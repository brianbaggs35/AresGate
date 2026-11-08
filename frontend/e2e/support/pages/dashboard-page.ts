import type { Locator, Page } from '@playwright/test'

/** The dashboard, which is the landing page. */
export class DashboardPage {
  readonly heading: Locator
  /** The sentence at the top that says whether anything needs attention, and its parts. */
  readonly banner: Locator
  readonly bannerTitle: Locator
  readonly bannerDetail: Locator
  readonly bannerAction: Locator
  /** The four numbers under it. */
  readonly alertsTile: Locator
  readonly blockedTile: Locator
  readonly devicesTile: Locator
  readonly collectionTile: Locator
  /** The cards of charts and the list of the latest alerts. */
  readonly trafficCard: Locator
  readonly trafficChart: Locator
  readonly trafficInterface: Locator
  /** The flags above the traffic, one for each incident (or group of them) that began in the
   * window, each a link to the incident, and the count some of them carry. */
  readonly trafficFlags: Locator
  readonly trafficFlagCounts: Locator
  readonly alertsCard: Locator
  readonly sourcesCard: Locator
  readonly latestAlerts: Locator
  readonly alertRows: Locator
  /** The lane of incidents that need a decision, its cards and the link to all of them. */
  readonly needsYou: Locator
  readonly needsYouCards: Locator
  readonly needsYouAll: Locator
  /** What was filtered out: the sentence that counts the incidents, and a link for each reason. */
  readonly filtered: Locator
  readonly filteredSummary: Locator
  readonly filteredUnsure: Locator
  readonly filteredCleared: Locator
  readonly filteredMuted: Locator
  readonly filteredHandled: Locator
  /** Where the alerts come from: the card, what it says in a sentence, the alerts it lists and
   * the buttons of each. */
  readonly noise: Locator
  readonly noiseSummary: Locator
  readonly noiseItems: Locator
  readonly noiseQuiet: Locator
  readonly noiseLogs: Locator
  /** What the page says after a verdict was given from a card, and the button to take it back. */
  readonly judged: Locator
  readonly undo: Locator
  /** The choice of 24 hours or 7 days, and the button that asks again. */
  readonly range: Locator
  readonly day: Locator
  readonly week: Locator
  readonly refresh: Locator
  /** When the numbers arrived. */
  readonly updated: Locator
  /** Shown when the page could not load at all, and when only a refresh failed. */
  readonly error: Locator
  readonly retry: Locator
  readonly stale: Locator

  constructor(private readonly page: Page) {
    this.heading = page.getByTestId('page-heading')
    this.banner = page.getByTestId('posture')
    this.bannerTitle = page.getByTestId('posture-title')
    this.bannerDetail = page.getByTestId('posture-detail')
    this.bannerAction = page.getByTestId('posture-action')
    this.alertsTile = page.getByTestId('tile-alerts')
    this.blockedTile = page.getByTestId('tile-blocked')
    this.devicesTile = page.getByTestId('tile-devices')
    this.collectionTile = page.getByTestId('tile-collection')
    this.trafficCard = page.getByTestId('traffic-card')
    this.trafficChart = page.getByTestId('traffic-chart')
    this.trafficInterface = page.getByTestId('traffic-interface')
    this.trafficFlags = this.trafficChart.getByTestId('chart-flag')
    this.trafficFlagCounts = this.trafficChart.getByTestId('chart-flag-count')
    this.alertsCard = page.getByTestId('alerts-card')
    this.sourcesCard = page.getByTestId('sources-card')
    this.latestAlerts = page.getByTestId('latest-alerts-card')
    this.alertRows = page.getByTestId('recent-alert')
    this.needsYou = page.getByTestId('needs-you')
    this.needsYouCards = this.needsYou.getByTestId('incident-card')
    this.needsYouAll = page.getByTestId('needs-you-all')
    this.filtered = page.getByTestId('filtered')
    this.filteredSummary = page.getByTestId('filtered-summary')
    this.filteredUnsure = page.getByTestId('filtered-unsure')
    this.filteredCleared = page.getByTestId('filtered-cleared')
    this.filteredMuted = page.getByTestId('filtered-muted')
    this.filteredHandled = page.getByTestId('filtered-handled')
    this.noise = page.getByTestId('noise-card')
    this.noiseSummary = page.getByTestId('noise-summary')
    this.noiseItems = this.noise.getByTestId('noise-item')
    this.noiseQuiet = this.noise.getByTestId('noise-quiet')
    this.noiseLogs = this.noise.getByTestId('noise-logs')
    this.judged = page.getByTestId('judged-text')
    this.undo = page.getByTestId('undo')
    this.range = page.getByTestId('range')
    this.day = page.getByTestId('range-24h')
    this.week = page.getByTestId('range-7d')
    this.refresh = page.getByTestId('refresh')
    this.updated = page.getByTestId('updated')
    this.error = page.getByTestId('dashboard-error')
    this.retry = page.getByTestId('retry')
    this.stale = page.getByTestId('dashboard-stale')
  }

  /** One of the three verdict buttons on a card of the lane, by the verdict, such as
   * `not_suspicious`, and the card's place in the lane. */
  quick(verdict: string, index = 0): Locator {
    return this.needsYouCards.nth(index).getByTestId(`quick-${verdict}`)
  }

  async goto(): Promise<void> {
    await this.page.goto('/')
  }
}
