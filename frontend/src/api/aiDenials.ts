import { apiDelete, apiGet, apiPost } from '@/api/client'

/** A change the assistant proposed that you denied: the kind of change, and to what. */
export interface DenyDraft {
  kind: 'status' | 'verdict'
  value: string
  incident_ids: number[]
}

/** A denial that stands: the assistant won't propose the same change for the same incident. */
export interface Denial {
  id: number
  kind: 'status' | 'verdict'
  value: string
  incident_id: number
  title: string
  denied_at: string
  /** When it stops standing by itself, if the incident does not change first. */
  expires_at: string
}

export interface Denials {
  items: Denial[]
  /** How long a denial stands. */
  days: number
}

export function fetchDenials(): Promise<Denials> {
  return apiGet<Denials>('/ai/denials')
}

/** Remembers a denial, so that the assistant does not propose it again. */
export function denyProposal(draft: DenyDraft, csrfToken: string): Promise<{ recorded: number }> {
  return apiPost<{ recorded: number }>('/ai/denials', draft, csrfToken)
}

export function forgetDenial(id: number, csrfToken: string): Promise<undefined> {
  return apiDelete(`/ai/denials/${id}`, csrfToken)
}

export function forgetAllDenials(csrfToken: string): Promise<{ forgotten: number }> {
  return apiDelete<{ forgotten: number }>('/ai/denials', csrfToken)
}
