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
  /** Alerts that a program keeps reporting, from three addresses to five others, for the
   * dashboard to call the noise. */
  repeated?: {
    source: string
    signature: string
    severity?: 'info' | 'low' | 'medium' | 'high' | 'critical'
    count: number
  }[]
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
/** How a pass of the notifier went. */
export interface NotifierReport {
  sent: number
  retrying: number
  failed: number
}

export interface IncidentRequest {
  /** Where it came from: a public address, since the documentation ranges are not outside the
   * network as far as the engine is concerned. The next of a few is used when it isn't given. */
  address?: string
  severity?: 'info' | 'low' | 'medium' | 'high' | 'critical'
  /** Which integrations saw it, in turn: the signals are shared between them. */
  programs?: string[]
  /** Whether the device sent its signals to the address, as a camera calls its cloud, rather than
   * the address sending them to the device. */
  outbound?: boolean
  /** How many alerts there are, a few minutes apart. */
  signals?: number
  /** Whether CrowdSec banned the address, and the time it said was left of the ban when it was
   * first read, as a Go duration ("3h59m12s" unless said). */
  ban?: boolean
  ban_left?: string
  /** How many times the firewall turned the address away before the ban and after it, and how
   * many alerts Suricata stopped. */
  blocks?: number
  blocks_after_ban?: number
  dropped?: number
  /** How long ago the last signal was. */
  minutes_ago?: number
  /** The device on the network that was attacked, and what it is called when it is known. */
  device?: string
  device_name?: string
  status?: 'open' | 'investigating' | 'resolved' | 'dismissed'
  /** How many days nothing has touched it, whatever the signals say: it is moved back once filed,
   * since signals older than a day are not filed. */
  idle_days?: number
  /** Makes every signal a port scan (the first is a brute force otherwise), as a bot sweeping the
   * network would send, from the address and this many of its neighbours of the same /24 in
   * turn, in this many bursts, over these ports in turn. */
  scan?: boolean
  neighbours?: number
  waves?: number
  ports?: number[]
  /** What the scanner went on to do: try an exploit, and a sign that it worked. Either makes the
   * incident more than scanning, which is never background. */
  exploit?: boolean
  compromise?: boolean
  /** A second program that reports every alert a couple of seconds after the first, as the same
   * thing seen twice (it counts once). */
  twin?: string
  /** Whether each program says what it knows besides the basics (the rule's groups and its
   * technique, the machine, the traffic), as the real ones do. */
  detailed?: boolean
  /** Whether the firewall's record also says what was said on the wire: a certificate a camera
   * signed itself, a plain web request with a login in it, a name looked up. Needs `detailed`. */
  wire?: boolean
  /** A CVE the alerts name in what they say, such as `CVE-2021-44228`. */
  cve?: string
}

/** How much `createIncidents()` stored. */
export interface IncidentsRecord {
  signals: number
  incidents: number
}

/** An event, or a run of them, as a program would have reported it, as `createEvents()` stores
 * it. All of it is optional. */
export interface EventRequest {
  source?: string
  /** Which connection of the integration brought it. */
  connection?: string
  kind?: string
  severity?: 'info' | 'low' | 'medium' | 'high' | 'critical'
  summary?: string
  /** The rule that fired, for an alert. */
  signature?: string
  src_address?: string
  src_port?: number
  dst_address?: string
  dst_port?: number
  protocol?: string
  /** The port it came in on, in the program's own name for it (`igc0`). */
  iface?: string
  /** How long ago the first was; a run goes back from there in time. */
  seconds_ago?: number
  /** The integration's own record of it, which the detail shows. */
  raw?: Record<string, unknown>
  /** How many there are, in a run, this many seconds apart. */
  repeat?: number
  every_seconds?: number
}

/** How many events `createEvents()` stored. */
export interface EventsRecord {
  events: number
}

/** One way an integration listed a device, and how long ago. Left out, it is the firewall's ARP
 * table, a minute ago. */
export interface AssetListing {
  source?: string
  via?: 'arp' | 'dhcp' | 'hosts' | 'agent'
  minutes_ago?: number
  /** Whether the firewall lists it as one of its own addresses (a permanent ARP entry). */
  own?: boolean
}

/** A device as the integrations that list it left it, as `createAssets()` stores it. All of it is
 * optional. */
export interface AssetDeviceRequest {
  hostname?: string
  /** Its hardware address; made up when it isn't given. */
  mac?: string
  vendor?: string
  /** The addresses it has now. */
  addresses?: string[]
  /** Addresses it had before, which it is no longer listed at. */
  earlier?: string[]
  /** Who listed it and when. The first is how it was first listed. */
  listed?: AssetListing[]
  /** How long ago it was first listed. A month by default, so it is not new. */
  first_seen_hours?: number
}

