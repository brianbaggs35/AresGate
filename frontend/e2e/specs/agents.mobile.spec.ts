import { expect, test, turnOnAi } from '../support'

test.describe('agents on a phone', () => {
  test.beforeEach(async ({ harness, aiSettings, agents }) => {
    await harness.createIncidents([
      { address: '93.184.216.34', severity: 'high', programs: ['wazuh', 'opnsense'], signals: 4 },
    ])
    await turnOnAi(harness, aiSettings)
    await agents.goto()
    await agents.kinds.first().getByTestId('agents-kind-make').click()
    await agents.save.click()
    await expect(agents.dialog).toHaveCount(0)
    await agents.cards.first().getByTestId('agent-run').click()
    await expect(agents.cards.first().getByTestId('agent-state')).toContainText('Waiting to start')
    await harness.runAgents()
  })

  test('fits the screen, with no sideways scroll, on the list and on the page of one', async ({
    agents,
    page,
  }) => {
    const overflow = () =>
      page.evaluate(
        () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
      )
    await expect(agents.cards.first().getByTestId('agent-outcome')).toContainText('1 finding', {
      timeout: 15_000,
    })
    expect(await overflow()).toBeLessThanOrEqual(0)

    await agents.cards.first().getByTestId('agent-open').click()
    await expect(agents.runStatus).toHaveText('Finished')
    expect(await overflow()).toBeLessThanOrEqual(0)
  })

  test('draws the graph from top to bottom, one step under another', async ({ agents }) => {
    await agents.cards.first().getByTestId('agent-open').click()
    await expect(agents.nodes).toHaveCount(4)

    const [first, second] = await Promise.all([
      agents.nodes.nth(0).boundingBox(),
      agents.nodes.nth(1).boundingBox(),
    ])
    expect(first).not.toBeNull()
    expect(second).not.toBeNull()
    expect(second!.y).toBeGreaterThan(first!.y + first!.height - 1)
    expect(Math.abs(second!.x - first!.x)).toBeLessThan(2)
  })
})
