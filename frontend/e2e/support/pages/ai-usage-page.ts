import type { Locator, Page } from '@playwright/test'

/** Settings > AI usage: what AI took and cost, the spending limits and every request. */
export class AiUsagePage {
  readonly card: Locator
  /** Shown before AI was ever asked anything. */
  readonly never: Locator
  readonly monthTile: Locator
  readonly costTile: Locator
  readonly tokensTile: Locator
  readonly requestsTile: Locator
  /** The note that says the costs are estimates, from where, and when. */
  readonly estimate: Locator
  readonly dailyChart: Locator
  readonly groupsChart: Locator
  readonly topItems: Locator
  readonly requests: Locator
  readonly more: Locator
  readonly download: Locator
  readonly dialog: Locator
  readonly error: Locator

  constructor(private readonly page: Page) {
    this.card = page.getByTestId('usage-card')
    this.never = page.getByTestId('usage-never')
    this.monthTile = page.getByTestId('tile-month')
    this.costTile = page.getByTestId('tile-cost')
    this.tokensTile = page.getByTestId('tile-tokens')
    this.requestsTile = page.getByTestId('tile-requests')
    this.estimate = page.getByTestId('usage-estimate')
    this.dailyChart = page.getByTestId('daily-chart')
    this.groupsChart = page.getByTestId('groups-chart')
    this.topItems = page.getByTestId('top-item')
    this.requests = page.getByTestId('call')
    this.more = page.getByTestId('calls-more')
    this.download = page.getByTestId('download')
    this.dialog = page.getByTestId('call-dialog')
    this.error = page.getByTestId('usage-error')
  }

  async goto(): Promise<void> {
    await this.page.goto('/settings/ai-usage')
  }

  /** The button of a range: 7d, 30d or 90d. */
  range(key: string): Locator {
    return this.page.getByTestId(`range-${key}`)
  }

  /** What to show: cost, tokens or calls. */
  metric(key: string): Locator {
    return this.page.getByTestId(`metric-${key}`)
  }

  /** What to group by: provider, model or use. */
  grouping(key: string): Locator {
    return this.page.getByTestId(`grouping-${key}`)
  }

  /** One of the two limits: `day` or `month`. */
  limitWords(period: 'day' | 'month'): Locator {
    return this.page.getByTestId(`limit-${period}-words`)
  }

  get dailyField(): Locator {
    return this.page.getByTestId('limit-daily-field').getByRole('textbox')
  }

  get monthlyField(): Locator {
    return this.page.getByTestId('limit-monthly-field').getByRole('textbox')
  }

  get saveLimits(): Locator {
    return this.page.getByTestId('limits-save')
  }

  get limitsSaved(): Locator {
    return this.page.getByTestId('limits-saved')
  }
}
