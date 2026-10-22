import {
  request as playwrightRequest,
  type APIRequest,
  type APIRequestContext,
  type APIResponse,
} from '@playwright/test'

/**
 * The test server's harness (backend/e2e): it puts the database back to a known state, makes
 * extra records and reports the API's code coverage. Only the e2e image, and the API that
 * `make e2e-host` starts, serve it, under /api/__test__.
 */

/** What to sign in with. */
export interface Credentials {
  username: string
  password: string
}

/** What the baseline holds, as the API describes it. */
export interface BaselineData {
  /** The `system_info` rows, by key. */
  system_info: Record<string, string>
  /** The account the baseline signs in with. */
  account: Credentials
  /** The setup code the `fresh-install` state waits with, where a real install prints its own. */
  fresh_install_setup_code: string
}

/** The named states `loadFixture()` can put the database in. */
export type FixtureName = 'baseline' | 'fresh-install'

export interface Loaded {
  fixture: FixtureName
  /** The tables that were emptied first. */
  tables_emptied: string[]
}

export interface SystemInfoRecord {
  key: string
  value: string
  updated_at: string
}

export interface ApiCoverage {
  percent_covered: number
  /** An HTML report and an LCOV file, paths relative to backend/ and contents in base64. */
  files: { path: string; content: string }[]
}

function newContext(requests: APIRequest, baseURL: string): Promise<APIRequestContext> {
  // The test container's certificate is self-signed.
  return requests.newContext({ baseURL, ignoreHTTPSErrors: true })
}

/** Reads a response's JSON, or fails with what the server said. */
export async function readJson<T>(response: APIResponse, what: string): Promise<T> {
  if (!response.ok()) {
    throw new Error(`${what} failed with ${response.status()}: ${await response.text()}`)
  }
  return (await response.json()) as T
}

export class Harness {
  private constructor(private readonly api: APIRequestContext) {}

  static async connect(
    baseURL: string,
    requests: APIRequest = playwrightRequest,
  ): Promise<Harness> {
    return new Harness(await newContext(requests, baseURL))
  }

  /** Waits for the test server to answer, and checks it has the harness (the e2e image). */
  async waitUntilReady(timeoutMs = 60_000): Promise<void> {
    const deadline = Date.now() + timeoutMs
    for (;;) {
      let problem: string
      try {
        const health = await this.api.get('/api/health', { timeout: 5_000 })
        if (health.ok()) break
        problem = `its health check answered ${health.status()}`
      } catch (error) {
        problem = error instanceof Error ? error.message : String(error)
      }
      if (Date.now() >= deadline) {
        throw new Error(
          `The test server isn't ready (${problem}). Start it with \`make e2e-up\`, or point ` +
            'ARESGATE_E2E_URL at one.',
        )
      }
      await new Promise((resolve) => setTimeout(resolve, 1_000))
    }
    const harness = await this.api.get('/api/__test__/baseline')
    if (harness.status() === 404) {
      throw new Error(
        "This server doesn't have the test harness, so it isn't the e2e image. The end-to-end " +
          'tests erase the database, so they only run against `make e2e-up` or `make e2e-host`.',
      )
    }
  }

  /** What the baseline holds, without touching the database. */
  describe(): Promise<BaselineData> {
    return this.api
      .get('/api/__test__/baseline')
      .then((response) => readJson<BaselineData>(response, 'Reading the baseline'))
  }

  /** Empties every table, then loads the baseline. */
  clean(): Promise<Loaded> {
    return this.api
      .post('/api/__test__/database/clean')
      .then((response) => readJson<Loaded>(response, 'Cleaning the database'))
  }

  /** Empties every table, then loads a named state. */
  loadFixture(name: FixtureName): Promise<Loaded> {
    return this.api
      .post(`/api/__test__/fixtures/${name}`)
      .then((response) => readJson<Loaded>(response, `Loading the ${name} fixture`))
  }

  /** How many rows each table holds. */
  rowCounts(): Promise<Record<string, number>> {
    return this.api
      .get('/api/__test__/database/counts')
      .then((response) => readJson<Record<string, number>>(response, 'Counting rows'))
  }

  /** Adds a `system_info` row; what isn't given is made up. */
  createSystemInfo(record: { key?: string; value?: string } = {}): Promise<SystemInfoRecord> {
    return this.api
      .post('/api/__test__/factories/system-info', { data: record })
      .then((response) => readJson<SystemInfoRecord>(response, 'Making a system_info row'))
  }

  /** Adds an account; what isn't given is made up. Returns what to sign in with. */
  createAccount(record: { username?: string; password?: string } = {}): Promise<Credentials> {
    return this.api
      .post('/api/__test__/factories/account', { data: record })
      .then((response) => readJson<Credentials>(response, 'Making an account'))
  }

  /** The API's coverage so far, or null when the API isn't measuring it. */
  async coverage(): Promise<ApiCoverage | null> {
    const response = await this.api.get('/api/__test__/coverage')
    if (response.status() === 404) return null
    return readJson<ApiCoverage>(response, "Reading the API's coverage")
  }

  dispose(): Promise<void> {
    return this.api.dispose()
  }
}
