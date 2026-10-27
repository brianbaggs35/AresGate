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

/** What the dashboard has to show, as `createActivity()` stores it. All of it is optional. */
export interface ActivityRequest {
  /** How many alerts of each severity. */
  alerts?: Partial<Record<'info' | 'low' | 'medium' | 'high' | 'critical', number>>
  /** How many connections the firewall refused from each address. */
  blocked?: Record<string, number>
  /** A steady speed in megabits a second for each interface of the firewall. */
  traffic?: Record<string, number>
  /** How many devices were seen for the first time half an hour ago. */
  devices?: number
  /** A collector of the firewall in each of these states, to say how collecting is going. The
   * integration need not be connected. */
  collectors?: ('waiting' | 'ok' | 'problem' | 'late')[]
}

/** How much `createActivity()` stored. */
export interface ActivityRecord {
  alerts: number
  blocked: number
  samples: number
  devices: number
  collectors: number
}

/** An attack that programs saw, as `createIncidents()` stores it. All of it is optional. */
export interface IncidentRequest {
  /** Where it came from: a public address, since the documentation ranges are not outside the
   * network as far as the engine is concerned. The next of a few is used when it isn't given. */
  address?: string
  severity?: 'info' | 'low' | 'medium' | 'high' | 'critical'
  /** Which integrations saw it, in turn: the signals are shared between them. */
  programs?: string[]
  /** How many alerts there are, a few minutes apart. */
  signals?: number
  /** Whether CrowdSec banned the address. */
  ban?: boolean
  /** How long ago the last signal was. */
  minutes_ago?: number
  /** The device on the network that was attacked, and what it is called when it is known. */
  device?: string
  device_name?: string
  status?: 'open' | 'investigating' | 'resolved' | 'dismissed'
}

/** How much `createIncidents()` stored. */
export interface IncidentsRecord {
  signals: number
  incidents: number
}

/** A verdict as the owner would give it: what it says and at least one thing it is about. */
export interface VerdictRequest {
  verdict: 'not_suspicious' | 'low_priority' | 'threat'
  address?: string
  source?: string
  signature?: string
  note?: string
}

/** How many verdicts `createVerdicts()` gave. */
export interface VerdictsRecord {
  verdicts: number
}

/** The kinds of integration a stand-in can answer like. */
export type StandInKind =
  'opnsense' | 'zenarmor' | 'ntopng' | 'crowdsec' | 'wazuh' | 'anthropic' | 'openai' | 'ollama'

/** What a stand-in accepts: ntopng a `token`, CrowdSec and Zenarmor an `api_key`, OPNsense an
 * `api_key` and `api_secret` (and the keys of the `services` it has installed and running),
 * Wazuh a `username` and `password` (one stand-in answers as both its manager and its indexer).
 * An AI provider's stand-in has the `models` it knows, and an Anthropic or OpenAI one an `api_key`
 * (so does Ollama's cloud); `provider` makes AresGate ask it instead of the provider it stands
 * in for. */
export interface StandInRequest {
  kind: StandInKind
  token?: string
  api_key?: string
  api_secret?: string
  services?: string[]
  username?: string
  password?: string
  models?: string[]
  /** An Ollama's models that need a paid plan: listed, and answered with 402. */
  paid?: string[]
  provider?: 'anthropic' | 'openai' | 'ollama_cloud'
}

/** A server on the test machine that answers like an integration. */
export interface StandIn {
  id: string
  kind: StandInKind
  /** Where to connect to it. */
  url: string
  /** Its certificate's SHA-256 fingerprint, for the ones that have a certificate of their own. */
  fingerprint: string | null
}

/** How the collector worker looks to the status page: it reported in just now, it did a while
 * ago and has gone quiet, or it never has. */
export type WorkerPulse = 'running' | 'stopped' | 'absent'

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

  /** Stores alerts, refused connections, interface speeds and new devices as of now, for the
   * dashboard to show. Hours of traffic are made at once, as if the firewall had been read all
   * that time. */
  createActivity(request: ActivityRequest): Promise<ActivityRecord> {
    return this.api
      .post('/api/__test__/factories/activity', { data: request })
      .then((response) => readJson<ActivityRecord>(response, 'Making activity'))
  }

  /** Stores the alerts of some attacks as of now and files them into incidents, as the worker
   * would have, for the Incidents pages to show. */
  createIncidents(incidents: IncidentRequest[]): Promise<IncidentsRecord> {
    return this.api
      .post('/api/__test__/factories/incidents', { data: { incidents } })
      .then((response) => readJson<IncidentsRecord>(response, 'Making incidents'))
  }

  /** Gives some verdicts and judges the incidents there are by them, as the page for them does. */
  createVerdicts(verdicts: VerdictRequest[]): Promise<VerdictsRecord> {
    return this.api
      .post('/api/__test__/factories/verdicts', { data: { verdicts } })
      .then((response) => readJson<VerdictsRecord>(response, 'Giving verdicts'))
  }

  /** Starts a server that answers like an integration. It runs until the next test's clean. */
  standIn(request: StandInRequest): Promise<StandIn> {
    return this.api
      .post('/api/__test__/stand-ins', { data: request })
      .then((response) => readJson<StandIn>(response, `Starting a ${request.kind} stand-in`))
  }

  /** Runs every collector once, now, and answers when they have all finished. The worker does
   * nothing of its own in the tests, so collecting happens when a spec says. */
  async runCollectors(): Promise<void> {
    const response = await this.api.post('/api/__test__/collectors/run')
    if (!response.ok()) {
      throw new Error(`Running the collectors failed with ${response.status()}`)
    }
  }

  /** Makes the collector worker look like it is running, has stopped or has never reported in. */
  async setWorker(state: WorkerPulse): Promise<void> {
    const response = await this.api.put('/api/__test__/collectors/worker', { data: { state } })
    if (!response.ok()) {
      throw new Error(`Setting the worker to ${state} failed with ${response.status()}`)
    }
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
