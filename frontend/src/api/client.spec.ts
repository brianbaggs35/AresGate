import { ApiError, apiGet, apiPost, errorMessage } from '@/api/client'

function respond(body: unknown, init: ResponseInit = {}) {
  const payload = typeof body === 'string' ? body : JSON.stringify(body)
  vi.mocked(fetch).mockResolvedValue(new Response(payload, init))
}

const failure = (call: Promise<unknown>) => call.catch((caught: unknown) => caught)

describe('apiGet', () => {
  it('reads JSON from the API on the same origin', async () => {
    respond({ status: 'ok' })
    await expect(apiGet('/health')).resolves.toEqual({ status: 'ok' })
    expect(fetch).toHaveBeenCalledWith('/api/health', {
      headers: { Accept: 'application/json' },
      credentials: 'same-origin',
    })
  })

  it("uses the API's words for a refusal, and names its status", async () => {
    respond({ detail: 'Incorrect username or password.' }, { status: 401 })
    const error = await failure(apiGet('/x'))
    expect(error).toBeInstanceOf(ApiError)
    expect(error).toMatchObject({
      status: 401,
      code: 'unauthenticated',
      message: 'Incorrect username or password.',
    })
  })

  it.each([
    [403, 'forbidden'],
    [404, 'not_found'],
    [409, 'conflict'],
    [422, 'invalid'],
    [429, 'rate_limited'],
    [418, 'error'],
  ])('names a %i failure %s', async (status, code) => {
    respond({ detail: 'No.' }, { status })
    expect(await failure(apiGet('/x'))).toMatchObject({ status, code, message: 'No.' })
  })

  it("doesn't pass on what a server says when it breaks", async () => {
    respond({ detail: 'Traceback: secrets' }, { status: 500 })
    expect(await failure(apiGet('/x'))).toMatchObject({
      status: 500,
      code: 'error',
      message: 'AresGate ran into a problem. Try again in a moment.',
    })
  })

  it('says to check the input when the framework rejects it with a list of problems', async () => {
    respond(
      { detail: [{ loc: ['body', 'code'], msg: 'too long', type: 'string_too_long' }] },
      {
        status: 422,
      },
    )
    expect(await failure(apiGet('/x'))).toMatchObject({
      status: 422,
      code: 'invalid',
      message: "AresGate couldn't use that. Check what you entered and try again.",
    })
  })

  it.each([
    ['a body that is not JSON', 'oops'],
    ['a body that is not an object', ['x']],
    ['a body without a detail', { message: 'x' }],
  ])('gives a generic message for %s', async (_name, body) => {
    respond(body, { status: 400 })
    expect(await failure(apiGet('/x'))).toMatchObject({
      status: 400,
      code: 'error',
      message: 'AresGate ran into a problem. Try again in a moment.',
    })
  })

  it('reports an unreachable API as offline', async () => {
    vi.mocked(fetch).mockRejectedValue(new TypeError('Failed to fetch'))
    expect(await failure(apiGet('/x'))).toMatchObject({ status: 0, code: 'offline' })
  })
})

describe('apiPost', () => {
  it('sends JSON, and the security token when it has one', async () => {
    respond({ ok: true })
    await expect(apiPost('/auth/login', { a: 1 }, 'a-token')).resolves.toEqual({ ok: true })
    expect(fetch).toHaveBeenCalledWith('/api/auth/login', {
      method: 'POST',
      headers: {
        Accept: 'application/json',
        'Content-Type': 'application/json',
        'X-CSRF-Token': 'a-token',
      },
      body: '{"a":1}',
      credentials: 'same-origin',
    })
  })

  it('sends no body, and no token, when there is none', async () => {
    vi.mocked(fetch).mockResolvedValue(new Response(null, { status: 204 }))
    await expect(apiPost('/auth/logout')).resolves.toBeUndefined()
    expect(fetch).toHaveBeenCalledWith('/api/auth/logout', {
      method: 'POST',
      headers: { Accept: 'application/json' },
      credentials: 'same-origin',
    })
  })

  it('fails like a read does', async () => {
    respond({ detail: 'Too many attempts. Try again in 1 minute.' }, { status: 429 })
    expect(await failure(apiPost('/auth/login', {}))).toMatchObject({
      status: 429,
      code: 'rate_limited',
      message: 'Too many attempts. Try again in 1 minute.',
    })
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
