const OFFLINE = "Can't reach AresGate. Check your connection and try again."
const SERVER_ERROR = 'AresGate ran into a problem. Try again in a moment.'

/** A failed API call: a message people can act on, and the API's code for it. */
export class ApiError extends Error {
  /** The API's error code, e.g. `invalid_credentials`, or a generic one this client assigns. */
  readonly code: string

  constructor(
    readonly status: number,
    message: string,
    code = 'error',
  ) {
    super(message)
    this.name = 'ApiError'
    this.code = code
  }
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

function toError(status: number, body: unknown): ApiError {
  const detail = isRecord(body) ? body.detail : undefined
  if (isRecord(detail) && typeof detail.code === 'string' && typeof detail.message === 'string') {
    return new ApiError(status, detail.message, detail.code)
  }
  return new ApiError(status, SERVER_ERROR)
}

/** Calls the API on the same origin, like every page of the web app does. */
export async function apiGet<T>(path: string): Promise<T> {
  let response: Response
  try {
    response = await fetch(`/api${path}`, {
      headers: { Accept: 'application/json' },
      credentials: 'same-origin',
    })
  } catch {
    throw new ApiError(0, OFFLINE, 'offline')
  }
  const body = await readBody(response)
  if (!response.ok) throw toError(response.status, body)
  return body as T
}

/** Words to show for any error, including ones that didn't come from the API. */
export function errorMessage(error: unknown): string {
  if (error instanceof Error) return error.message
  return String(error)
}
