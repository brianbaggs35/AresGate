import type { IncidentRequest } from '../support'
import { expect, expectAccessible, test } from '../support'

const ATTACKER = '93.184.216.34'
const DEVICE = '192.168.1.20'

/** An attack that the firewall turned away, Suricata stopped alerts of and Wazuh saw on the device. */
const SEEN: IncidentRequest = {
  address: ATTACKER,
  severity: 'high',
  programs: ['opnsense', 'wazuh'],
  signals: 4,
  blocks: 3,
  dropped: 2,
  minutes_ago: 5,
  device: DEVICE,
  device_name: 'Kitchen camera',
}

async function openIncident(page: import('@playwright/test').Page): Promise<void> {
  await page.goto('/incidents?view=all')
  await page.getByTestId('incident').filter({ hasText: ATTACKER }).click()
  await expect(page).toHaveURL(/\/incidents\/\d+$/)
}

test.describe('how an incident travelled', () => {
  test('draws the programs that saw it between the internet and the device', async ({
    harness,
    page,
  }) => {
    await harness.createIncidents([SEEN])

    await openIncident(page)

    const card = page.getByTestId('path-card')
    await expect(card).toBeVisible()
    await expect(card.getByTestId('path-lead')).toContainText('It came in from the internet')
    const stops = card.getByTestId('path-hop')
    await expect(stops.first()).toHaveAttribute('data-kind', 'internet')
    await expect(stops.last()).toHaveAttribute('data-kind', 'device')
    await expect(stops.first().getByTestId('hop-subject')).toHaveText(ATTACKER)
    // The test server's resolver gives this address a name, and the page says where it came from.
    await expect(stops.first().getByTestId('hop-name')).toHaveText('scanner-17.example.net')
    await expect(card.getByTestId('hop-note').first()).toContainText('Turned it away')
  })

  test('fits the screen and has no accessibility violations', async ({ harness, page }) => {
    await harness.createIncidents([SEEN])

    await openIncident(page)

    await expect(page.getByTestId('path-card')).toBeVisible()
    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
    )
    expect(overflow).toBeLessThanOrEqual(0)
    await expectAccessible(page)
  })
})

test.describe('an alert two programs reported, on the Logs page', () => {
  test('says which other programs reported it, and that the repeat is the same alert', async ({
    harness,
    page,
  }) => {
    const flow = {
      kind: 'alert',
      severity: 'high' as const,
      signature: 'ET SCAN Potential SSH Scan',
      summary: 'ET SCAN Potential SSH Scan',
      src_address: ATTACKER,
      dst_address: DEVICE,
      dst_port: 22,
      protocol: 'tcp',
    }
    await harness.createEvents([
      { ...flow, source: 'opnsense', seconds_ago: 90 },
      { ...flow, source: 'wazuh', seconds_ago: 88 },
    ])

    await page.goto('/logs')

    const rows = page.getByTestId(/^log-(row|card)$/)
    await expect(rows).toHaveCount(2)
    // The newest is Wazuh's report, which repeats OPNsense's.
    await rows.first().click()
    await expect(page.getByTestId('drawer-agreement')).toContainText(
      'The same alert as one already reported by another program',
    )
    await page.getByTestId('drawer-close').click()
    await rows.last().click()
    await expect(page.getByTestId('drawer-agreement')).toContainText('Also reported by Wazuh')
  })
})
