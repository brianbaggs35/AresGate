import { apiDelete, apiGet, apiPost, apiPut } from '@/api/client'

/** Whether an integration, or one of its connections, is set up and working. */
export type Status = 'not_connected' | 'untested' | 'connected' | 'problem'

/** What testing a connection found of a service that runs on the system, such as Suricata. */
export type ModuleState =
  'running' | 'stopped' | 'installed' | 'not_installed' | 'no_access' | 'unknown'

/** How a system's certificate is checked: against the certificates the computer trusts, against
 * a certificate authority that was pasted in, or against one certificate's fingerprint. */
export type TlsMode = 'system' | 'ca' | 'pinned'

export interface Choice {
  value: string
  label: string
}

export interface Field {
  key: string
  label: string
  kind: 'text' | 'secret' | 'number' | 'choice' | 'lookup'
  help: string
  placeholder: string
  default: string | number | null
  choices: Choice[]
  minimum: number
  maximum: number
  /** The field only applies while another field has this value. */
  only_if: { field: string; value: string } | null
  /** For a lookup: the button that asks the system for its list, such as `Fetch interfaces`. */
  action: string
  /** For a lookup: more than one can be chosen, and are kept as values joined by commas. */
  multiple: boolean
  /** What the owner must know before choosing, shown as a warning beside the field. Empty when
   * there is nothing to warn of. */
  caution: string
}

/** What a connection takes, from the integration's definition. */
export interface ConnectionDefinition {
  key: string
  label: string
  summary: string
  url_example: string
  /** Whether plain http:// is accepted, which can be read on the network. */
  allow_http: boolean
  fields: Field[]
  /** Not everyone has it, such as Zenarmor on OPNsense. */
  optional: boolean
  /**
   * What the product's documentation adds about its certificate, shown beside the choice of how
   * to trust it. Empty when there is nothing.
   */
  certificate_note: string
  /** The address the connection always uses, when the service has one for everyone. Empty when
   * the owner gives the address. */
  address: string
  /** Whether the service is on the internet rather than the home network. */
  internet: boolean
}

/** A service that runs on the system, and whether AresGate reads it. */
export interface Module {
  key: string
  label: string
  summary: string
  /** Null until the connection has been tested. */
  state: ModuleState | null
  enabled: boolean
}

/** A service that was found, as an integration's card lists it. */
export interface Service {
  key: string
  label: string
  state: ModuleState
}

export interface Connection {
  definition: ConnectionDefinition
  url: string | null
  tls_mode: TlsMode
  tls_ca_pem: string | null
  tls_fingerprint: string | null
  options: Record<string, string | number>
  modules: Module[]
  /** Which secrets are kept. Their values are never sent. */
  secrets_set: string[]
  status: Status
  last_attempt_at: string | null
  last_success_at: string | null
  last_error: string | null
  /** Whether the last failure was about the system's certificate, which can be reviewed and
   * trusted from the page. */
  certificate_problem: boolean
}

/** A limit VirusTotal set on lookups, which holds them until it lifts: its daily quota, which lifts
 * at 00:00 UTC, or a minute's wait after it asked for fewer requests. */
export interface Pause {
  /** When the limit lifts, as a time. */
  until: string
  /** Whether it is the daily quota. */
  daily: boolean
}

export interface IntegrationSummary {
  key: string
  name: string
  provides: string
  /** The kind of thing it is, such as `firewall`. */
  icon: string
  /** What family it belongs to, such as `Threat intelligence`. Empty when it belongs to none. */
  category: string
  status: Status
  last_success_at: string | null
  services: Service[]
  /** VirusTotal's own limit on lookups, while one holds. Null when none does. */
  pause: Pause | null
}

/** A page of the product's documentation (or source) that a guide was written from. */
export interface GuideSource {
  title: string
  url: string
}

/** An exact value to pick or enter, and what it is for. */
export interface GuideFill {
  label: string
  value: string
}

export interface GuideStep {
  title: string
  detail: string
  /** The menus to go through, in order. */
  menu: string[]
  fills: GuideFill[]
  /** Something to run in a shell, to be copied as it is. */
  command: string
  /** Which of AresGate's fields what this step produced goes into. */
  result: string
  /** What is easy to get wrong. */
  watch: string
  /** What was worked out rather than read from the documentation, and why. */
  inferred: string
}

/** The steps for one connection of the integration. */
export interface GuidePart {
  title: string
  /** The connection whose form the steps fill in. */
  connection: string
  intro: string
  steps: GuideStep[]
  optional: boolean
}

export interface Guide {
  parts: GuidePart[]
  sources: GuideSource[]
}

export interface Integration extends IntegrationSummary {
  docs_url: string
  /** How to get what the fields ask for, step by step, in the product's own terms. */
  guide: Guide
  last_error: string | null
  connections: Connection[]
}

/** What is sent for one connection. A secret that is left out keeps the one already kept. */
export interface ConnectionSettings {
  url: string
  tls_mode: TlsMode
  tls_ca_pem: string | null
  tls_fingerprint: string | null
  options: Record<string, string | number | null>
  /** Services not to read, by key. */
  disabled_modules: string[]
  secrets: Record<string, string>
}

