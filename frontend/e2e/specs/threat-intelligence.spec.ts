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
    provider: 'virustotal',
    provider_name: 'VirusTotal',
    kind: 'domain',
    subject: 'example.com',
    judgement: 'clean',
    reported_judgement: 'clean',
    ruling: null,
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
  reported_judgement: 'malicious',
  cached: true,
  malicious: 5,
  suspicious: 1,
  harmless: 60,
  undetected: 18,
  reputation: -20,
  link: 'https://www.virustotal.com/gui/ip-address/203.0.113.9',
})

/** The list as it is after AlienVault OTX's connection has been tested. */
async function showOtxConnected(page: Page) {
  await page.route('**/api/integrations', async (route) => {
    const response = await route.fetch()
    const body = (await response.json()) as { key: string; status: string }[]
    for (const item of body) {
      if (item.key === 'otx') item.status = 'connected'
    }
    await route.fulfill({ status: response.status(), json: body })
  })
}

test.describe('threat intelligence page', () => {
  test('has a tab for each kind of threat intelligence, and says on a tab that no connected service answers that it needs connecting', async ({
    page,
    shell,
  }) => {
    await page.goto('/')
    await shell.dashboardLink.waitFor()
    await shell.goTo('threat-intelligence')

    await expect(page.getByRole('tab')).toHaveText([
      'IP addresses',
      'Domains',
      'Web addresses',
      'CVEs',
      'Devices',
    ])

    await page.getByRole('tab', { name: 'Web addresses' }).click()

    await expect(page.getByTestId('threat-intelligence-setup')).toContainText(
      'No service is connected for this',
    )
    await expect(page.getByTestId('threat-intelligence-setup')).toContainText(
      'VirusTotal answers searches for a web address',
    )
    await expect(page.locator('[data-test="threat-known"]')).toContainText(
      'Every answer the services gave about web addresses is kept here',
    )
  })

  test('searches AlienVault OTX for an address from the IP addresses tab and reports the pulses that name it', async ({
    page,
    shell,
  }) => {
    await showOtxConnected(page)
    const sent: { provider: string; subject: string; kind: string }[] = []
    await page.route('**/api/threat-intel/lookups', async (route) => {
      sent.push(
        route.request().postDataJSON() as { provider: string; subject: string; kind: string },
      )
      await route.fulfill({
        json: answer({
          provider: 'otx',
          provider_name: 'AlienVault OTX',
          kind: 'ip',
          subject: '203.0.113.9',
          judgement: 'malicious',
          reported_judgement: 'malicious',
          malicious: 2,
          suspicious: 1,
          harmless: 0,
          undetected: 0,
          reputation: -3,
          details: [{ label: 'Pulses', value: '3' }],
          link: 'https://otx.alienvault.com/indicator/ip/203.0.113.9',
        }),
      })
    })

    await page.goto('/')
    await shell.dashboardLink.waitFor()
    await shell.goTo('threat-intelligence')

    // The IP addresses tab opens first, and searches every connected service that answers there.
    const panel = page.locator('[data-test="threat-lookup"]')
    await panel.getByRole('textbox', { name: 'IP address', exact: true }).fill('203.0.113.9')
    await panel.getByRole('button', { name: 'Search' }).click()

    const report = page.locator('[data-test="threat-report"]')
    await expect(report.locator('[data-test="report-kind"]')).toHaveText(
      'AlienVault OTX · IP address',
    )
    await expect(report.locator('[data-test="report-summary"]')).toContainText(
      '3 pulses name it, 2 of them also naming malware',
    )
    await expect(report.locator('[data-test="report-bar"]')).toHaveCount(0)
    await expect(report.getByRole('link', { name: 'Open in AlienVault OTX' })).toHaveAttribute(
      'href',
      'https://otx.alienvault.com/indicator/ip/203.0.113.9',
    )
    expect(sent).toEqual([{ provider: 'otx', subject: '203.0.113.9', kind: 'ip' }])
  })

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
      'VirusTotal, AlienVault OTX, and GreyNoise answer searches for an IP address',
    )
    await expect(page.getByRole('textbox', { name: 'IP address', exact: true })).toHaveCount(0)

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
    await page.getByRole('tab', { name: 'Domains' }).click()

    const panel = page.locator('[data-test="threat-lookup"]')
    const report = page.locator('[data-test="threat-report"]')
    await panel.getByRole('textbox', { name: 'Domain', exact: true }).fill('example.com')
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

    await panel.getByRole('textbox', { name: 'Domain', exact: true }).fill('203.0.113.9')
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
    await page.getByRole('tab', { name: 'Domains' }).click()

    const panel = page.locator('[data-test="threat-lookup"]')
    const report = page.locator('[data-test="threat-report"]')
    const subject = panel.getByRole('textbox', { name: 'Domain', exact: true })
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
    const sent: { provider: string; subject: string; kind: string; refresh?: boolean }[] = []
    await page.route('**/api/threat-intel/lookups', async (route) => {
      sent.push(
        route.request().postDataJSON() as {
          provider: string
          subject: string
          kind: string
          refresh?: boolean
        },
      )
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
    expect(asked.at(-1)).toBe('q=203.0&kind=ip&limit=25')

    await known
      .getByRole('button', {
        name: '203.0.113.9, VirusTotal: Malicious, 6 of 84 flagged. Open its report.',
      })
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
    expect(sent).toEqual([
      { provider: 'virustotal', subject: '203.0.113.9', kind: 'ip', refresh: true },
    ])
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
    await page.getByRole('tab', { name: 'Domains' }).click()

    const panel = page.locator('[data-test="threat-lookup"]')
    await panel.getByRole('textbox', { name: 'Domain', exact: true }).fill('example.com')
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

  test('lists what NVD says of the CVEs that incidents name, and opens one as a report', async ({
    page,
    shell,
  }) => {
    const exploited = {
      cve_id: 'CVE-2024-3400',
      state: 'found',
      checked_at: '2026-11-14T08:00:00Z',
      status: 'Analyzed',
      published_at: '2024-04-12T08:15:06Z',
      modified_at: '2026-10-02T10:00:00Z',
      cvss_version: '3.1',
      score: 10,
      rating: 'critical',
      vector: 'CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:C/C:H/I:H/A:H',
      description: 'A command injection in the GlobalProtect feature of PAN-OS.',
      weaknesses: ['CWE-77'],
      exploited: true,
      exploited_on: '2024-04-12',
      action_due: '2024-04-19',
      required_action: 'Apply the mitigations the vendor lists.',
      kev_name: 'Palo Alto Networks PAN-OS Command Injection Vulnerability',
      link: 'https://nvd.nist.gov/vuln/detail/CVE-2024-3400',
    }
    const quiet = {
      ...exploited,
      cve_id: 'CVE-2023-1234',
      score: 5.4,
      rating: 'medium',
      exploited: false,
      kev_name: null,
      description: 'A cross-site scripting flaw.',
    }
    const asked: string[] = []
    await page.route('**/api/threat-intel/cves**', async (route) => {
      const query = new URL(route.request().url()).searchParams
      asked.push(query.toString())
      const items = [exploited, quiet].filter(
        (item) => query.get('exploited') !== 'true' || item.exploited,
      )
      await route.fulfill({
        json: {
          notice:
            'This product uses data from the NVD API but is not endorsed or certified by the NVD.',
          total: items.length,
          counts: { critical: 1, high: 0, medium: 1, low: 0, unrated: 0, exploited: 1 },
          items,
        },
      })
    })

    await page.goto('/')
    await shell.dashboardLink.waitFor()
    await shell.goTo('threat-intelligence')
    await page.getByRole('tab', { name: 'CVEs' }).click()

    const cves = page.locator('[data-test="threat-cves"]')
    const rows = cves.locator('[data-test="cves-row"]')
    await expect(rows).toHaveCount(2)
    await expect(rows.first()).toContainText('CVE-2024-3400')
    await expect(rows.first()).toContainText('Exploited in the wild')
    await expect(cves.locator('[data-test="cves-notice"]')).toContainText(
      'This product uses data from the NVD API',
    )

    await cves.getByRole('button', { name: 'Exploited in the wild 1' }).click()
    await expect(rows).toHaveCount(1)
    expect(asked.at(-1)).toBe('exploited=true&limit=25')

    await rows.first().click()
    const report = page.locator('[data-test="cve-dialog"]')
    await expect(report.getByRole('heading', { name: 'CVE-2024-3400' })).toBeVisible()
    await expect(report.locator('[data-test="cve-kev"]')).toContainText(
      'Apply the mitigations the vendor lists.',
    )
    await expect(report.getByRole('link', { name: 'View on NVD' })).toHaveAttribute(
      'href',
      'https://nvd.nist.gov/vuln/detail/CVE-2024-3400',
    )
    await report.getByRole('button', { name: 'Done' }).click()
    await expect(report).toBeHidden()
  })

  test('lists what Fingerbank made of each device, and says why one was not asked about', async ({
    page,
    shell,
  }) => {
    const camera = {
      device_id: 7,
      mac: '3c:5a:b4:00:00:01',
      hostname: 'driveway-cam',
      vendor: 'Google, Inc.',
      address: '192.168.1.50',
      state: 'identified',
      reason: 'asset',
      name: 'Nest Cam',
      path: 'Hardware Manufacturer/Google/Camera',
      manufacturer: 'Google',
      operating_system: 'Linux OS',
      score: 87,
      checked_at: '2026-11-14T08:00:00Z',
      last_seen_at: '2026-11-15T08:00:00Z',
    }
    const phone = {
      ...camera,
      device_id: 8,
      mac: 'da:a1:19:00:00:02',
      hostname: null,
      vendor: null,
      address: null,
      state: 'private',
      reason: 'incident',
      name: null,
      path: null,
      manufacturer: null,
      operating_system: null,
      score: null,
    }
    await page.route('**/api/threat-intel/devices**', async (route) => {
      const query = new URL(route.request().url()).searchParams
      const items = [camera, phone].filter(
        (item) => !query.get('state') || item.state === query.get('state'),
      )
      await route.fulfill({
        json: {
          total: items.length,
          counts: { identified: 1, unknown: 0, private: 1 },
          items,
        },
      })
    })

    await page.goto('/')
    await shell.dashboardLink.waitFor()
    await shell.goTo('threat-intelligence')
    await page.getByRole('tab', { name: 'Devices' }).click()

    const devices = page.locator('[data-test="threat-devices"]')
    const rows = devices.locator('[data-test="devices-row"]')
    await expect(rows).toHaveCount(2)
    await expect(rows.first()).toContainText('Nest Cam')
    await expect(rows.first()).toContainText('87% sure')
    await expect(rows.first()).toContainText('Linux OS')
    await expect(rows.last()).toContainText('Private address')
    await expect(rows.last()).toContainText('Fingerbank was not asked')

    await devices.getByRole('button', { name: 'Private address 1' }).click()
    await expect(rows).toHaveCount(1)
    await expect(rows.first()).toContainText('da:a1:19:00:00:02')
  })
})
