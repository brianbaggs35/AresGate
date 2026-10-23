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
  kind: 'text' | 'secret' | 'number' | 'choice'
  help: string
  placeholder: string
  default: string | number | null
  choices: Choice[]
  minimum: number
  maximum: number
  /** The field only applies while another field has this value. */
  only_if: { field: string; value: string } | null
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
}

export interface IntegrationSummary {
  key: string
  name: string
  provides: string
  /** The kind of thing it is, such as `firewall`. */
  icon: string
  status: Status
  last_success_at: string | null
  services: Service[]
}

export interface Integration extends IntegrationSummary {
  docs_url: string
  /** How to get what the fields ask for, in the product's own terms. */
  setup: string[]
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
}

/** How a test went, and the integration as it is now. */
export interface CheckReport {
  ok: boolean
  checks: Check[]
  integration: Integration
}

/** The certificate a system presents. */
export interface Certificate {
  /** SHA-256, as pairs of hexadecimal digits separated by colons. */
  fingerprint: string
  subject: string
  issuer: string
  not_before: string
  not_after: string
  names: string[]
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

/** The certificate that the system at an address presents, to pin or to compare. */
export function lookUpCertificate(
  key: string,
  url: string,
  csrfToken: string,
): Promise<Certificate> {
  return apiPost<Certificate>(path(key, '/certificate'), { url }, csrfToken)
}

/** The newest calls first. */
export function fetchCalls(key: string, query: CallQuery = {}): Promise<CallPage> {
  const parameters = new URLSearchParams()
  for (const [name, value] of Object.entries(query)) {
    if (value !== undefined) parameters.set(name, String(value))
  }
  const text = parameters.toString()
  return apiGet<CallPage>(path(key, `/calls${text ? `?${text}` : ''}`))
}
