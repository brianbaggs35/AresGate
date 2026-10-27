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
  /** The sentence at the top that tells what happened, its parts and the confidence in its ring. */
  readonly hero: Locator
  readonly heroTitle: Locator
  readonly heroDetail: Locator
  readonly score: Locator
  readonly signalsTile: Locator
  readonly programsTile: Locator
  readonly addressesTile: Locator
  readonly blockedTile: Locator
  /** What was done about it: the state, a sentence, the bans, what else turned it away, the
   * steps in order and what AresGate can't tell. */
  readonly responseCard: Locator
  readonly responseState: Locator
  readonly responseHeadline: Locator
  readonly bans: Locator
  readonly banStatus: Locator
  readonly banReason: Locator
  readonly banEnds: Locator
  readonly turnedAway: Locator
  readonly steps: Locator
  readonly notes: Locator
  /** Why AresGate is as sure as it is. */
  readonly reasonsCard: Locator
  readonly confidence: Locator
  readonly reasons: Locator
  /** Where the addresses and devices are, and the facts. */
  readonly addressesCard: Locator
  readonly addresses: Locator
  /** What the owner thinks of it: the standing line, the verdicts that apply and the form for
   * giving another. */
  readonly verdictCard: Locator
  readonly standing: Locator
  readonly verdictChip: Locator
  readonly applied: Locator
  readonly scope: Locator
  readonly why: Locator
  readonly verdictNotice: Locator
  readonly verdictError: Locator
  /** Why its signals are one incident: the lines, the kind of activity, the waves and ports. */
  readonly groupingCard: Locator
  readonly grouping: Locator
  readonly waves: Locator
  readonly ports: Locator
  readonly showMorePorts: Locator
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
    this.hero = page.getByTestId('incident-hero')
    this.heroTitle = page.getByTestId('incident-hero-title')
    this.heroDetail = page.getByTestId('incident-hero-detail')
    this.score = page.getByTestId('confidence-score')
    this.signalsTile = page.getByTestId('tile-signals')
    this.programsTile = page.getByTestId('tile-programs')
    this.addressesTile = page.getByTestId('tile-addresses')
    this.blockedTile = page.getByTestId('tile-blocked')
    this.responseCard = page.getByTestId('response-card')
    this.responseState = page.getByTestId('response-state')
    this.responseHeadline = page.getByTestId('response-headline')
    this.bans = page.getByTestId('response-ban')
    this.banStatus = page.getByTestId('response-ban-status')
    this.banReason = page.getByTestId('response-ban-reason')
    this.banEnds = page.getByTestId('response-ban-ends')
    this.turnedAway = page.getByTestId('response-facts').getByTestId('fact-value')
    this.steps = page.getByTestId('response-step-title')
    this.notes = page.getByTestId('response-note')
    this.reasonsCard = page.getByTestId('reasons-card')
    this.confidence = page.getByTestId('confidence-level').first()
    this.reasons = page.getByTestId('reason')
    this.addressesCard = page.getByTestId('addresses-card')
    this.addresses = page.getByTestId('address')
    this.verdictCard = page.getByTestId('verdict-card')
    this.standing = page.getByTestId('verdict-standing')
    this.verdictChip = page.locator('.incident__chips').getByTestId('verdict')
    this.applied = page.getByTestId('applied')
    this.scope = page.getByTestId('verdict-scope')
    this.why = page.getByTestId('verdict-note').locator('input')
    this.verdictNotice = page.getByTestId('verdict-notice')
    this.verdictError = page.getByTestId('verdict-error')
    this.groupingCard = page.getByTestId('grouping-card')
    this.grouping = page.getByTestId('grouping-line')
    this.waves = page.getByTestId('waves')
    this.ports = page.getByTestId('port')
    this.showMorePorts = page.getByTestId('ports-show-more')
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

  /** The button that gives a verdict, such as `not_suspicious`. */
  give(verdict: string): Locator {
    return this.page.getByTestId(`give-${verdict}`)
  }

  /** Chooses what the verdict is about, by its name in the menu. */
  async about(label: string | RegExp): Promise<void> {
    await this.scope.click()
    await this.page.getByRole('option', { name: label }).click()
  }

  async goto(id: number): Promise<void> {
    await this.page.goto(`/incidents/${id.toString()}`)
  }
}