export interface Check {
  connection: string
  ok: boolean
  message: string
  /** Whether it failed over the system's certificate. */
  certificate_problem: boolean
  /** The keys of the services found installed but not running, which connecting switched off. */
  switched_off: string[]
}

/** How a test went, and the integration as it is now. */
export interface CheckReport {
  ok: boolean
  checks: Check[]
  integration: Integration
}

/** One thing a system lists when asked, such as one of ntopng's interfaces. */
export interface LookupEntry {
  /** What is kept when it is chosen. */
  value: string
  label: string
  /** What else is known of it, in a few words. */
  detail: string
  /** Nothing has passed through it yet. */
  quiet: boolean
  /** It only carries the machine's traffic to itself, which normally has nothing worth reading. */
  loopback: boolean
}

/** What a system listed when it was asked for the choices of a field, or why it couldn't say. */
export interface LookupResult {
  ok: boolean
  message: string
  entries: LookupEntry[]
}

/** A certificate, as a system presents it. */
export interface Certificate {
  /** SHA-256, as pairs of hexadecimal digits separated by colons. */
  fingerprint: string
  subject: string
  issuer: string
  not_before: string
  not_after: string
  names: string[]
  /** Whether it names itself as its issuer: nobody else vouches for it. */
  self_signed: boolean
}

/** What a system presents: its own certificate, which is the one that is pinned, then the others
 * it sent with it, and what the connection's way of checking makes of it. */
export interface CertificateReview extends Certificate {
  issuers: Certificate[]
  /** Whether the connection, as it is set to check, would accept the certificate. */
  accepted: boolean
  /** Why it would or wouldn't, in words. */
  verdict: string
}

/** How a connection is set to check a certificate, so that a lookup can say whether it would
 * accept the one it finds. */
export interface CertificateChoice {
  mode: TlsMode
  authority: string
  fingerprint: string
}

/** One request AresGate made to an integration. */
export interface Call {
  id: number
  occurred_at: string
  connection: string
  method: string
  path: string
  /** Null when no answer came. */
  status_code: number | null
  duration_ms: number
  error: string | null
}

export interface CallPage {
  calls: Call[]
  /** Pass it as `before` for the next page of older calls. Null on the last page. */
  next_before: number | null
}

export interface CallQuery {
  connection?: string
  method?: string
  /** True for only the calls that failed, false for only those that worked. */
  failed?: boolean
  since?: string
  before?: number
  limit?: number
}

const path = (key: string, rest = '') => `/integrations/${encodeURIComponent(key)}${rest}`

export function fetchIntegrations(): Promise<IntegrationSummary[]> {
  return apiGet<IntegrationSummary[]>('/integrations')
}

export function fetchIntegration(key: string): Promise<Integration> {
  return apiGet<Integration>(path(key))
}

/** Connects, or changes the settings of, the connections named. A connection of an optional kind
 * that is left out is forgotten. */
export function saveIntegration(
  key: string,
  connections: Record<string, ConnectionSettings>,
  csrfToken: string,
): Promise<Integration> {
  return apiPut<Integration>(path(key), { connections }, csrfToken)
}

/** Forgets the settings and secrets of every connection of an integration. */
export async function disconnectIntegration(key: string, csrfToken: string): Promise<void> {
  await apiDelete(path(key), csrfToken)
}

/** Tests each saved connection with one harmless read. */
export function testIntegration(key: string, csrfToken: string): Promise<CheckReport> {
  return apiPost<CheckReport>(path(key, '/test'), undefined, csrfToken)
}

/** Asks a connection for the choices of one of its fields (the interfaces ntopng has), with the
 * address and sign-in as they are filled in. Nothing is saved. */
export function lookUpField(
  key: string,
  connection: string,
  field: string,
  settings: ConnectionSettings,
  csrfToken: string,
): Promise<LookupResult> {
  const rest = `/connections/${encodeURIComponent(connection)}/lookup/${encodeURIComponent(field)}`
  return apiPost<LookupResult>(path(key, rest), settings, csrfToken)
}

/** The certificate that the system at an address presents, with whether the way of checking
 * chosen would accept it, to trust (pin) or to compare. */
export function lookUpCertificate(
  key: string,
  url: string,
  choice: CertificateChoice,
  csrfToken: string,
): Promise<CertificateReview> {
  return apiPost<CertificateReview>(
    path(key, '/certificate'),
    {
      url,
      tls_mode: choice.mode,
      tls_ca_pem: choice.mode === 'ca' ? choice.authority : null,
      tls_fingerprint: choice.mode === 'pinned' ? choice.fingerprint.trim() : null,
    },
    csrfToken,
  )
}

/** The newest calls first. */
export function fetchCalls(key: string, query: CallQuery = {}): Promise<CallPage> {
  const parameters = new URLSearchParams()
  for (const [name, value] of Object.entries(query)) {
    if (value !== undefined) parameters.set(name, String(value))
  }
  const text = parameters.toString()
  const suffix = text ? `?${text}` : ''
  return apiGet<CallPage>(path(key, `/calls${suffix}`))
}
