import { apiGet } from '@/api/client'

export interface BuildInfo {
  version: string
  /** Which commit it was built from; none where it runs from source. */
  commit: string | null
  built_at: string | null
  environment: string
  started_at: string
  uptime_seconds: number
}

export interface DatabaseInfo {
  status: 'ok' | 'unavailable'
  /** PostgreSQL's own version. */
  version: string | null
  size_bytes: number | null
  connections: number | null
  max_connections: number | null
  /** The migration the database is at, and the one this version expects. */
  migration: string | null
  migration_head: string | null
}

export interface CertificateInfo {
  subject: string
  issuer: string
  names: string[]
  not_before: string
  not_after: string
  days_left: number
  self_signed: boolean
}

export interface StackInfo {
  python: string
  nginx: string | null
  database: DatabaseInfo
  /** What browsers are shown, or none where nothing serves it (running from source). */
  certificate: CertificateInfo | null
}

export interface Memory {
  used_bytes: number
  /** None where nothing limits it but the computer's own memory. */
  limit_bytes: number | null
  total_bytes: number | null
}

export interface Disk {
  used_bytes: number
  total_bytes: number
}

export interface ContainerInfo {
  cpus: number | null
  /** Processes waiting to run, averaged over the last 1, 5 and 15 minutes. */
  load: number[] | null
  memory: Memory | null
  disk: Disk | null
  /** AresGate's clock when it answered. */
  server_time: string
}

export type PartState = 'ok' | 'problem' | 'unknown' | 'off'

/** One part of AresGate that can be healthy or not. */
export interface Part {
  key: string
  name: string
  group: 'integration'
  state: PartState
  detail: string | null
  last_success_at: string | null
}

export interface StatusReport {
  aresgate: BuildInfo
  stack: StackInfo
  container: ContainerInfo
  parts: Part[]
  /** The same facts as text for a bug report, with addresses left out. */
  diagnostics: string
}

export function fetchStatus(): Promise<StatusReport> {
  return apiGet<StatusReport>('/status')
}
