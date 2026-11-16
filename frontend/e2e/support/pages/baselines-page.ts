import type { Locator, Page } from '@playwright/test'

/** The Baselines page: what is usual for each interface, and the places each device talks to. */
export class BaselinesPage {
  readonly heading: Locator
  readonly charts: Locator
  readonly uncounted: Locator
  readonly learning: Locator
  readonly deviations: Locator
  readonly talkers: Locator
  readonly talkersEmpty: Locator
  readonly places: Locator
  readonly placeRows: Locator
  readonly failure: Locator
  readonly networkField: Locator
  readonly portField: Locator
  readonly addPlace: Locator

  constructor(private readonly page: Page) {
    this.heading = page.getByRole('heading', { level: 1 })
    this.charts = page.getByTestId('baseline-interface')
    this.uncounted = page.getByTestId('interfaces-uncounted')
    this.learning = page.getByTestId('interfaces-learning')
    this.deviations = page.getByTestId('baseline-deviations')
    this.talkers = page.getByTestId('talker')
    this.talkersEmpty = page.getByTestId('talkers-empty')
    this.places = page.getByTestId('baseline-places')
    this.placeRows = page.getByTestId('places-list').getByRole('listitem')
    this.failure = page.getByTestId('places-failure')
    this.networkField = page.getByTestId('place-network').locator('input')
    this.portField = page.getByTestId('place-port').locator('input')
    this.addPlace = page.getByTestId('place-add')
  }

  async goto(query = ''): Promise<void> {
    await this.page.goto(`/baselines${query}`)
  }

  /** The row of a place, by its network. */
  place(network: string): Locator {
    return this.placeRows.filter({ hasText: network })
  }
}
