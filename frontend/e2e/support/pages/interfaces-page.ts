import type { Locator, Page } from '@playwright/test'

/** The Interfaces page: the parts of the network, the guesses at where feeds belong, and the
 * feeds not placed yet, and the page of one interface. */
export class InterfacesPage {
  readonly heroTitle: Locator
  readonly find: Locator
  readonly found: Locator
  readonly add: Locator
  readonly problem: Locator
  readonly suggestions: Locator
  readonly confirmAll: Locator
  readonly cards: Locator
  readonly unplaced: Locator
  readonly ignored: Locator
  /** The sheet that makes or changes an interface. */
  readonly editor: Locator
  readonly editorTitle: Locator
  readonly editorName: Locator
  readonly editorNetworks: Locator
  readonly editorProblem: Locator
  readonly save: Locator
  readonly remove: Locator
  /** What is said at the bottom of the page after a change, and its Undo. */
  readonly notice: Locator
  readonly undo: Locator
  /** The page of one interface. */
  readonly role: Locator
  readonly sources: Locator
  readonly edit: Locator

  constructor(private readonly page: Page) {
    this.heroTitle = page.getByTestId('interfaces-hero-title')
    this.find = page.getByTestId('interfaces-find')
    this.found = page.getByTestId('interfaces-found')
    this.add = page.getByTestId('interfaces-add')
    this.problem = page.getByTestId('interfaces-problem')
    this.suggestions = page.getByTestId('suggestion')
    this.confirmAll = page.getByTestId('suggestions-confirm-all')
    this.cards = page.getByTestId('interface-card')
    this.unplaced = page.getByTestId('interfaces-unplaced')
    this.ignored = page.getByTestId('interfaces-ignored')
    this.editor = page.getByTestId('interface-editor')
    this.editorTitle = page.getByTestId('editor-title')
    this.editorName = page.getByTestId('editor-name').locator('input')
    this.editorNetworks = page.getByTestId('editor-networks').locator('textarea').first()
    this.editorProblem = page.getByTestId('editor-problem')
    this.save = page.getByTestId('editor-save')
    this.remove = page.getByTestId('editor-remove')
    this.notice = page.getByTestId('undo-notice-text')
    this.undo = page.getByTestId('undo-notice-undo')
    this.role = page.getByTestId('interface-role')
    this.sources = page.getByTestId('interface-sources')
    this.edit = page.getByTestId('interface-edit')
  }

  async goto(): Promise<void> {
    await this.page.goto('/interfaces')
  }

  /** The card of the interface with this name. */
  card(name: string): Locator {
    return this.cards.filter({ hasText: name })
  }

  /** The row of the feed with this name, wherever it is listed. */
  feed(name: string): Locator {
    return this.page.getByTestId('feed').filter({ hasText: name })
  }

  /** Chooses where a feed goes, from the list on its row. */
  async place(feed: string, where: string): Promise<void> {
    await this.feed(feed).getByTestId('feed-move').click()
    await this.page.getByRole('option', { name: where }).click()
  }

  /** Chooses the role of the interface being made or changed. */
  async chooseRole(label: string): Promise<void> {
    await this.page.getByTestId('role-picker').getByText(label, { exact: true }).click()
  }
}
