import { expect, IntegrationPage, test } from '../support'

const TOKEN = 'a-valid-ntopng-token'

test.describe('status page', () => {
  test('opens from the menu', async ({ page, shell, status }) => {
    await page.goto('/')

    await shell.statusLink.click()

    await expect(page).toHaveURL('/status')
    await expect(page).toHaveTitle('Status · AresGate')
    await expect(status.heading).toHaveText('Status')
    await expect(shell.statusLink).toHaveAttribute('aria-current', 'page')
    await expect(status.aresgate).toBeVisible()
  })

  test('says what is running, and that the database is where it should be', async ({ status }) => {
    await status.goto()

    await expect(status.fine).toHaveText('Everything checks out.')
    await expect(status.fact('version')).toHaveText(/^\d+\.\d+\.\d+/)
    await expect(status.fact('environment')).toHaveText('test')
    await expect(status.fact('uptime')).toHaveText(/^(\d+d )?(\d+h )?\d+m$/)
    await expect(status.fact('python')).toHaveText(/^3\.\d+\.\d+$/)
    await expect(status.fact('database')).toHaveText(/^\d+(\.\d+)?$/)
    await expect(status.fact('migration')).toHaveText(/ \(up to date\)$/)
    await expect(status.fact('clock')).toHaveText('In step with this computer')
    await expect(status.meters.first()).toBeVisible()
  })

  test('lists the integrations as parts, and opens one', async ({ page, status }) => {
    await status.goto()

    await expect(status.partNames).toHaveText(['OPNsense', 'ntopng', 'Wazuh', 'CrowdSec'])
    await expect(status.partStates).toHaveText(['Off', 'Off', 'Off', 'Off'])
    await expect(status.part('Wazuh')).toContainText('Not connected.')

    await status.part('Wazuh').getByRole('link', { name: 'Open Wazuh' }).click()

    await expect(page).toHaveURL('/integrations/wazuh')
  })

  test('shows a part that works, and one with a problem, and asks again on request', async ({
    harness,
    integration,
    status,
  }) => {
    const ntopng = await harness.standIn({ kind: 'ntopng', token: TOKEN })
    await integration.goto('ntopng')
    await integration.address('api').fill(ntopng.url)
    await integration.field('api', 'token').fill(TOKEN)
    await integration.save.click()
    await expect(integration.status).toHaveText('Connected')

    await status.goto()

    await expect(status.part('ntopng').getByTestId('part-state')).toHaveText('Working')
    await expect(status.part('ntopng')).toContainText('Last worked just now')
    await expect(status.fine).toBeVisible()

    // Then the token stops working, as if it had been changed on the ntopng side.
    await integration.goto('ntopng')
    await integration.field('api', 'token').fill('the wrong token')
    await integration.save.click()
    await expect(integration.status).toHaveText('Problem')
    await status.goto()

    await expect(status.part('ntopng').getByTestId('part-state')).toHaveText('Problem')
    await expect(status.attentionItems).toHaveText(['ntopng has a problem.'])
    await expect(status.fine).toHaveCount(0)
  })

  test('refreshes in place', async ({ page, harness, status }) => {
    await status.goto()
    await expect(status.part('ntopng').getByTestId('part-state')).toHaveText('Off')
    const ntopng = await harness.standIn({ kind: 'ntopng', token: TOKEN })
    // Another browser connects it meanwhile.
    const elsewhere = await page.context().newPage()
    const there = new IntegrationPage(elsewhere)
    await there.goto('ntopng')
    await there.address('api').fill(ntopng.url)
    await there.field('api', 'token').fill(TOKEN)
    await there.save.click()
    await expect(there.status).toHaveText('Connected')
    await elsewhere.close()

    await status.refresh.click()

    await expect(status.part('ntopng').getByTestId('part-state')).toHaveText('Working')
  })

  test('has the text for a bug report, which leaves out where things are', async ({
    harness,
    integration,
    status,
  }) => {
    const ntopng = await harness.standIn({ kind: 'ntopng', token: TOKEN })
    await integration.goto('ntopng')
    await integration.address('api').fill(ntopng.url)
    await integration.field('api', 'token').fill('the wrong token')
    await integration.save.click()
    await expect(integration.status).toHaveText('Problem')

    await status.goto()

    await expect(status.diagnostics).toContainText('AresGate diagnostics')
    await expect(status.diagnostics).toContainText('- ntopng: problem')
    const text = (await status.diagnostics.textContent()) ?? ''
    expect(text).not.toContain('127.0.0.1')
  })

  test('copies the text for a bug report', async ({ context, page, status }) => {
    await context.grantPermissions(['clipboard-read', 'clipboard-write'])
    await status.goto()
    await expect(status.diagnostics).toBeVisible()

    await status.copy.click()

    await expect(status.copied).toHaveText('Copied.')
    const copied = await page.evaluate(() => navigator.clipboard.readText())
    expect(copied).toBe(await status.diagnostics.textContent())
  })

  test('says to copy it by hand when the browser would not', async ({ page, status }) => {
    await status.goto()
    await expect(status.diagnostics).toBeVisible()
    await page.evaluate(() => {
      Object.defineProperty(navigator, 'clipboard', {
        value: { writeText: () => Promise.reject(new Error('Not allowed')) },
        configurable: true,
      })
    })

    await status.copy.click()

    await expect(status.copyFailed).toContainText('copy it yourself')
    await expect(status.copied).toHaveCount(0)
  })

  test('says why the status can’t be read, and tries again', async ({ page, status }) => {
    let fail = true
    await page.route('**/api/status', (route) => (fail ? route.abort() : route.continue()))
    await status.goto()
    await expect(status.loadError).toContainText("Can't reach AresGate.")
    await expect(status.aresgate).toHaveCount(0)

    fail = false
    await status.retry.click()

    await expect(status.loadError).toHaveCount(0)
    await expect(status.aresgate).toBeVisible()
  })

  test('sends you to sign in when the sign-in has ended', async ({ page, status, harness }) => {
    await status.goto()
    await expect(status.aresgate).toBeVisible()
    // Cleaning the database ends every sign-in, as the idle limit would.
    await harness.clean()

    await status.refresh.click()

    await expect(page).toHaveURL('/sign-in?next=/status')
  })
})
