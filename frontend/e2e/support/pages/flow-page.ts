import type { Locator, Page } from '@playwright/test'

/** The Network Flow page: the paths the traffic takes, what a block of them is, and the timeline. */
export class FlowPage {
  readonly heading: Locator
  readonly chart: Locator
  readonly bands: Locator
  readonly events: Locator
  readonly blocked: Locator
  readonly detail: Locator
  readonly detailName: Locator
  readonly readLogs: Locator
  readonly close: Locator
  readonly timeline: Locator
  readonly empty: Locator

  constructor(private readonly page: Page) {
    this.heading = page.getByRole('heading', { level: 1 })
    this.chart = page.getByTestId('flow-chart')
    this.bands = page.getByTestId('flow-band')
    this.events = page.getByTestId('stat-events')
    this.blocked = page.getByTestId('stat-blocked')
    this.detail = page.getByTestId('flow-detail')
    this.detailName = page.getByTestId('detail-name')
    this.readLogs = page.getByTestId('detail-logs')
    this.close = page.getByTestId('detail-close')
    this.timeline = page.getByTestId('flow-timeline')
    this.empty = page.getByTestId('chart-empty')
  }

  async goto(query = ''): Promise<void> {
    await this.page.goto(`/flow${query}`)
  }

  /** A block of the picture, by its id: `source:192.168.1.20` or `service:tcp/443`. */
  node(id: string): Locator {
    return this.page.getByTestId(`flow-node-${id}`)
  }

  window(hours: 1 | 6 | 24 | 168): Locator {
    return this.page.getByTestId(`window-${hours.toString()}`)
  }

  direction(way: 'all' | 'outgoing' | 'incoming' | 'inside'): Locator {
    return this.page.getByTestId(`direction-${way}`)
  }
}
