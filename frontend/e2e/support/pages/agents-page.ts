import type { Locator, Page } from '@playwright/test'

/** The agents: the list of them, the sheet that makes or changes one, and the page of one, with
 * the graph it runs and what its last run found. */
export class AgentsPage {
  readonly heading: Locator
  readonly make: Locator
  /** What is shown before there is an agent: a card for each kind to make one from. */
  readonly empty: Locator
  readonly kinds: Locator
  /** The note that AI is off or has no provider. */
  readonly ai: Locator
  readonly cards: Locator
  readonly problem: Locator
  /** The sheet that makes or changes an agent. */
  readonly dialog: Locator
  readonly dialogKinds: Locator
  readonly setupTitle: Locator
  readonly setupChecks: Locator
  readonly setupSteps: Locator
  readonly dialogName: Locator
  readonly dialogGoal: Locator
  /** The part of the sheet for an agent that tests the network, and the switch that allows it. */
  readonly dialogActive: Locator
  readonly dialogAllow: Locator
  readonly dialogProblem: Locator
  readonly save: Locator
  readonly remove: Locator
  /** The page of one agent. */
  readonly start: Locator
  readonly stop: Locator
  readonly edit: Locator
  readonly state: Locator
  readonly blocked: Locator
  readonly graph: Locator
  readonly nodes: Locator
  readonly runStatus: Locator
  readonly summary: Locator
  readonly findings: Locator
  readonly steps: Locator
  readonly history: Locator
  readonly notice: Locator
  /** What the noise cleaner suggests on its page, and the buttons of each suggestion. */
  readonly suggestions: Locator
  readonly proposals: Locator
  readonly apply: Locator
  readonly dismiss: Locator
  readonly undo: Locator
  readonly recentStatus: Locator

  constructor(private readonly page: Page) {
    this.heading = page.getByTestId('page-heading')
    this.make = page.getByTestId('agents-make')
    this.empty = page.getByTestId('agents-empty')
    this.kinds = page.getByTestId('agents-kind')
    this.ai = page.getByTestId('agents-ai')
    this.cards = page.getByTestId('agent-card')
    this.problem = page.getByTestId('agents-problem')
    this.dialog = page.getByTestId('agent-dialog')
    this.dialogKinds = page.getByTestId('dialog-kind')
    this.setupTitle = this.dialog.getByTestId('setup-title')
    this.setupChecks = this.dialog.getByTestId('setup-check')
    this.setupSteps = this.dialog.getByTestId('setup-step')
    this.dialogName = page.getByTestId('dialog-name').locator('input')
    this.dialogGoal = page.getByTestId('dialog-goal').locator('textarea').first()
    this.dialogActive = page.getByTestId('dialog-active')
    this.dialogAllow = page.getByTestId('dialog-allow').locator('input')
    this.dialogProblem = page.getByTestId('dialog-problem')
    this.save = page.getByTestId('dialog-save')
    this.remove = page.getByTestId('dialog-remove')
    this.start = page.getByTestId('agent-start')
    this.stop = page.getByTestId('agent-stop')
    this.edit = page.getByTestId('agent-edit')
    this.state = page.getByTestId('agent-state')
    this.blocked = page.getByTestId('agent-blocked')
    this.graph = page.getByTestId('agent-graph')
    this.nodes = page.getByTestId('graph-node')
    this.runStatus = page.getByTestId('run-status')
    this.summary = page.getByTestId('run-summary')
    this.findings = page.getByTestId('finding')
    this.steps = page.getByTestId('timeline-step')
    this.history = page.getByTestId('history-run')
    this.notice = page.getByTestId('undo-notice-text')
    this.suggestions = page.getByTestId('agent-suggestions')
    this.proposals = page.getByTestId('proposal')
    this.apply = page.getByTestId('proposal-apply')
    this.dismiss = page.getByTestId('proposal-dismiss')
    this.undo = page.getByTestId('proposal-undo')
    this.recentStatus = page.getByTestId('recent-status')
  }

  async goto(): Promise<void> {
    await this.page.goto('/agents')
  }

  /** The card of the agent with this name. */
  card(name: string): Locator {
    return this.cards.filter({ hasText: name })
  }

  /** Chooses what the new agent should do, by the name of the kind. */
  chooseKind(name: string): Promise<void> {
    return this.dialogKinds.filter({ hasText: name }).click()
  }
}
