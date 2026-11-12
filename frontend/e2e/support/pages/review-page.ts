import type { Locator, Page } from '@playwright/test'

/** The Review page: what the AI decided, to agree or disagree with. */
export class ReviewPage {
  readonly heading: Locator
  readonly cards: Locator
  readonly empty: Locator
  readonly standing: Locator
  readonly offer: Locator
  readonly agreeAll: Locator
  readonly notice: Locator
  readonly settingsLink: Locator
  readonly more: Locator
  readonly nudge: Locator
  readonly nudgeOpen: Locator
  readonly confirm: Locator
  readonly badge: Locator

  constructor(private readonly page: Page) {
    this.heading = page.getByTestId('page-heading')
    this.cards = page.getByTestId('review-card')
    this.empty = page.getByTestId('review-empty')
    this.standing = page.getByTestId('review-standing-line')
    this.offer = page.getByTestId('review-offer')
    this.agreeAll = page.getByTestId('review-agree-all')
    this.notice = page.getByTestId('review-notice')
    this.settingsLink = page.getByTestId('review-settings')
    this.more = page.getByTestId('review-more')
    this.nudge = page.getByTestId('review-nudge')
    this.nudgeOpen = page.getByTestId('review-nudge-open')
    this.confirm = page.getByTestId('confirm-accept')
    this.badge = page.getByTestId('nav-review').getByTestId('nav-badge')
  }

  async goto(): Promise<void> {
    await this.page.goto('/review')
  }

  /** A list of the page: waiting, decided or answered, whose button says how many are in it. */
  list(name: 'waiting' | 'decided' | 'answered'): Locator {
    return this.page.getByTestId(`review-list-${name}`)
  }

  /** The card of a decision, found by what it is called. */
  card(title: string): Locator {
    return this.cards.filter({ hasText: title })
  }

  agree(card: Locator): Locator {
    return card.getByTestId('review-agree')
  }

  disagree(card: Locator): Locator {
    return card.getByTestId('review-disagree')
  }

  addReason(card: Locator): Locator {
    return card.getByTestId('review-add-reason')
  }

  reason(card: Locator): Locator {
    return card.getByTestId('review-reason').locator('textarea')
  }

  keep(card: Locator): Locator {
    return card.getByTestId('review-keep').locator('input')
  }

  said(card: Locator): Locator {
    return card.getByTestId('review-said')
  }

  undo(card: Locator): Locator {
    return card.getByTestId('review-undo')
  }
}

/** Settings > Review: how much of what the AI decides waits for the owner. */
export class ReviewSettingsPage {
  readonly mode: Locator
  readonly fromBar: Locator
  readonly fromValue: Locator
  readonly learn: Locator
  readonly save: Locator
  readonly discard: Locator
  readonly saved: Locator
  readonly failure: Locator

  constructor(private readonly page: Page) {
    this.mode = page.getByTestId('review-mode')
    this.fromBar = page.getByTestId('review-from-bar')
    this.fromValue = page.getByTestId('review-from-value')
    this.learn = page.getByTestId('review-learn').locator('input')
    this.save = page.getByTestId('review-save')
    this.discard = page.getByTestId('review-discard')
    this.saved = page.getByTestId('review-saved')
    this.failure = page.getByTestId('review-save-failure')
  }

  async goto(): Promise<void> {
    await this.page.goto('/settings/review')
  }

  choice(mode: 'all' | 'uncertain' | 'auto'): Locator {
    return this.page.getByTestId(`review-mode-${mode}`).locator('input')
  }
}
