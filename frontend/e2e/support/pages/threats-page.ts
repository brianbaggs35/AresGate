import type { Locator, Page } from '@playwright/test'

/** The Threats page: how the reports came down to threats, the three lanes, and the kinds of
 * incident the background is made of. */
export class ThreatsPage {
  readonly heading: Locator
  readonly funnelSentence: Locator
  readonly coverage: Locator
  readonly kindsLink: Locator
  readonly tuneLink: Locator
  readonly range7: Locator
  readonly refresh: Locator
  /** The cards of the lane on screen, and what is said when it is empty. */
  readonly cards: Locator
  readonly laneMeaning: Locator
  readonly laneEmpty: Locator
  /** The kinds the background is made of. */
  readonly kinds: Locator
  readonly kindsEmpty: Locator
  readonly allKinds: Locator
  readonly backgroundIncidents: Locator
  readonly more: Locator
  readonly error: Locator
  readonly stale: Locator
  /** What is offered from what you decided of incidents, and its buttons. */
  readonly suggestions: Locator
  readonly suggestionReason: Locator
  readonly suggestionTake: Locator
  readonly suggestionDismiss: Locator
  /** What the threat hunter flagged among the incidents going on. */
  readonly hunted: Locator
  readonly huntedItems: Locator

  constructor(private readonly page: Page) {
    this.heading = page.getByTestId('page-heading')
    this.funnelSentence = page.getByTestId('funnel-sentence')
    this.coverage = page.getByTestId('coverage')
    this.kindsLink = page.getByTestId('kinds-link')
    this.tuneLink = page.getByTestId('tune-link')
    this.range7 = page.getByTestId('range-7d')
    this.refresh = page.getByTestId('refresh')
    this.cards = page.getByTestId('incident-card')
    this.laneMeaning = page.getByTestId('lane-meaning')
    this.laneEmpty = page.getByTestId('lane-empty')
    this.kinds = page.getByTestId('family-card')
    this.kindsEmpty = page.getByTestId('kind-empty')
    this.allKinds = page.getByTestId('all-kinds')
    this.backgroundIncidents = page.getByTestId('background-incidents')
    this.more = page.getByTestId('more')
    this.error = page.getByTestId('threats-error')
    this.stale = page.getByTestId('threats-stale')
    this.suggestions = page.getByTestId('suggestion')
    this.suggestionReason = page.getByTestId('suggestion-reason')
    this.suggestionTake = page.getByTestId('suggestion-take')
    this.suggestionDismiss = page.getByTestId('suggestion-dismiss')
    this.hunted = page.getByTestId('hunted')
    this.huntedItems = page.getByTestId('hunted-item')
  }

  async goto(lane?: 'threat' | 'suspect' | 'background'): Promise<void> {
    await this.page.goto(lane ? `/threats?lane=${lane}` : '/threats')
  }

  /** The button for a lane, and the number it shows. */
  lane(name: 'threat' | 'suspect' | 'background'): Locator {
    return this.page.getByTestId(`lane-${name}`)
  }

  count(name: 'threat' | 'suspect' | 'background'): Locator {
    return this.page.getByTestId(`count-${name}`)
  }

  /** One step of the funnel, and its number. */
  step(name: string): Locator {
    return this.page.getByTestId(`funnel-${name}`)
  }

  stepCount(name: string): Locator {
    return this.step(name).getByTestId('funnel-count')
  }
}

/** The list of kinds of incident. */
export class KindsPage {
  readonly heading: Locator
  readonly search: Locator
  readonly total: Locator
  readonly cards: Locator
  readonly empty: Locator
  readonly more: Locator

  constructor(private readonly page: Page) {
    this.heading = page.getByTestId('page-heading')
    this.search = page.getByRole('textbox', { name: 'Search the kinds' })
    this.total = page.getByTestId('kinds-total')
    this.cards = page.getByTestId('family-card')
    this.empty = page.getByTestId('kinds-empty')
    this.more = page.getByTestId('kinds-more')
  }

  async goto(query = ''): Promise<void> {
    await this.page.goto(`/threats/kinds${query}`)
  }

  /** The select for a lane, and the one for who judged it. */
  get lane(): Locator {
    return this.page.getByTestId('kinds-lane')
  }

  get judged(): Locator {
    return this.page.getByTestId('kinds-judged')
  }
}

