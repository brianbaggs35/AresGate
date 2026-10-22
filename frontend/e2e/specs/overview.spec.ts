import { expect, test } from '../support'

test.describe('overview', () => {
  test('shows that the API and the database are up', async ({ page, overview }) => {
    await overview.goto()

    await expect(page).toHaveTitle('Overview · AresGate')
    await expect(overview.apiStatus).toHaveText('API: Running')
    await expect(overview.databaseStatus).toHaveText('Database: Connected')
  })

  test('asks the API again when told to', async ({ page, overview }) => {
    await overview.goto()
    await expect(overview.apiStatus).toHaveText('API: Running')

    const [request] = await Promise.all([
      page.waitForRequest('**/api/health'),
      overview.refresh.click(),
    ])

    expect(request.method()).toBe('GET')
    await expect(overview.apiStatus).toHaveText('API: Running')
  })

  test('says so when the API reports the database as unavailable', async ({ page, overview }) => {
    await page.route('**/api/health', (route) =>
      route.fulfill({ status: 503, json: { status: 'degraded', database: 'unavailable' } }),
    )

    await overview.goto()

    await expect(overview.apiStatus).toHaveText('API: Running')
    await expect(overview.databaseStatus).toHaveText('Database: Unavailable')
  })

  test('says so when the API cannot be reached', async ({ page, overview }) => {
    await page.route('**/api/health', (route) => route.abort())

    await overview.goto()

    await expect(overview.apiStatus).toHaveText('API: Unreachable')
    await expect(overview.databaseStatus).toHaveText('Database: Unknown')
  })
})
