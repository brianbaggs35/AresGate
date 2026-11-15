import { expect, test } from '../support'

/** What the browser and the API say to each other about the dashboard's numbers: the answer comes
 * with a tag, a poll that names it gets no body while it is still the answer, and a change that
 * was made shows at once instead of when the seconds that an answer is kept for have passed. */
test.describe('the dashboard answer', () => {
  test('is sent with a tag, and a poll that names it is told nothing is new', async ({
    dashboard,
    page,
  }) => {
    await dashboard.goto()

    const first = await page.request.get('/api/dashboard')
    const etag = first.headers()['etag'] ?? ''
    expect(first.status()).toBe(200)
    // Nginx compresses a body this size and so marks its tag as weak (W/), which is still a tag.
    expect(etag).toMatch(/^(W\/)?"[0-9a-f]{32}"$/)
    expect(first.headers()['cache-control']).toBe('private, no-cache')

    const again = await page.request.get('/api/dashboard', { headers: { 'If-None-Match': etag } })
    expect(again.status()).toBe(304)
    expect(await again.text()).toBe('')
    expect(again.headers()['etag']).toBe(etag)
  })

  test('shows what the person just changed on the very next poll', async ({
    harness,
    dashboard,
    page,
  }) => {
    await harness.createActivity({ collectors: ['ok'] })
    await dashboard.goto()
    const first = await page.request.get('/api/dashboard')
    const etag = first.headers()['etag'] ?? ''

    await harness.createActivity({ alerts: { high: 2 } })

    const next = await page.request.get('/api/dashboard', { headers: { 'If-None-Match': etag } })
    expect(next.status()).toBe(200)
    expect(next.headers()['etag']).not.toBe(etag)
    const body = (await next.json()) as { alerts: { total: number } }
    expect(body.alerts.total).toBe(2)
  })

  test('is not given to someone who is not signed in', async ({ request }) => {
    const signedOut = await request.get('/api/dashboard', { headers: { 'If-None-Match': '*' } })

    expect(signedOut.status()).toBe(401)
    expect(signedOut.headers()['etag']).toBeUndefined()
  })
})
