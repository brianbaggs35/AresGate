import { apiGet } from '@/api/client'

/** One thing that happened to the install's security. */
export interface AuditEvent {
  id: number
  occurred_at: string
  /** What happened, such as `auth.login_succeeded`. */
  action: string
  outcome: 'success' | 'failure'
  username: string | null
  client_address: string | null
  user_agent: string | null
}

interface AuditPage {
  events: AuditEvent[]
}

/** The newest events first. */
export async function fetchRecentActivity(limit: number): Promise<AuditEvent[]> {
  const page = await apiGet<AuditPage>(`/audit/events?limit=${limit}`)
  return page.events
}
