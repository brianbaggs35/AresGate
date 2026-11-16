import type { Locator, Page } from '@playwright/test'

/** The page for what the AI cleared, and what it suggests clearing. */
export class ClearedPage {
  readonly heading: Locator
  readonly cards: Locator
  readonly empty: Locator
  readonly notice: Locator
  readonly failure: Locator
  readonly settingsLink: Locator
  readonly pickAll: Locator
  readonly confirmPicked: Locator
  readonly takeBackPicked: Locator
  readonly accept: Locator
  readonly nudge: Locator
  readonly nudgeOpen: Locator
  readonly trail: Locator

  constructor(private readonly page: Page) {
    this.heading = page.getByTestId('page-heading')
    this.cards = page.getByTestId('cleared-card')
    this.empty = page.getByTestId('cleared-empty')
    this.notice = page.getByTestId('cleared-notice')
    this.failure = page.getByTestId('cleared-failure')
    this.settingsLink = page.getByTestId('cleared-settings')
    this.pickAll = page.getByTestId('cleared-pick-all')
    this.confirmPicked = page.getByTestId('cleared-confirm-picked')
    this.takeBackPicked = page.getByTestId('cleared-take-back-picked')
    this.accept = page.getByTestId('confirm-accept')
    this.nudge = page.getByTestId('cleared-nudge')
    this.nudgeOpen = page.getByTestId('cleared-nudge-open')
    this.trail = page.getByTestId('clearing-trail')
  }

  async goto(): Promise<void> {
    await this.page.goto('/cleared')
  }

  /** A list of the page, whose button says how many are in it. */
  list(name: 'waiting' | 'cleared'): Locator {
    return this.page.getByTestId(`cleared-list-${name}`)
  }

  /** The card of an incident, found by its address. */
  card(text: string): Locator {
    return this.cards.filter({ hasText: text })
  }

  pick(card: Locator): Locator {
    return card.getByTestId('cleared-pick')
  }

  confirm(card: Locator): Locator {
    return card.getByTestId('cleared-confirm')
  }

  other(card: Locator): Locator {
    return card.getByTestId('cleared-other')
  }

  takeBack(card: Locator): Locator {
    return card.getByTestId('cleared-take-back')
  }
}
