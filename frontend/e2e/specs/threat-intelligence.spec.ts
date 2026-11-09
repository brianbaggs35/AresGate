import { expect, test } from '../support'

test.describe('threat intelligence page', () => {
  test('is in the menu, and says VirusTotal must be set up before it can search', async ({
    page,
    shell,
  }) => {
    await page.goto('/')
    await shell.dashboardLink.waitFor()
    await shell.goTo('threat-intelligence')

    await expect(page).toHaveURL('/threat-intelligence')
    await expect(page).toHaveTitle('Threat intelligence · AresGate')
    await shell.expectCurrent('threat-intelligence')
    await expect(page.getByTestId('page-heading')).toHaveText('Threat intelligence')
    await expect(page.getByTestId('threat-intelligence-setup')).toContainText(
      "VirusTotal isn't set up yet",
    )
    await expect(
      page.getByRole('textbox', { name: 'IP address, domain or web address', exact: true }),
    ).toHaveCount(0)

    await page.getByTestId('threat-intelligence-set-up').click()

    await expect(page).toHaveURL('/integrations/virustotal')
  })

  test('looks a domain up and shows what VirusTotal says in a window, then says when a search must wait', async ({
    page,
    shell,
  }) => {
    // The list as it is after VirusTotal's connection has been tested, which is when the search is offered.
    await page.route('**/api/integrations', async (route) => {
      const response = await route.fetch()
      const body = (await response.json()) as { key: string; status: string }[]
      for (const item of body) {
        if (item.key === 'virustotal') item.status = 'connected'
      }
      await route.fulfill({ status: response.status(), json: body })
    })
    const searched: string[] = []
    await page.route('**/api/threat-intel/lookups', async (route) => {
      const sent = route.request().postDataJSON() as { subject: string }
      searched.push(sent.subject)
      if (sent.subject === 'example.com') {
        await route.fulfill({
          json: {
            kind: 'domain',
            subject: 'example.com',
            judgement: 'clean',
            checked_at: '2026-11-09T12:00:00Z',
            analysed_at: '2026-11-08T09:30:00Z',
            malicious: 0,
            suspicious: 0,
            harmless: 70,
            undetected: 12,
            reputation: 4,
            categories: ['software/cloud services'],
            details: [{ label: 'Registrar', value: 'Example Registrar' }],
            link: 'https://www.virustotal.com/gui/domain/example.com',
          },
        })
        return
      }
      await route.fulfill({
        status: 429,
        headers: { 'Retry-After': '15' },
        json: { detail: "VirusTotal's limit on searches is reached. Try again in 15 seconds." },
      })
    })

    await page.goto('/')
    await shell.dashboardLink.waitFor()
    await shell.goTo('threat-intelligence')

    const panel = page.locator('[data-test="threat-lookup"]')
    const report = page.locator('[data-test="threat-report"]')
    await panel
      .getByRole('textbox', { name: 'IP address, domain or web address', exact: true })
      .fill('example.com')
    await panel.getByRole('button', { name: 'Search' }).click()

    await expect(report).toBeVisible()
    await expect(report.locator('[data-test="report-subject"]')).toHaveText('example.com')
    await expect(report.locator('[data-test="report-judgement"]')).toHaveText(
      'No engine flagged it',
    )
    await expect(report.getByRole('link', { name: 'Open in VirusTotal' })).toHaveAttribute(
      'href',
      'https://www.virustotal.com/gui/domain/example.com',
    )
    await report.getByRole('button', { name: 'Done' }).click()
    await expect(report).toBeHidden()

    await panel
      .getByRole('textbox', { name: 'IP address, domain or web address', exact: true })
      .fill('203.0.113.9')
    await panel.getByRole('button', { name: 'Search' }).click()

    await expect(panel.locator('[data-test="threat-problem"]')).toContainText(
      'Try again in 15 seconds.',
    )
    await expect(report).toBeHidden()
    expect(searched).toEqual(['example.com', '203.0.113.9'])
  })
})
