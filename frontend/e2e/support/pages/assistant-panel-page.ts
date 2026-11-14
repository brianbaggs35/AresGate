import type { Locator, Page } from '@playwright/test'

/** The assistant's panel, which opens over any page: a drawer at the side, or a sheet on a phone. */
export class AssistantPanelPage {
  /** The button in the app bar that opens and closes it. */
  readonly opener: Locator
  readonly panel: Locator
  /** What the panel says it is looking at. */
  readonly context: Locator
  readonly starters: Locator
  readonly input: Locator
  readonly send: Locator
  readonly answers: Locator
  readonly newConversation: Locator
  readonly full: Locator
  readonly close: Locator
  /** The buttons for what the assistant suggests you do. */
  readonly actions: Locator
  readonly done: Locator
  readonly undo: Locator
  readonly undone: Locator

  constructor(page: Page) {
    this.opener = page.getByTestId('assistant-open')
    this.panel = page.getByTestId('assistant-panel')
    this.context = page.getByTestId('panel-context')
    this.starters = page.getByTestId('panel-starter')
    this.input = page.getByTestId('panel-input').locator('textarea')
    this.send = page.getByTestId('panel-send')
    this.answers = this.panel.getByLabel('The assistant answered')
    this.newConversation = page.getByTestId('panel-new')
    this.full = page.getByTestId('panel-full')
    this.close = page.getByTestId('panel-close')
    this.actions = page.getByTestId('action')
    this.done = page.getByTestId('action-done')
    this.undo = page.getByTestId('action-undo')
    this.undone = page.getByTestId('action-undone')
  }

  /** Types a question and sends it with the button. */
  async ask(question: string): Promise<void> {
    await this.input.fill(question)
    await this.send.click()
  }
}
