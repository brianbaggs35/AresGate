import type { Locator, Page } from '@playwright/test'

/** One incident. */
export class IncidentPage {
  readonly heading: Locator
  readonly severity: Locator
  readonly status: Locator
  readonly back: Locator
  /** What can be done about it, and what was done. */
  readonly notice: Locator
  readonly changeError: Locator
  /** The four numbers under the title. */
  readonly signalsTile: Locator
  readonly programsTile: Locator
  readonly addressesTile: Locator
  readonly blockedTile: Locator
  /** Why AresGate is as sure as it is. */
  readonly reasonsCard: Locator
  readonly confidence: Locator
  readonly reasons: Locator
  /** Where the addresses and devices are, and the facts. */
  readonly addressesCard: Locator
  readonly addresses: Locator
  /** The chart of signals over time, and the timeline. */
  readonly spreadCard: Locator
  readonly timelineCard: Locator
  readonly signals: Locator
  readonly more: Locator
  readonly updated: Locator
  /** Shown when the incident could not load at all, and when only a refresh failed. */
  readonly error: Locator
  readonly retry: Locator
  readonly stale: Locator

  constructor(private readonly page: Page) {
    this.heading = page.getByTestId('page-heading')
    this.severity = page.getByTestId('severity').first()
    this.status = page.getByTestId('incident-status')
    this.back = page.getByTestId('back')
    this.notice = page.getByTestId('notice')
    this.changeError = page.getByTestId('change-error')
    this.signalsTile = page.getByTestId('tile-signals')
    this.programsTile = page.getByTestId('tile-programs')
    this.addressesTile = page.getByTestId('tile-addresses')
    this.blockedTile = page.getByTestId('tile-blocked')
    this.reasonsCard = page.getByTestId('reasons-card')
    this.confidence = page.getByTestId('confidence-level').first()
    this.reasons = page.getByTestId('reason')
    this.addressesCard = page.getByTestId('addresses-card')
    this.addresses = page.getByTestId('address')
    this.spreadCard = page.getByTestId('spread-card')
    this.timelineCard = page.getByTestId('timeline-card')
    this.signals = page.getByTestId('signal')
    this.more = page.getByTestId('timeline-more')
    this.updated = page.getByTestId('updated')
    this.error = page.getByTestId('incident-error')
    this.retry = page.getByTestId('retry')
    this.stale = page.getByTestId('incident-stale')
  }

  /** The button that changes the status to one, such as `resolved`. */
  action(status: string): Locator {
    return this.page.getByTestId(`action-${status}`)
  }

  async goto(id: number): Promise<void> {
    await this.page.goto(`/incidents/${id.toString()}`)
  }
}