/** A machine with no hardware address, such as a Wazuh agent, which the page merges into the
 * device that has its address or its name, or lists on its own. */
export interface AssetHostRequest {
  key: string
  hostname?: string
  address?: string
  state?: string
  online?: boolean
  minutes_ago?: number
  source?: string
  connection?: string
  via?: string
}

export interface AssetsRequest {
  devices?: AssetDeviceRequest[]
  hosts?: AssetHostRequest[]
}

/** How many devices and machines `createAssets()` stored. */
export interface AssetsRecord {
  devices: number
  hosts: number
}

/** What ntopng read of one host: the bytes it sent and received, an hour apart, oldest first. */
export interface TrafficHostRequest {
  /** The address of the host. */
  host: string
  sent?: number[]
  received?: number[]
}

/** How many readings `createTraffic()` stored. */
export interface TrafficRecord {
  readings: number
}

/** What a program reports about one of its ports, as discovery finds it and as the Interfaces
 * page leaves it. Left out, it is OPNsense's, with no name: a whole connection. */
export interface FeedRequest {
  integration?: string
  /** The name the program uses for the port; empty for a connection that has none. */
  native_name?: string
  connection?: string
  label?: string
  detail?: string
  /** The interface it is placed on, made if there isn't one of that name. Left out, it is not
   * placed. */
  interface?: string
  /** The role of an interface that is made for it. */
  role?: 'internet' | 'dmz' | 'home' | 'guest' | 'iot' | 'vpn' | 'management' | 'other'
  /** Set aside as not wanted. */
  ignored?: boolean
}

/** How many feeds `createFeeds()` made. */
export interface FeedsRecord {
  feeds: number
}

/** A verdict as the owner would give it: what it says and at least one thing it is about. */
export interface VerdictRequest {
  verdict: 'not_suspicious' | 'low_priority' | 'threat'
  address?: string
  /** Where that address sends its traffic, as one address or a whole network. */
  destination?: string
  source?: string
  signature?: string
  note?: string
}

/** How many verdicts `createVerdicts()` gave. */
export interface VerdictsRecord {
  verdicts: number
}

/** What an AI decided of an incident that is there (or the kind it is of), and where the owner's
 * review of it stands. */
export interface DecisionRequest {
  /** The address of the incident it is about. */
  address: string
  subject?: 'incident' | 'family'
  ai_class?: 'compromise' | 'attack' | 'probe' | 'noise' | 'unclear'
  confidence?: number
  review?: 'pending' | 'auto' | 'agreed' | 'disagreed'
  headline?: string
}

/** How many decisions `createDecisions()` made. */
export interface DecisionsRecord {
  decisions: number
}

/** How much of what the AI decides waits for the owner. */
export interface ReviewSettingsRequest {
  mode?: 'all' | 'uncertain' | 'auto'
  auto_from?: number
  learn?: boolean
}

/** A request to an AI provider as the gateway would have recorded it. Whatever is left out is
 * made up. */
export interface AiCallRequest {
  purpose?: string
  about?: string
  provider?: string
  model?: string
  ok?: boolean
  input_tokens?: number
  output_tokens?: number
  cached_tokens?: number
  /** Millionths of a US dollar; null for a model whose price is not known. */
  cost_micros?: number | null
  /** How long ago the last was; a run goes back from there, an hour apart. */
  hours_ago?: number
  error?: string
  repeat?: number
}

/** How many calls `createAiCalls()` recorded. */
export interface AiCallsRecord {
  calls: number
}

/** The kinds of integration a stand-in can answer like. */
export type StandInKind =
  | 'opnsense'
  | 'zenarmor'
  | 'ntopng'
  | 'crowdsec'
  | 'wazuh'
  | 'anthropic'
  | 'openai'
  | 'ollama'
  | 'discord'

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
  /** Discord's: the `id/token` of the one webhook it knows. Alerts are sent to it instead of to
   * Discord while it runs. */
  webhook?: string
  /** ntopng: it numbers its interfaces like one on an OPNsense firewall (WAN 1, LAN 2, the
   * loopback 3, a VPN 6), not from 0. */
  firewall?: boolean
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

/** A request a stand-in received. */
export interface StandInCall {
  method: string
  path: string
  user_agent: string
  /** The message that was posted, if it was JSON. */
  body: unknown
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

