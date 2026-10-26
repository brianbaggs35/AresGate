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
  readonly alertsCard: Locator
  readonly sourcesCard: Locator
  readonly latestAlerts: Locator
  readonly alertRows: Locator
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
    this.alertsCard = page.getByTestId('alerts-card')
    this.sourcesCard = page.getByTestId('sources-card')
    this.latestAlerts = page.getByTestId('latest-alerts-card')
    this.alertRows = page.getByTestId('recent-alert')
    this.range = page.getByTestId('range')
    this.day = page.getByTestId('range-24h')
    this.week = page.getByTestId('range-7d')
    this.refresh = page.getByTestId('refresh')
    this.updated = page.getByTestId('updated')
    this.error = page.getByTestId('dashboard-error')
    this.retry = page.getByTestId('retry')
    this.stale = page.getByTestId('dashboard-stale')
  }

  async goto(): Promise<void> {
    await this.page.goto('/')
  }
}
