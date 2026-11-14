import {
  ApiError,
  apiDelete,
  apiGet,
  apiPatch,
  apiPost,
  apiPut,
  apiStream,
  errorMessage,
  type StreamEvent,
} from '@/api/client'

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

describe('apiPatch', () => {
  it('changes part of something with JSON, and the security token', async () => {
    respond({ status: 'resolved' })
    await expect(apiPatch('/incidents/7', { status: 'resolved' }, 'a-token')).resolves.toEqual({
      status: 'resolved',
    })
    expect(fetch).toHaveBeenCalledWith('/api/incidents/7', {
      method: 'PATCH',
      headers: {
        Accept: 'application/json',
        'Content-Type': 'application/json',
        'X-CSRF-Token': 'a-token',
      },
      body: '{"status":"resolved"}',
      credentials: 'same-origin',
    })
  })

  it('fails like the others do', async () => {
    respond({ detail: "There's no such incident." }, { status: 404 })
    expect(await failure(apiPatch('/incidents/9', {}))).toMatchObject({
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

/** A response whose body arrives in these pieces, as a server that sends as it goes would. */
function stream(pieces: string[], failAfter = false) {
  const encoder = new TextEncoder()
  const body = new ReadableStream<Uint8Array>({
    start(controller) {
      for (const piece of pieces) controller.enqueue(encoder.encode(piece))
      if (failAfter) controller.error(new TypeError('network error'))
      else controller.close()
    },
  })
  vi.mocked(fetch).mockResolvedValue(new Response(body, { status: 200 }))
}

async function events(call: Promise<void>, seen: StreamEvent[]) {
  await call
  return seen
}

describe('apiStream', () => {
  it('asks for a stream with the security token, and hands over each event as it comes', async () => {
    stream(['event: looked\ndata: {"tool":"alerts"}\n\n', 'event: wrote\ndata: {"text":"Hi"}\n\n'])
    const seen: StreamEvent[] = []

    await events(
      apiStream('/ai/conversations/stream', { text: 'Hello' }, 'a-token', (event) =>
        seen.push(event),
      ),
      seen,
    )

    expect(seen).toEqual([
      { name: 'looked', data: { tool: 'alerts' } },
      { name: 'wrote', data: { text: 'Hi' } },
    ])
    expect(fetch).toHaveBeenCalledWith('/api/ai/conversations/stream', {
      method: 'POST',
      headers: {
        Accept: 'text/event-stream',
        'Content-Type': 'application/json',
        'X-CSRF-Token': 'a-token',
      },
      body: '{"text":"Hello"}',
      credentials: 'same-origin',
    })
  })

  it('puts together an event that arrives cut in pieces, even in the middle of a character', async () => {
    const bytes = new TextEncoder().encode('event: wrote\ndata: {"text":"é"}\n\n')
    const cut = bytes.indexOf(0xc3) + 1
    const body = new ReadableStream<Uint8Array>({
      start(controller) {
        controller.enqueue(bytes.slice(0, 5))
        controller.enqueue(bytes.slice(5, cut))
        controller.enqueue(bytes.slice(cut))
        controller.close()
      },
    })
    vi.mocked(fetch).mockResolvedValue(new Response(body, { status: 200 }))
    const seen: StreamEvent[] = []

    await apiStream('/x', {}, 't', (event) => seen.push(event))

    expect(seen).toEqual([{ name: 'wrote', data: { text: 'é' } }])
  })

  it('leaves out what is not an event: comments, data that is not JSON, and an event with none', async () => {
    stream([': a comment\n\n', 'event: x\ndata: not json\n\n', 'event: y\n\n', 'data: {"a":1}\n\n'])
    const seen: StreamEvent[] = []

    await apiStream('/x', {}, 't', (event) => seen.push(event))

    expect(seen).toEqual([{ name: 'message', data: { a: 1 } }])
  })

  it('reads the data of an event that is on more than one line as one', async () => {
    stream(['event: x\ndata: {"a":\ndata: 1}\n\n'])
    const seen: StreamEvent[] = []

    await apiStream('/x', {}, 't', (event) => seen.push(event))

    expect(seen).toEqual([{ name: 'x', data: { a: 1 } }])
  })

  it("uses the API's words for a refusal, before anything is streamed", async () => {
    respond({ detail: 'There is no such conversation.' }, { status: 404 })

    const error = await failure(apiStream('/x', {}, 't', vi.fn()))

    expect(error).toMatchObject({ status: 404, code: 'not_found' })
    expect(error).toHaveProperty('message', 'There is no such conversation.')
  })

  it('says AresGate cannot be reached when there is no answer', async () => {
    vi.mocked(fetch).mockRejectedValue(new TypeError('Failed to fetch'))

    expect(await failure(apiStream('/x', {}, 't', vi.fn()))).toMatchObject({
      status: 0,
      code: 'offline',
    })
  })

  it('says so when the connection breaks in the middle', async () => {
    stream(['event: x\ndata: {}\n\n'], true)

    const error = await failure(apiStream('/x', {}, 't', vi.fn()))

    expect(error).toMatchObject({
      status: 0,
      code: 'offline',
      message: 'The connection broke before the answer was finished.',
    })
  })
})
