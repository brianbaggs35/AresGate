import type { Page } from '@playwright/test'

import { expect, test } from '../support'

/** The list as it is after VirusTotal's connection has been tested, which is when the search is offered. */
async function showVirusTotalConnected(page: Page) {
  await page.route('**/api/integrations', async (route) => {
    const response = await route.fetch()
    const body = (await response.json()) as { key: string; status: string }[]
    for (const item of body) {
      if (item.key === 'virustotal') item.status = 'connected'
    }
    await route.fulfill({ status: response.status(), json: body })
  })
}

/** An answer about example.com that no engine flagged, as the API gives one. */
function answer(overrides: Record<string, unknown> = {}) {
  return {
    kind: 'domain',
    subject: 'example.com',
    judgement: 'clean',
    checked_at: '2026-11-09T12:00:00Z',
    cached: false,
    stale: false,
    notice: null,
    repeatable: true,
    first_checked_at: '2026-11-02T08:00:00Z',
    checks: 1,
    fresh_until: '2026-11-16T12:00:00Z',
    changed_at: null,
    previous_judgement: null,
    analysed_at: '2026-11-08T09:30:00Z',
    malicious: 0,
    suspicious: 0,
    harmless: 70,
    undetected: 12,
    reputation: 4,
    categories: [],
    details: [],
    link: 'https://www.virustotal.com/gui/domain/example.com',
    ...overrides,
  }
}

const FLAGGED = answer({
  kind: 'ip',
  subject: '203.0.113.9',
  judgement: 'malicious',
  cached: true,
  malicious: 5,
  suspicious: 1,
  harmless: 60,
  undetected: 18,
  reputation: -20,
  link: 'https://www.virustotal.com/gui/ip-address/203.0.113.9',
})

