import type { IncidentRequest } from '../support'
import { expect, test } from '../support'

const ADDRESS = '93.184.216.34'

/** A scan that tried an exploit of a CVE, which the alerts name. */
const EXPLOIT: IncidentRequest = {
  address: ADDRESS,
  severity: 'high',
  programs: ['wazuh'],
  signals: 2,
  cve: 'CVE-2021-44228',
  minutes_ago: 5,
}

test.describe('the vulnerabilities an incident names', () => {
  test('lists a CVE its alerts name, and says NVD has not been asked yet', async ({
    harness,
    page,
  }) => {
    await harness.createIncidents([EXPLOIT])

    await page.goto('/incidents?view=all')
    await page.getByTestId('incident').filter({ hasText: ADDRESS }).click()
    await expect(page).toHaveURL(/\/incidents\/\d+$/)

    const card = page.getByTestId('vulnerabilities-card')
    await expect(card).toBeVisible()
    await expect(card.getByTestId('section-title')).toHaveText('Vulnerabilities it names')
    // Both alerts name it, and it is listed once.
    const item = card.getByTestId('vulnerability-CVE-2021-44228')
    await expect(item).toHaveCount(1)
    await expect(item).toContainText('CVE-2021-44228')
    await expect(item.getByTestId('vulnerability-unsettled')).toHaveText(
      'NVD has not been asked about it yet.',
    )
    await expect(item.getByTestId('vulnerability-link')).toHaveAttribute(
      'href',
      'https://nvd.nist.gov/vuln/detail/CVE-2021-44228',
    )
    await expect(card.getByTestId('nvd-notice')).toContainText('not endorsed or certified')
  })

  test('has no such card for an incident that names none', async ({ harness, page }) => {
    await harness.createIncidents([{ ...EXPLOIT, cve: undefined }])

    await page.goto('/incidents?view=all')
    await page.getByTestId('incident').filter({ hasText: ADDRESS }).click()

    await expect(page.getByTestId('incident-when')).toBeVisible()
    await expect(page.getByTestId('vulnerabilities-card')).toHaveCount(0)
  })
})
