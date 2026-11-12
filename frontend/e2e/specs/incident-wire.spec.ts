import type { Page } from '@playwright/test'

import type { IncidentRequest } from '../support'
import { expect, test } from '../support'

const ADDRESS = '93.184.216.34'

/** A camera calling its cloud: the firewall's intrusion detection read the certificate the
 * service showed (signed by itself), a login sent without encryption and the name it asked for. */
const CAMERA: IncidentRequest = {
  address: ADDRESS,
  severity: 'medium',
  programs: ['opnsense'],
  signals: 3,
  detailed: true,
  wire: true,
  outbound: true,
  minutes_ago: 5,
}

async function openIncident(page: Page): Promise<void> {
  await page.goto('/incidents?view=all')
  await page.getByTestId('incident').filter({ hasText: ADDRESS }).click()
  await expect(page).toHaveURL(/\/incidents\/\d+$/)
}

test.describe('what was said on the wire', () => {
  test('shows the certificate a camera signed itself, with a word on why that is common', async ({
    harness,
    page,
  }) => {
    await harness.createIncidents([CAMERA])

    await openIncident(page)

    const card = page.getByTestId('wire-card')
    await expect(card).toBeVisible()
    await expect(card.getByTestId('wire-note').first()).toContainText('is self-signed')
    await expect(card.getByTestId('wire-note').first()).toContainText('Cameras, doorbells')
    const certificate = card.getByTestId('wire-certificate')
    await expect(certificate.getByTestId('wire-certificate-name')).toHaveText('cloud.example.net')
    await expect(certificate.getByTestId('wire-self-signed')).toBeVisible()
    await expect(certificate).toContainText('TLS 1.2')
    await expect(certificate).toContainText('Good until2035-01-01')
  })

  test('opens the web request and the lookup, and never shows a login', async ({
    harness,
    page,
  }) => {
    await harness.createIncidents([CAMERA])

    await openIncident(page)

    const card = page.getByTestId('wire-card')
    await card.getByTestId('wire-panel-requests').getByRole('button').click()
    await expect(card.getByTestId('wire-request-name')).toHaveText('POST api.example.net/v1/login')
    await expect(card.getByTestId('wire-hidden')).toBeVisible()
    await expect(card).not.toContainText('Y2FtZXJhOnNlY3JldA==')
    await expect(card).toContainText('A login or key went to api.example.net')
    await card.getByTestId('wire-panel-lookups').getByRole('button').click()
    await expect(card.getByTestId('wire-lookup')).toContainText('cloud.example.net → 192.0.2.80')
  })

  test('leaves the section out when no program read any of it', async ({ harness, page }) => {
    await harness.createIncidents([{ ...CAMERA, programs: ['wazuh'] }])

    await openIncident(page)

    await expect(page.getByTestId('insights-card')).toBeVisible()
    await expect(page.getByTestId('wire-card')).toHaveCount(0)
  })
})
