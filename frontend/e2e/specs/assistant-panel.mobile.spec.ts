import type { IncidentRequest } from '../support'
import { expect, test, turnOnAi } from '../support'

const SCAN: IncidentRequest = {
  address: '93.184.216.34',
  severity: 'high',
  programs: ['wazuh', 'opnsense'],
  signals: 4,
  minutes_ago: 4,
}

// Only a phone has the sheet.
test.describe('the assistant panel on a phone', () => {
  test('is a sheet on a phone that keeps the box above the keyboard, and can be closed', async ({
    harness,
    aiSettings,
    assistantPanel,
    page,
  }) => {
    await harness.createIncidents([SCAN])
    await turnOnAi(harness, aiSettings)
    await page.goto('/')
    await assistantPanel.opener.click()

    await expect(assistantPanel.panel).toBeVisible()
    const view = page.viewportSize()
    const box = await assistantPanel.input.boundingBox()
    expect(box).not.toBeNull()
    expect(box!.y + box!.height).toBeLessThanOrEqual(view!.height)

    // A way back to the page that does not hide the app's own controls for good.
    await assistantPanel.close.click()
    await expect(assistantPanel.panel).toBeHidden()
    await expect(page.getByTestId('nav-more')).toBeVisible()
  })
})