test.describe('threat intelligence page', () => {
  test('is in the menu, and says an integration must be connected before it can search', async ({
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
      'needs at least one threat intelligence integration connected',
    )
    await expect(
      page.getByRole('textbox', { name: 'IP address, domain or web address', exact: true }),
    ).toHaveCount(0)

    await page.getByRole('link', { name: 'Go to Integrations' }).click()

    await expect(page).toHaveURL('/integrations')
    await expect(page.getByTestId('page-heading')).toHaveText('Integrations')
  })

  test('looks a domain up and shows what VirusTotal says in a window, then says when a search must wait', async ({
    page,
    shell,
  }) => {
    await showVirusTotalConnected(page)
    const searched: string[] = []
    await page.route('**/api/threat-intel/lookups', async (route) => {
      const sent = route.request().postDataJSON() as { subject: string }
      searched.push(sent.subject)
      if (sent.subject === 'example.com') {
        await route.fulfill({
          json: answer({
            categories: ['software/cloud services'],
            details: [{ label: 'Registrar', value: 'Example Registrar' }],
          }),
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
    await expect(report.locator('[data-test="report-cached"]')).toHaveCount(0)
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

    await expect(panel.locator('[data-test="threat-notice"]')).toContainText(
      'Try again in 15 seconds.',
    )
    await expect(panel.locator('[data-test="threat-problem"]')).toHaveCount(0)
    await expect(report).toBeHidden()
    expect(searched).toEqual(['example.com', '203.0.113.9'])
  })

  test('says when a search was answered from what AresGate kept, and so sent nothing to VirusTotal', async ({
    page,
    shell,
  }) => {
    await showVirusTotalConnected(page)
    let answered = 0
    await page.route('**/api/threat-intel/lookups', async (route) => {
      answered += 1
      await route.fulfill({ json: answer({ cached: answered > 1 }) })
    })

    await page.goto('/')
    await shell.dashboardLink.waitFor()
    await shell.goTo('threat-intelligence')

    const panel = page.locator('[data-test="threat-lookup"]')
    const report = page.locator('[data-test="threat-report"]')
    const subject = panel.getByRole('textbox', {
      name: 'IP address, domain or web address',
      exact: true,
    })
    await subject.fill('example.com')
    await panel.getByRole('button', { name: 'Search' }).click()
    await expect(report).toBeVisible()
    await expect(report.locator('[data-test="report-cached"]')).toHaveCount(0)
    await report.getByRole('button', { name: 'Done' }).click()
    await expect(report).toBeHidden()

    await subject.fill('example.com')
    await panel.getByRole('button', { name: 'Search' }).click()

    await expect(report).toBeVisible()
    await expect(report.locator('[data-test="report-cached"]')).toContainText(
      'nothing was sent to VirusTotal',
    )
    expect(answered).toBe(2)
  })

  test('lists what AresGate has kept, narrows it, and checks an answer again from its report', async ({
    page,
    shell,
  }) => {
    await showVirusTotalConnected(page)
    const asked: string[] = []
    await page.route('**/api/threat-intel/subjects**', async (route) => {
      const query = new URL(route.request().url()).searchParams
      asked.push(query.toString())
      const kept = [FLAGGED, answer({ cached: true })]
      const items = kept.filter(
        (item) =>
          (!query.get('judgement') || item.judgement === query.get('judgement')) &&
          item.subject.includes(query.get('q') ?? ''),
      )
      await route.fulfill({
        json: {
          total: items.length,
          counts: { malicious: 1, suspicious: 0, clean: 1, unknown: 0 },
          items,
        },
      })
    })
    const sent: { subject: string; refresh?: boolean }[] = []
    await page.route('**/api/threat-intel/lookups', async (route) => {
      sent.push(route.request().postDataJSON() as { subject: string; refresh?: boolean })
      await route.fulfill({
        json: { ...FLAGGED, cached: false, checks: 2, checked_at: '2026-11-10T12:00:00Z' },
      })
    })

    await page.goto('/')
    await shell.dashboardLink.waitFor()
    await shell.goTo('threat-intelligence')

    const known = page.locator('[data-test="threat-known"]')
    const rows = known.locator('[data-test="known-row"]')
    await expect(known.getByRole('heading', { name: 'What AresGate knows' })).toBeVisible()
    await expect(rows).toHaveCount(2)
    await expect(rows.first()).toContainText('203.0.113.9')
    await expect(rows.first()).toContainText('6 of 84 flagged')
    await expect(known.getByRole('button', { name: 'All 2' })).toHaveAttribute(
      'aria-pressed',
      'true',
    )

    await known.getByRole('button', { name: 'Clean 1' }).click()
    await expect(rows).toHaveCount(1)
    await expect(rows.first()).toContainText('example.com')

    await known.getByRole('button', { name: 'All 2' }).click()
    await known.getByRole('textbox', { name: 'Find in what is kept' }).fill('203.0')
    await known.getByRole('button', { name: 'Find', exact: true }).click()
    await expect(rows).toHaveCount(1)
    expect(asked.at(-1)).toBe('q=203.0&limit=25')

    await known
      .getByRole('button', { name: '203.0.113.9, IP address, Malicious. Open its report.' })
      .click()
    const report = page.locator('[data-test="threat-report"]')
    await expect(report).toBeVisible()
    await expect(report.locator('[data-test="report-judgement"]')).toHaveText(
      'Reported as malicious',
    )
    await expect(report.locator('[data-test="report-checks"]')).toHaveText('Once')

    await report.getByRole('button', { name: 'Check again' }).click()

    await expect(report.locator('[data-test="report-checks"]')).toHaveText('2 times')
    await expect(report.locator('[data-test="report-asked"]')).toContainText(
      'AresGate kept the answer',
    )
    expect(sent).toEqual([{ subject: '203.0.113.9', refresh: true }])
  })

  test('shows the answer kept, and why it is old, when a limit holds a search', async ({
    page,
    shell,
  }) => {
    await showVirusTotalConnected(page)
    await page.route('**/api/threat-intel/lookups', async (route) => {
      await route.fulfill({
        json: answer({
          cached: true,
          stale: true,
          notice: "VirusTotal's daily limit is reached. Searches resume at 00:00 UTC.",
        }),
      })
    })

    await page.goto('/')
    await shell.dashboardLink.waitFor()
    await shell.goTo('threat-intelligence')

    const panel = page.locator('[data-test="threat-lookup"]')
    await panel
      .getByRole('textbox', { name: 'IP address, domain or web address', exact: true })
      .fill('example.com')
    await panel.getByRole('button', { name: 'Search' }).click()

    const report = page.locator('[data-test="threat-report"]')
    await expect(report.locator('[data-test="report-notice"]')).toContainText(
      "VirusTotal's daily limit is reached. Searches resume at 00:00 UTC. This is the answer AresGate kept.",
    )
    await expect(report.locator('[data-test="report-cached"]')).toContainText(
      'It is due to be checked again.',
    )
    await expect(panel.locator('[data-test="threat-problem"]')).toHaveCount(0)
  })

  test('says nothing is kept yet before the first answer', async ({ page, shell }) => {
    await page.goto('/')
    await shell.dashboardLink.waitFor()
    await shell.goTo('threat-intelligence')

    await expect(page.locator('[data-test="known-empty"]')).toContainText('Nothing is kept yet')
  })

  test("says when VirusTotal's daily limit holds searches, and that this is not a failure", async ({
    page,
    shell,
  }) => {
    // The list as it is while VirusTotal's daily quota is used up: the key is still connected.
    await page.route('**/api/integrations', async (route) => {
      const response = await route.fetch()
      const body = (await response.json()) as {
        key: string
        status: string
        pause: { until: string; daily: boolean } | null
      }[]
      for (const item of body) {
        if (item.key === 'virustotal') {
          item.status = 'connected'
          item.pause = { until: '2099-01-01T00:00:00Z', daily: true }
        }
      }
      await route.fulfill({ status: response.status(), json: body })
    })

    await page.goto('/')
    await shell.dashboardLink.waitFor()
    await shell.goTo('threat-intelligence')

    const panel = page.locator('[data-test="threat-lookup"]')
    await expect(panel.locator('[data-test="threat-notice"]')).toContainText(
      "VirusTotal's daily limit is reached. Searches resume at 00:00 UTC.",
    )
    await expect(panel.locator('[data-test="threat-problem"]')).toHaveCount(0)
  })
})
