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

test.describe('agents', () => {
  test('is a place in the menu, and offers the kinds of agent before there is one', async ({
    page,
    shell,
    agents,
  }) => {
    await page.goto('/')

    await shell.goTo('agents')

    await expect(page).toHaveURL('/agents')
    await expect(page).toHaveTitle('Agents · AresGate')
    await expect(agents.heading).toHaveText('Agents')
    await expect(agents.empty).toBeVisible()
    await expect(agents.kinds).toHaveCount(12)
    await expect(agents.cards).toHaveCount(0)
  })

  test('says AI is off, and what an agent needs it for', async ({ agents }) => {
    await agents.goto()

    await expect(agents.ai).toContainText('AI is turned off.')
  })

  test('says what a kind needs before it is made, and how to set it up', async ({ agents }) => {
    await agents.goto()

    await agents.make.click()
    await expect(agents.setupTitle).toHaveText('It needs a little setup first')
    await expect(agents.setupChecks.first()).toContainText('An AI provider for the agents to ask')
    await agents.chooseKind('Intelligence analyst')
    await expect(agents.setupChecks).toHaveCount(3)
    await agents.dialog.getByText('How to set it up').click()
    await expect(agents.setupSteps.first()).toContainText('VirusTotal')
  })

  test('makes an agent from a kind, with its name and instructions to change', async ({
    harness,
    aiSettings,
    agents,
    page,
  }) => {
    await turnOnAi(harness, aiSettings)
    await agents.goto()
    await expect(agents.ai).toHaveCount(0)

    await agents.make.click()
    await expect(agents.dialog).toBeVisible()
    await expect(agents.dialogKinds).toHaveCount(12)
    await agents.chooseKind('Threat hunter')
    await agents.dialogName.fill('Night watch')
    await agents.dialogGoal.fill('Only wake me for real compromises.')
    await agents.save.click()

    await expect(agents.dialog).toHaveCount(0)
    await expect(agents.notice).toContainText('Night watch')
    await expect(agents.card('Night watch')).toContainText('Threat hunter')
    // It was saved, not only shown.
    await page.reload()
    await expect(agents.card('Night watch')).toBeVisible()
  })

  test('runs one, shows each step as the graph, and says what it found with what it is based on', async ({
    harness,
    aiSettings,
    agents,
    page,
  }) => {
    await harness.createIncidents([SCAN])
    await turnOnAi(harness, aiSettings)
    await agents.goto()
    await agents.kinds.filter({ hasText: 'Threat hunter' }).getByTestId('agents-kind-make').click()
    await agents.dialogName.fill('Night watch')
    await agents.save.click()
    await expect(agents.dialog).toHaveCount(0)

    await agents.card('Night watch').getByTestId('agent-run').click()
    await expect(agents.card('Night watch').getByTestId('agent-state')).toContainText(
      'Waiting to start',
    )
    expect(await harness.runAgents()).toBe(1)

    await expect(agents.card('Night watch').getByTestId('agent-outcome')).toContainText(
      '1 finding',
      SEEN,
    )
    // Mission control says what needs the owner, and leads to the agent that said so.
    await expect(agents.mission).toHaveText('1 thing needs you', SEEN)
    await expect(agents.missionNeeds).toContainText('needs a look')
    await agents.missionNeeds.first().click()

    await expect(page).toHaveURL(/\/agents\/\d+$/)
    await expect(agents.heading).toHaveText('Night watch')
    await expect(agents.runStatus).toHaveText('Finished')
    await expect(agents.nodes).toHaveText([
      /Plan.*Done/s,
      /Look.*Done/s,
      /Think.*Done/s,
      /Report.*Done/s,
    ])
    await expect(agents.summary).toContainText('Start with incident')
    await expect(agents.findings).toHaveCount(1)
    await expect(agents.findings.first()).toContainText('needs a look')
    await expect(agents.findings.first()).toContainText('What to do: Check the device it reached')
    await expect(agents.findings.first()).toContainText('Sure')
    await expect(agents.findings.first()).toContainText('First time it was reported')
    await expect(agents.trend).toBeVisible()
    await expect(agents.steps.first()).toBeVisible()

    await agents.findings.first().getByTestId('finding-cite').first().click()

    await expect(page).toHaveURL(/\/incidents\/\d+$/)
  })

  test('says nothing needed attention when there was nothing to look at', async ({
    harness,
    aiSettings,
    agents,
  }) => {
    await turnOnAi(harness, aiSettings)
    await agents.goto()
    await agents.kinds.first().getByTestId('agents-kind-make').click()
    await agents.save.click()
    await expect(agents.dialog).toHaveCount(0)
    await agents.cards.first().getByTestId('agent-run').click()
    await expect(agents.cards.first().getByTestId('agent-state')).toContainText('Waiting to start')
    await harness.runAgents()

    await agents.cards.first().getByTestId('agent-open').click()

    await expect(agents.runStatus).toHaveText('Finished', SEEN)
    await expect(agents.findings).toHaveCount(0)
    await expect(agents.summary).toContainText('Nothing needs your attention')
  })

  test('keeps a network test from running until it was allowed, and is never on a schedule', async ({
    harness,
    aiSettings,
    agents,
  }) => {
    await turnOnAi(harness, aiSettings)
    await agents.goto()
    await agents.make.click()
    await agents.chooseKind('Exposure scanner')
    await expect(agents.dialogActive).toBeVisible()
    await agents.save.click()
    await expect(agents.dialog).toHaveCount(0)

    await agents.cards.first().getByTestId('agent-open').click()

    await expect(agents.blocked).toBeVisible()
    await expect(agents.start).toBeDisabled()
    await agents.edit.click()
    await agents.dialogAllow.check()
    await agents.save.click()
    await expect(agents.dialog).toHaveCount(0)
    await expect(agents.blocked).toHaveCount(0)
    await expect(agents.start).toBeEnabled()
    expect(await harness.runAgents()).toBe(0)
  })

  test('removes an agent after asking', async ({ harness, aiSettings, agents, page }) => {
    await turnOnAi(harness, aiSettings)
    await agents.goto()
    await agents.kinds.first().getByTestId('agents-kind-make').click()
    await agents.save.click()
    await expect(agents.dialog).toHaveCount(0)
    await agents.cards.first().getByTestId('agent-open').click()

    await agents.edit.click()
    await agents.remove.click()
    await page.getByTestId('confirm-accept').click()

    await expect(agents.heading).toHaveText('Agents')
    await expect(agents.cards).toHaveCount(0)
    await expect(agents.empty).toBeVisible()
  })

  test('has a noise cleaner that suggests tidying, which is applied with a press and taken back', async ({
    harness,
    aiSettings,
    agents,
    incidents,
    incident,
    page,
  }) => {
    // Not serious, and nothing has touched it for days.
    await harness.createIncidents([
      { address: '8.8.4.4', severity: 'low', idle_days: 4, device_name: 'printer' },
    ])
    await turnOnAi(harness, aiSettings)
    await agents.goto()
    await agents.kinds.filter({ hasText: 'Noise cleaner' }).getByTestId('agents-kind-make').click()
    await agents.save.click()
    await expect(agents.dialog).toHaveCount(0)
    await agents.cards.first().getByTestId('agent-run').click()
    await expect(agents.cards.first().getByTestId('agent-state')).toContainText('Waiting to start')
    expect(await harness.runAgents()).toBe(1)

    await expect(agents.cards.first().getByTestId('agent-proposals')).toHaveText(
      '1 clean-up is waiting for you.',
      SEEN,
    )
    await agents.cards.first().getByTestId('agent-open').click()

    await expect(agents.suggestions).toBeVisible()
    await expect(agents.proposals).toHaveCount(1)
    await expect(agents.proposals.first()).toContainText('1 old incident nothing has touched')
    await agents.apply.click()

    await expect(agents.notice).toContainText('Done')
    await expect(agents.proposals).toHaveCount(0)
    await expect(agents.recentStatus).toHaveText(['Done'])
    await incidents.goto()
    await expect(incidents.cards).toHaveCount(0)

    await page.goBack()
    await agents.undo.click()

    await expect(agents.notice).toContainText('Taken back')
    await expect(agents.recentStatus).toHaveText(['Taken back'])
    await incidents.goto()
    await expect(incidents.cards).toHaveCount(1)
    await incidents.cards.first().click()
    await expect(incident.status).toHaveText('Open')
  })
})