  /** Stores events, as of now, for the Logs page to show. They are not filed into incidents. */
  createEvents(events: EventRequest[]): Promise<EventsRecord> {
    return this.api
      .post('/api/__test__/factories/events', { data: { events } })
      .then((response) => readJson<EventsRecord>(response, 'Making events'))
  }

  /** Stores devices, and the machines that integrations list without a hardware address, as the
   * integrations would have left them, for the Assets page to show. */
  createAssets(request: AssetsRequest): Promise<AssetsRecord> {
    return this.api
      .post('/api/__test__/factories/assets', { data: request })
      .then((response) => readJson<AssetsRecord>(response, 'Making assets'))
  }

  /** Stores what ntopng read of hosts, an hour apart, for an asset's page to chart the traffic of.
   * Each reading is a counter, so the traffic is what it rose by. */
  createTraffic(hosts: TrafficHostRequest[]): Promise<TrafficRecord> {
    return this.api
      .post('/api/__test__/factories/traffic', { data: { hosts } })
      .then((response) => readJson<TrafficRecord>(response, 'Making traffic'))
  }

  /** Makes feeds, and the interfaces they are placed on, as the Interfaces page leaves them. */
  createFeeds(feeds: FeedRequest[]): Promise<FeedsRecord> {
    return this.api
      .post('/api/__test__/factories/feeds', { data: { feeds } })
      .then((response) => readJson<FeedsRecord>(response, 'Making feeds'))
  }

  /** Gives some verdicts and judges the incidents there are by them, as the page for them does. */
  createVerdicts(verdicts: VerdictRequest[]): Promise<VerdictsRecord> {
    return this.api
      .post('/api/__test__/factories/verdicts', { data: { verdicts } })
      .then((response) => readJson<VerdictsRecord>(response, 'Giving verdicts'))
  }

  /** Records what an AI decided of incidents that are there, for the Review page to show. */
  createDecisions(decisions: DecisionRequest[]): Promise<DecisionsRecord> {
    return this.api
      .post('/api/__test__/factories/decisions', { data: { decisions } })
      .then((response) => readJson<DecisionsRecord>(response, 'Recording decisions'))
  }

  /** Sets how much of what the AI decides waits for the owner, as Settings > Review does. */
  setReview(settings: ReviewSettingsRequest): Promise<ReviewSettingsRequest> {
    return this.api
      .post('/api/__test__/factories/review-settings', { data: settings })
      .then((response) => readJson<ReviewSettingsRequest>(response, 'Setting review'))
  }

  /** Records requests to AI providers as of now, for the usage page to show. */
  createAiCalls(calls: AiCallRequest[]): Promise<AiCallsRecord> {
    return this.api
      .post('/api/__test__/factories/ai-calls', { data: { calls } })
      .then((response) => readJson<AiCallsRecord>(response, 'Recording AI calls'))
  }

  /** Starts a server that answers like an integration. It runs until the next test's clean. */
  standIn(request: StandInRequest): Promise<StandIn> {
    return this.api
      .post('/api/__test__/stand-ins', { data: request })
      .then((response) => readJson<StandIn>(response, `Starting a ${request.kind} stand-in`))
  }

  /** What a stand-in was asked, oldest first, such as the messages a Discord one was sent. */
  standInRequests(id: string): Promise<StandInCall[]> {
    return this.api
      .get(`/api/__test__/stand-ins/${id}/requests`)
      .then((response) => readJson<StandInCall[]>(response, 'Reading what a stand-in was asked'))
  }

  /** Runs every collector once, now, and answers when they have all finished. The worker does
   * nothing of its own in the tests, so collecting happens when a spec says. */
  async runCollectors(): Promise<void> {
    const response = await this.api.post('/api/__test__/collectors/run')
    if (!response.ok()) {
      throw new Error(`Running the collectors failed with ${response.status()}`)
    }
  }

  /** Tells the destinations of the incidents there are, now, once, and answers how it went. The
   * worker does nothing of its own in the tests, so alerts are sent when a spec says. Discord is
   * the stand-in the spec started. */
  async runNotifier(): Promise<NotifierReport> {
    return this.api
      .post('/api/__test__/notifier/run')
      .then((response) => readJson<NotifierReport>(response, 'Sending the alerts'))
  }

  /** Starts the agents that are due, runs everything that waits, once, and answers how many ran.
   * The worker does nothing of its own in the tests, so an agent runs when a spec says. `open`
   * lists the devices the network test finds answering, as "address:port". */
  async runAgents(open: string[] = []): Promise<number> {
    return this.api
      .post('/api/__test__/agents/run', { data: { open } })
      .then((response) => readJson<{ ran: number }>(response, 'Running the agents'))
      .then((report) => report.ran)
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
