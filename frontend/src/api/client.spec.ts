import { ApiError, apiDelete, apiGet, apiPost, apiPut, errorMessage } from '@/api/client'

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

  it('keeps where each problem was, without the body they were in', async () => {
    respond(
      {
        detail: [
          { loc: ['body', 'connections', 'api', 'url'], msg: 'Not private.', type: 'value_error' },
          { loc: ['query', 'limit', 1], msg: 'Too big.', type: 'less_than_equal' },
          { loc: 'nowhere', msg: 'Not a list.' },
          { loc: ['body', 'x'] },
          'text',
        ],
      },
      { status: 422 },
    )
    expect(await failure(apiGet('/x'))).toMatchObject({
      status: 422,
      problems: [
        { path: ['connections', 'api', 'url'], message: 'Not private.' },
        { path: ['query', 'limit', '1'], message: 'Too big.' },
      ],
    })
  })

  it('has no problems to list for any other refusal', async () => {
    respond({ detail: [{ loc: ['body', 'x'], msg: 'No.' }] }, { status: 400 })
    expect(await failure(apiGet('/x'))).toMatchObject({ status: 400, problems: [] })
    respond({ detail: 'Words.' }, { status: 422 })
    expect(await failure(apiGet('/x'))).toMatchObject({ status: 422, problems: [] })
    respond({ detail: { not: 'a list' } }, { status: 422 })
    expect(await failure(apiGet('/x'))).toMatchObject({ status: 422, problems: [] })
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

describe('apiPut', () => {
  it('replaces with JSON, and the security token', async () => {
    respond({ saved: true })
    await expect(apiPut('/integrations/ntopng', { a: 1 }, 'a-token')).resolves.toEqual({
      saved: true,
    })
    expect(fetch).toHaveBeenCalledWith('/api/integrations/ntopng', {
      method: 'PUT',
      headers: {
        Accept: 'application/json',
        'Content-Type': 'application/json',
        'X-CSRF-Token': 'a-token',
      },
      body: '{"a":1}',
      credentials: 'same-origin',
    })
  })

  it('fails like the others do', async () => {
    respond({ detail: 'There is no such integration.' }, { status: 404 })
    expect(await failure(apiPut('/integrations/x', {}))).toMatchObject({
      status: 404,
      code: 'not_found',
    })
  })
})

describe('apiDelete', () => {
  it('removes, with the security token and nothing else to send', async () => {
    vi.mocked(fetch).mockResolvedValue(new Response(null, { status: 204 }))
    await expect(apiDelete('/integrations/ntopng', 'a-token')).resolves.toBeUndefined()
    expect(fetch).toHaveBeenCalledWith('/api/integrations/ntopng', {
      method: 'DELETE',
      headers: { Accept: 'application/json', 'X-CSRF-Token': 'a-token' },
      credentials: 'same-origin',
    })
  })

  it('works without a token, and fails like the others do', async () => {
    respond({ detail: "It isn't connected." }, { status: 404 })
    expect(await failure(apiDelete('/integrations/ntopng'))).toMatchObject({
      status: 404,
      message: "It isn't connected.",
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
