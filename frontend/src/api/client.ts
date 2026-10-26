const OFFLINE = "Can't reach AresGate. Check your connection and try again."
const SERVER_ERROR = 'AresGate ran into a problem. Try again in a moment.'
const REJECTED = "AresGate couldn't use that. Check what you entered and try again."

/** One thing wrong with what was sent, and where: `path` is the field's place in the request
 * without its leading `body`, such as `['connections', 'api', 'url']`. */
export interface Problem {
  path: readonly string[]
  message: string
}

/** A failed API call: a message people can act on, and a code to tell failures apart. */
export class ApiError extends Error {
  /** What kind of failure it is, e.g. `unauthenticated`, or `offline` when there was no answer. */
  readonly code: string
  /** For a request that was refused field by field, what was wrong with each. */
  readonly problems: readonly Problem[]

  constructor(
    readonly status: number,
    message: string,
    code = 'error',
    problems: readonly Problem[] = [],
  ) {
    super(message)
    this.name = 'ApiError'
    this.code = code
    this.problems = problems
  }
}

/** The API's own status codes, named. */
const CODES: Readonly<Record<number, string>> = {
  401: 'unauthenticated',
  403: 'forbidden',
  404: 'not_found',
  409: 'conflict',
  422: 'invalid',
  429: 'rate_limited',
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

async function readBody(response: Response): Promise<unknown> {
  try {
    return await response.json()
  } catch {
    return undefined
  }
}

/** The problems in a list that the framework (or a page of settings) answers with, each naming
 * where it was and what was wrong. An entry that isn't in that shape is left out. */
function readProblems(detail: unknown): Problem[] {
  if (!Array.isArray(detail)) return []
  const problems: Problem[] = []
  for (const item of detail as unknown[]) {
    if (!isRecord(item) || !Array.isArray(item.loc) || typeof item.msg !== 'string') continue
    const path = (item.loc as unknown[]).map(String)
    problems.push({ path: path[0] === 'body' ? path.slice(1) : path, message: item.msg })
  }
  return problems
}

/** The API explains a refusal in words made for people (`detail`), except when a request is so
 * malformed that its framework answers instead, with a list for programs. */
function toError(status: number, body: unknown): ApiError {
  if (status >= 500) return new ApiError(status, SERVER_ERROR)
  const code = CODES[status] ?? 'error'
  const detail = isRecord(body) ? body.detail : undefined
  if (typeof detail === 'string') return new ApiError(status, detail, code)
  const problems = status === 422 ? readProblems(detail) : []
  return new ApiError(status, status === 422 ? REJECTED : SERVER_ERROR, code, problems)
}

interface Request {
  method: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE'
  body?: unknown
  csrfToken?: string
}

async function send<T>(path: string, { method, body, csrfToken }: Request): Promise<T> {
  const headers: Record<string, string> = { Accept: 'application/json' }
  if (body !== undefined) headers['Content-Type'] = 'application/json'
  // Proves the call comes from AresGate's own pages. Every change after signing in needs it.
  if (csrfToken) headers['X-CSRF-Token'] = csrfToken
  let response: Response
  try {
    response = await fetch(`/api${path}`, {
      ...(method === 'GET' ? {} : { method }),
      headers,
      ...(body === undefined ? {} : { body: JSON.stringify(body) }),
      credentials: 'same-origin',
    })
  } catch {
    throw new ApiError(0, OFFLINE, 'offline')
  }
  const answer = await readBody(response)
  if (!response.ok) throw toError(response.status, answer)
  return answer as T
}

/** Calls the API on the same origin, like every page of the web app does. */
export function apiGet<T>(path: string): Promise<T> {
  return send<T>(path, { method: 'GET' })
}

/** Asks the API to change something. After signing in, that takes the sign-in's security token. */
export function apiPost<T>(path: string, body?: unknown, csrfToken?: string): Promise<T> {
  return send<T>(path, { method: 'POST', body, csrfToken })
}

/** Replaces something with what is sent. Like `apiPost`, it takes the sign-in's security token. */
export function apiPut<T>(path: string, body: unknown, csrfToken?: string): Promise<T> {
  return send<T>(path, { method: 'PUT', body, csrfToken })
}

/** Changes part of something with what is sent. Like `apiPost`, it takes the sign-in's security
 * token. */
export function apiPatch<T>(path: string, body: unknown, csrfToken?: string): Promise<T> {
  return send<T>(path, { method: 'PATCH', body, csrfToken })
}

/** Removes something. Like `apiPost`, it takes the sign-in's security token. */
export function apiDelete<T = undefined>(path: string, csrfToken?: string): Promise<T> {
  return send<T>(path, { method: 'DELETE', csrfToken })
}

/** Words to show for any error, including ones that didn't come from the API. */
export function errorMessage(error: unknown): string {
  if (error instanceof Error) return error.message
  return String(error)
}
