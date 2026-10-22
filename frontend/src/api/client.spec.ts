import { ApiError, apiGet, errorMessage } from '@/api/client'

function respond(body: unknown, init: ResponseInit = {}) {
  const payload = typeof body === 'string' ? body : JSON.stringify(body)
  vi.mocked(fetch).mockResolvedValue(new Response(payload, init))
}

describe('apiGet', () => {
  it('reads JSON from the API on the same origin', async () => {
    respond({ status: 'ok' })
    await expect(apiGet('/health')).resolves.toEqual({ status: 'ok' })
    expect(fetch).toHaveBeenCalledWith('/api/health', {
      headers: { Accept: 'application/json' },
      credentials: 'same-origin',
    })
  })

  it("uses the API's code and message for a failure", async () => {
    respond({ detail: { code: 'nope', message: 'Not allowed.' } }, { status: 403 })
    const error = await apiGet('/x').catch((caught: unknown) => caught)
    expect(error).toBeInstanceOf(ApiError)
    expect(error).toMatchObject({ status: 403, code: 'nope', message: 'Not allowed.' })
  })

  it.each([
    ['a body that is not JSON', 'oops'],
    ['a body that is not an object', ['x']],
    ['a detail without a code', { detail: { message: 'x' } }],
    ['a detail that is a string', { detail: 'x' }],
  ])('gives a generic message for %s', async (_name, body) => {
    respond(body, { status: 500 })
    const error = await apiGet('/x').catch((caught: unknown) => caught)
    expect(error).toMatchObject({
      status: 500,
      code: 'error',
      message: 'AresGate ran into a problem. Try again in a moment.',
    })
  })

  it('reports an unreachable API as offline', async () => {
    vi.mocked(fetch).mockRejectedValue(new TypeError('Failed to fetch'))
    const error = await apiGet('/x').catch((caught: unknown) => caught)
    expect(error).toMatchObject({ status: 0, code: 'offline' })
  })
})

describe('errorMessage', () => {
  it('uses an error’s message', () => {
    expect(errorMessage(new Error('bad'))).toBe('bad')
  })

  it('stringifies anything else', () => {
    expect(errorMessage('boom')).toBe('boom')
  })
})
