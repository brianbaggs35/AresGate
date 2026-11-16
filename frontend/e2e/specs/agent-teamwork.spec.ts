import type { IncidentRequest } from '../support'
import { expect, test, turnOnAi } from '../support'

/** A scan that two programs saw, of a device on the network that is known by name. */
const SCAN: IncidentRequest = {
  address: '93.184.216.34',
  severity: 'high',
  programs: ['wazuh', 'opnsense'],
  signals: 4,
  minutes_ago: 4,
  device_name: 'nas',
}

// The page looks again every four seconds, so a run that the test started is seen within that.
const SEEN = { timeout: 15_000 }

test.describe('agents working together', () => {
  test.beforeEach(async ({ harness, aiSettings }) => {
    await harness.createIncidents([SCAN])
    await turnOnAi(harness, aiSettings)
  })

  test('an agent asks another to look further, and the owner can follow it', async ({
    harness,
    agents,
    page,
  }) => {
    await agents.goto()
    const made = [
      ['Incident investigator', 'Investigator'],
      ['Security orchestrator', 'Orchestrator'],
    ] as const
    for (const [kind, name] of made) {
      await agents.make.click()
      await agents.chooseKind(kind)
      await agents.dialogName.fill(name)
      await agents.save.click()
      await expect(agents.dialog).toHaveCount(0)
    }
    await expect(agents.handoffsSection).toHaveCount(0)

    await agents.card('Orchestrator').getByTestId('agent-run').click()
    // The orchestrator reports and asks the investigator, whose run waits; then that is run too.
    expect(await harness.runAgents()).toBe(1)
    expect(await harness.runAgents()).toBe(1)

    await expect(agents.handoffsSection).toBeVisible(SEEN)
    await expect(agents.handoffs).toHaveCount(1)
    await expect(agents.handoffs.first()).toContainText('Orchestrator')
    await expect(agents.handoffs.first()).toContainText('Investigator')
    await expect(agents.handoffs.first().getByTestId('handoff-status')).toHaveText('Asked')
    await expect(agents.handoffs.first()).toContainText('closer look')
    await expect(page.getByTestId('handoffs-limits')).toContainText('2 levels deep')

    // The agent that was asked says who asked, and how the run fits in.
    await agents.card('Investigator').getByTestId('agent-open').click()
    await expect(page.getByTestId('run-meta')).toContainText('Asked by another agent', SEEN)
    await expect(agents.investigation).toBeVisible()
    await expect(agents.moments.first()).toContainText('Was asked by Orchestrator')
    await expect(agents.moments.last()).toContainText('Concluded')

    // The incident shows what each agent made of it, in order.
    await page.goto('/incidents')
    await page
      .getByRole('link', { name: /93\.184\.216\.34/ })
      .first()
      .click()
    await expect(page.getByTestId('agents-card')).toBeVisible(SEEN)
    await expect(page.getByTestId('agents-card').getByTestId('moment-kind').first()).toBeVisible()
    await expect(page.getByTestId('agents-card')).toContainText('Asked Investigator')
  })

  test('the steps the planner proposes wait until the owner approves or dismisses them', async ({
    harness,
    agents,
    page,
  }) => {
    await agents.goto()
    await agents.make.click()
    await agents.chooseKind('Response planner')
    await agents.dialogName.fill('Planner')
    await agents.save.click()
    await expect(agents.dialog).toHaveCount(0)
    await agents.card('Planner').getByTestId('agent-run').click()
    expect(await harness.runAgents()).toBe(1)

    await expect(agents.stepsSection).toBeVisible(SEEN)
    await expect(agents.planSteps).toHaveCount(1)
    await expect(agents.planSteps.first()).toContainText('Change the password of the device')
    await expect(agents.planSteps.first().getByTestId('step-risk')).toContainText(
      'What it risks: Anything signed in',
    )
    await expect(agents.planSteps.first().getByTestId('step-incident')).toBeVisible()

    await agents.approveStep.click()

    await expect(agents.notice).toContainText('Approved', SEEN)
    await expect(agents.planSteps).toHaveCount(0)
    await expect(agents.stepsSection.getByTestId('recent-status')).toHaveText('Approved')

    // It stays on its incident as a task the owner carries out.
    await page.goto('/incidents')
    await page
      .getByRole('link', { name: /93\.184\.216\.34/ })
      .first()
      .click()
    await expect(page.getByTestId('agents-card')).toBeVisible(SEEN)
    await expect(page.getByTestId('agents-card').getByTestId('recent-status')).toHaveText(
      'Approved',
    )
    await expect(page.getByTestId('agents-card')).toContainText('Proposed a step')
  })

  test('a step that is dismissed is not proposed again', async ({ harness, agents }) => {
    await agents.goto()
    await agents.make.click()
    await agents.chooseKind('Response planner')
    await agents.dialogName.fill('Planner')
    await agents.save.click()
    await expect(agents.dialog).toHaveCount(0)
    await agents.card('Planner').getByTestId('agent-run').click()
    expect(await harness.runAgents()).toBe(1)
    await expect(agents.planSteps).toHaveCount(1, SEEN)

    await agents.dismissStep.click()
    await expect(agents.planSteps).toHaveCount(0, SEEN)
    await agents.card('Planner').getByTestId('agent-run').click()
    expect(await harness.runAgents()).toBe(1)

    await expect(agents.stepsSection.getByTestId('recent-status')).toHaveText('Dismissed', SEEN)
    await expect(agents.planSteps).toHaveCount(0)
  })
})