/** One kind of incident: what is thought of it, by you and the AI, and its incidents. */
export class KindPage {
  readonly heading: Locator
  readonly judgementClass: Locator
  readonly judgementReason: Locator
  readonly judgementBy: Locator
  readonly judgementNone: Locator
  readonly judgementOwner: Locator
  readonly judgementFailure: Locator
  readonly background: Locator
  readonly watch: Locator
  readonly takeBack: Locator
  readonly judge: Locator
  readonly why: Locator
  readonly suggestion: Locator
  readonly suggestionDismiss: Locator
  readonly changed: Locator
  readonly changes: Locator
  readonly sample: Locator
  readonly cards: Locator
  readonly openInIncidents: Locator
  readonly error: Locator

  constructor(page: Page) {
    this.heading = page.getByTestId('page-heading')
    this.judgementClass = page.getByTestId('judgement-class')
    this.judgementReason = page.getByTestId('judgement-reason')
    this.judgementBy = page.getByTestId('judgement-by')
    this.judgementNone = page.getByTestId('judgement-none')
    this.judgementOwner = page.getByTestId('judgement-owner')
    this.judgementFailure = page.getByTestId('judgement-failure')
    this.background = page.getByTestId('call-background')
    this.watch = page.getByTestId('call-watch')
    this.takeBack = page.getByTestId('call-clear')
    this.judge = page.getByTestId('judge')
    this.why = page.getByTestId('why')
    this.suggestion = page.getByTestId('suggestion')
    this.suggestionDismiss = page.getByTestId('suggestion-dismiss')
    this.changed = page.getByTestId('changed')
    this.changes = page.getByTestId('change')
    this.sample = page.getByTestId('sample')
    this.cards = page.getByTestId('incident-card')
    this.openInIncidents = page.getByTestId('sample-all')
    this.error = page.getByTestId('kind-error')
  }
}

/** Settings > Threat detection. */
export class ThreatSettingsPage {
  readonly levelValue: Locator
  readonly levelSentence: Locator
  readonly levelReset: Locator
  readonly aiOff: Locator
  readonly clearBar: Locator
  readonly clearValue: Locator
  readonly clearSentence: Locator
  readonly ports: Locator
  readonly portsError: Locator
  readonly notes: Locator
  readonly effectSentence: Locator
  readonly effectIdle: Locator
  readonly effectTable: Locator
  readonly save: Locator
  readonly discard: Locator
  readonly saved: Locator
  readonly failure: Locator

  constructor(private readonly page: Page) {
    this.levelValue = page.getByTestId('threat-value')
    this.levelSentence = page.getByTestId('threat-sentence')
    this.levelReset = page.getByTestId('threat-reset')
    this.aiOff = page.getByTestId('threat-ai-off')
    this.clearBar = page.getByTestId('threat-clear-bar')
    this.clearValue = page.getByTestId('clear-value')
    this.clearSentence = page.getByTestId('clear-sentence')
    this.ports = page.getByTestId('threat-ports').getByRole('textbox')
    this.portsError = page.getByTestId('threat-ports').locator('.v-messages')
    this.notes = page.getByTestId('threat-notes').getByRole('textbox')
    const card = page.getByTestId('threat-effect-card')
    this.effectSentence = card.getByTestId('effect-sentence')
    this.effectIdle = card.getByTestId('effect-idle')
    this.effectTable = card.getByTestId('effect-table')
    this.save = card.getByTestId('effect-save')
    this.discard = card.getByTestId('effect-discard')
    this.saved = card.getByTestId('effect-saved')
    this.failure = card.getByTestId('effect-failure')
  }

  async goto(): Promise<void> {
    await this.page.goto('/settings/threat-detection')
  }

  get levelSlider(): Locator {
    return this.page.getByRole('slider', {
      name: 'How sure AresGate has to be to call an incident a threat',
    })
  }

  get clearSwitch(): Locator {
    return this.page.getByTestId('threat-clear').getByRole('checkbox')
  }

  get clearSlider(): Locator {
    return this.page.getByRole('slider', {
      name: 'How sure the AI has to be to set an incident aside',
    })
  }

  get confirmSwitch(): Locator {
    return this.page.getByTestId('threat-confirm').getByRole('checkbox')
  }

  /** The radio for what is open to the internet: none, some or unknown. */
  exposure(choice: 'none' | 'some' | 'unknown'): Locator {
    return this.page.getByTestId(`exposure-${choice}`).getByRole('radio')
  }

  /** What the table says of one lane, now and with the settings as they are on the page. */
  figure(key: 'threats' | 'suspects' | 'background' | 'cleared' | 'muted'): {
    now: Locator
    after: Locator
  } {
    const row = this.page.getByTestId(`effect-${key}`)
    return { now: row.getByTestId('effect-now'), after: row.getByTestId('effect-after') }
  }
}
