import type { Locator, Page } from '@playwright/test'

/** The chat with the assistant: conversations, the box to ask in, and the answers. */
export class AssistantPage {
  readonly heading: Locator
  /** What is shown before anything was asked. */
  readonly empty: Locator
  readonly starters: Locator
  /** The form with the box to type in and the button to send. */
  readonly composer: Locator
  readonly input: Locator
  readonly send: Locator
  readonly thread: Locator
  readonly ownerMessages: Locator
  readonly answers: Locator
  readonly busy: Locator
  /** The note that AI is off or has no provider. */
  readonly off: Locator
  readonly failure: Locator
  readonly failedAnswer: Locator
  readonly retry: Locator
  readonly lookups: Locator
  readonly cites: Locator
  readonly calls: Locator
  readonly conversations: Locator
  readonly newConversation: Locator
  /** The list of conversations beside the page, where the screen has room for it. */
  readonly sidebar: Locator
  readonly conversationsButton: Locator
  readonly callDialog: Locator
  readonly confirm: Locator
  readonly error: Locator

  constructor(private readonly page: Page) {
    this.heading = page.getByTestId('page-heading')
    this.empty = page.getByTestId('chat-empty')
    this.starters = page.getByTestId('chat-starter')
    this.composer = page.getByTestId('chat-form')
    this.input = page.getByTestId('chat-input').locator('textarea')
    this.send = page.getByTestId('chat-send')
    this.thread = page.getByTestId('chat-thread')
    this.ownerMessages = page.getByTestId('message-owner')
    this.answers = page.getByLabel('The assistant answered')
    this.busy = page.getByTestId('chat-writing')
    this.off = page.getByTestId('chat-off')
    this.failure = page.getByTestId('chat-failure')
    this.failedAnswer = page.getByTestId('message-failed')
    this.retry = page.getByTestId('message-retry')
    this.lookups = page.getByTestId('message-lookup')
    this.cites = page.getByTestId('message-cite')
    this.calls = page.getByTestId('message-call')
    this.conversations = page.getByTestId('conversation')
    this.newConversation = page.getByTestId('new-chat')
    this.sidebar = page.getByRole('complementary', { name: 'Conversations' })
    this.conversationsButton = page.getByTestId('conversations-open')
    this.callDialog = page.getByTestId('call-dialog')
    this.confirm = page.getByTestId('confirm-accept')
    this.error = page.getByTestId('chat-error')
  }

  async goto(path = ''): Promise<void> {
    await this.page.goto(`/assistant${path}`)
  }

  /** Types a question and sends it with the button. */
  async ask(question: string): Promise<void> {
    await this.input.fill(question)
    await this.send.click()
  }

  /** Makes the list of conversations visible: on a phone it is in a sheet behind a button. */
  async showConversations(): Promise<void> {
    const sheet = this.page.getByTestId('conversations-sheet')
    // Which of the two the screen has is only known once the page has drawn one of them.
    await this.conversationsButton.or(this.sidebar).waitFor()
    if ((await this.conversationsButton.isVisible()) && !(await sheet.isVisible())) {
      await this.conversationsButton.click()
      await sheet.waitFor()
    }
  }

  /** Closes the sheet of conversations where there is one, so the page can be used again. */
  async hideConversations(): Promise<void> {
    if (await this.conversationsButton.isVisible()) {
      await this.page.keyboard.press('Escape')
      await this.page.getByTestId('conversations-sheet').waitFor({ state: 'hidden' })
    }
  }

  /**
   * Opens a conversation from the list, the one that has this text or the first. On a phone it
   * waits for the sheet to go, since a sheet on its way out still takes the taps meant for the page.
   */
  async openConversation(text?: string): Promise<void> {
    await this.showConversations()
    const found = text ? this.conversations.filter({ hasText: text }) : this.conversations
    await found.first().getByRole('link').click()
    if (await this.conversationsButton.isVisible()) {
      await this.page.getByTestId('conversations-sheet').waitFor({ state: 'hidden' })
    }
  }

  /** The delete button of a conversation. */
  deleteButton(conversation: Locator): Locator {
    return conversation.getByTestId('conversation-delete')
  }
}
