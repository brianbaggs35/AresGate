import type { Locator, Page } from '@playwright/test'

/** The page that says how AresGate and the programs under it are doing. */
export class StatusPage {
  readonly heading: Locator
  readonly refresh: Locator
  readonly loadError: Locator
  readonly retry: Locator
  /** What it says when nothing needs a look, or the list of what does. */
  readonly fine: Locator
  readonly attention: Locator
  readonly attentionItems: Locator
  readonly aresgate: Locator
  readonly software: Locator
  readonly container: Locator
  /** The integrations, and the worker and collectors, each in a card of its own. */
  readonly parts: Locator
  readonly partNames: Locator
  readonly partStates: Locator
  readonly collectors: Locator
  readonly collectorNames: Locator
  readonly collectorStates: Locator
  /** The bars for what is used of memory and the disk. */
  readonly meters: Locator
  /** The text for a bug report, and copying it. */
  readonly report: Locator
  readonly diagnostics: Locator
  readonly copy: Locator
  readonly copied: Locator
  readonly copyFailed: Locator

  constructor(private readonly page: Page) {
    this.heading = page.getByTestId('page-heading')
    this.refresh = page.getByTestId('status-refresh')
    this.loadError = page.getByTestId('status-error')
    this.retry = page.getByTestId('status-retry')
    this.fine = page.getByTestId('status-fine')
    this.attention = page.getByTestId('status-attention')
    this.attentionItems = page.getByTestId('status-attention-item')
    this.aresgate = page.getByTestId('status-aresgate')
    this.software = page.getByTestId('status-software')
    this.container = page.getByTestId('status-container')
    this.parts = page.getByTestId('status-parts')
    this.partNames = this.parts.getByTestId('part-name')
    this.partStates = this.parts.getByTestId('part-state')
    this.collectors = page.getByTestId('status-collectors')
    this.collectorNames = this.collectors.getByTestId('part-name')
    this.collectorStates = this.collectors.getByTestId('part-state')
    this.meters = page.getByTestId('usage-meter')
    this.report = page.getByTestId('status-report')
    this.diagnostics = page.getByTestId('diagnostics')
    this.copy = page.getByTestId('status-copy')
    this.copied = page.getByTestId('status-copied')
    this.copyFailed = page.getByTestId('status-copy-failed')
  }

  async goto(): Promise<void> {
    await this.page.goto('/status')
  }

  /** The value of one fact in a card, such as `version`. */
  fact(id: string): Locator {
    return this.page.getByTestId(`fact-${id}`).getByTestId('fact-value')
  }

  /** One integration's row, by its name. */
  part(name: string): Locator {
    return this.parts.getByTestId('part').filter({ hasText: name })
  }

  /** The row of the worker or of one collector, by its name. */
  collector(name: string): Locator {
    return this.collectors.getByTestId('part').filter({ hasText: name })
  }
}
