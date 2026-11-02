import type { Locator, Page } from '@playwright/test'

/** Settings > Noise filters: how sure AresGate has to be before it asks, what each program has to
 * be worth, whether alerts inside the network count, and what saving would change. */
export class NoiseFiltersPage {
  readonly floorCard: Locator
  readonly floorValue: Locator
  readonly floorSentence: Locator
  readonly floorReset: Locator
  readonly sourcesCard: Locator
  readonly sources: Locator
  readonly noSources: Locator
  readonly insideCard: Locator
  readonly manageVerdicts: Locator
  /** What saving would change, and the buttons that save or put the page back. */
  readonly effectCard: Locator
  readonly effectSentence: Locator
  readonly effectIdle: Locator
  readonly effectTable: Locator
  readonly save: Locator
  readonly discard: Locator
  readonly saved: Locator
  readonly failure: Locator

  constructor(private readonly page: Page) {
    this.floorCard = page.getByTestId('floor-card')
    this.floorValue = page.getByTestId('floor-value')
    this.floorSentence = page.getByTestId('floor-sentence')
    this.floorReset = page.getByTestId('floor-reset')
    this.sourcesCard = page.getByTestId('sources-card')
    this.sources = page.getByTestId('source')
    this.noSources = page.getByTestId('no-sources')
    this.insideCard = page.getByTestId('inside-card')
    this.manageVerdicts = page.getByTestId('manage-verdicts')
    this.effectCard = page.getByTestId('effect-card')
    this.effectSentence = page.getByTestId('effect-sentence')
    this.effectIdle = page.getByTestId('effect-idle')
    this.effectTable = page.getByTestId('effect-table')
    this.save = page.getByTestId('effect-save')
    this.discard = page.getByTestId('effect-discard')
    this.saved = page.getByTestId('effect-saved')
    this.failure = page.getByTestId('effect-failure')
  }

  async goto(): Promise<void> {
    await this.page.goto('/settings/noise-filters')
  }

  /** The slider for how sure AresGate has to be. */
  get floorSlider(): Locator {
    return this.page.getByRole('slider', { name: 'How sure AresGate has to be before it asks you' })
  }

  /** The switch for alerts between two devices on the network. */
  get insideSwitch(): Locator {
    return this.page.getByTestId('inside-switch').getByRole('checkbox')
  }

  /** The row for one program, by its name. */
  source(name: string): Locator {
    return this.sources.filter({ hasText: name })
  }

  /** Chooses the lowest severity that counts for a program, by what the list calls it. */
  async chooseFloor(name: string, choice: string): Promise<void> {
    await this.source(name).getByTestId('source-floor').click()
    await this.page.getByRole('option', { name: choice }).click()
  }

  /** What the table says of one figure, now and with the settings as they are on the page. */
  figure(key: 'needs-you' | 'filtered-out' | 'set-aside'): {
    now: Locator
    after: Locator
  } {
    const row = this.page.getByTestId(`effect-${key}`)
    return { now: row.getByTestId('effect-now'), after: row.getByTestId('effect-after') }
  }
}
