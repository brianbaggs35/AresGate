import { apiGet, apiPost, apiPut } from '@/api/client'

/** What is exposed to the internet: nothing, something (the ports are listed), or not known. */
export const EXPOSURES = ['none', 'some', 'unknown'] as const
export type Exposure = (typeof EXPOSURES)[number]

/** What is changed when saving, which is all of it. */
export interface ThreatDraft {
  /** How sure AresGate has to be, from 1 to 100, to call an incident a threat. */
  threat_from: number
  /** Whether an AI may set an incident aside as background. */
  ai_may_clear: boolean
  /** How sure an AI has to be to do that. */
  clear_from: number
  /** Whether an incident needs an AI to agree before it is a threat (when one is watching). */
  ai_confirms: boolean
  exposure: Exposure
  exposed_ports: number[]
  /** Anything about the network that tells what is normal there. */
  notes: string
}

export interface ThreatSettings extends ThreatDraft {
  /** What each is until it is changed, and the lowest the AI's bar can be. */
  default_threat_from: number
  default_clear_from: number
  min_clear_from: number
  max_notes: number
  max_ports: number
  /** Whether an AI is watching: on, with a provider, and reading by itself. */
  watching: boolean
  updated_at: string | null
}

/** The incidents that are going on, by where they stand. */
export interface Lanes {
  threats: number
  suspects: number
  /** Unsure, or set aside by an AI. */
  background: number
  cleared: number
  muted: number
}

export interface ThreatPreview {
  now: Lanes
  after: Lanes
}

export function fetchThreatSettings(): Promise<ThreatSettings> {
  return apiGet<ThreatSettings>('/threat-settings')
}

export function saveThreatSettings(draft: ThreatDraft, csrfToken: string): Promise<ThreatSettings> {
  return apiPut<ThreatSettings>('/threat-settings', draft, csrfToken)
}

/** What the lanes would come to if the settings were as asked. Nothing is kept. */
export function previewThreatSettings(
  draft: ThreatDraft,
  csrfToken: string,
): Promise<ThreatPreview> {
  return apiPost<ThreatPreview>('/threat-settings/preview', draft, csrfToken)
}
