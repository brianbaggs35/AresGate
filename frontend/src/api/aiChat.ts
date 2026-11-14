import { apiDelete, apiGet, apiPost } from '@/api/client'

/** What an answer looked at to make it, and what it found, in a few words. */
export interface ChatLookup {
  tool: string
  summary: string
}

/** Something an answer is based on, to link to: an `incident` or an `integration`. */
export interface ChatCite {
  kind: string
  key: string
  label: string
}

/** Something the assistant suggests you do. It changes nothing itself: you press its button, and
 * the page makes the same request the page for it would. `kind` is `open` (go to a page),
 * `status` (`value` is the incident's new status) or `verdict` (`value` is the verdict, `note`
 * why). `target_kind` is `incident`, `device`, `integration` or `logs` (then `value` is the
 * search). */
export interface ChatAction {
  kind: 'open' | 'status' | 'verdict'
  target_kind: string
  target_key: string
  value: string | null
  note: string | null
  label: string
}

/** Where you are when you ask, so that "this incident" means the one on screen. */
export interface PageContext {
  kind: 'incident' | 'device' | 'logs' | 'incidents' | 'other'
  id?: number
  /** A device's page is by its address. */
  address?: string
  /** The search on screen. */
  query?: string
  title?: string
}

export interface ChatMessage {
  id: number
  role: 'user' | 'assistant'
  text: string
  /** False for an answer that could not be made: its text says why. */
  ok: boolean
  created_at: string
  lookups: ChatLookup[]
  cites: ChatCite[]
  actions: ChatAction[]
  /** The requests to the provider that made it, to read on the AI usage page. */
  call_ids: number[]
}

export interface Conversation {
  id: number
  title: string
  created_at: string
  updated_at: string
  messages: ChatMessage[]
}

export interface ConversationSummary {
  id: number
  title: string
  updated_at: string
  messages: number
}

export function fetchConversations(): Promise<ConversationSummary[]> {
  return apiGet('/ai/conversations')
}

export function fetchConversation(id: number): Promise<Conversation> {
  return apiGet(`/ai/conversations/${id.toString()}`)
}

/** Begins a conversation with a question. It answers in the same breath, which can take a minute
 * or two: the assistant may look things up and ask the provider more than once. */
export function startConversation(
  text: string,
  csrfToken: string,
  page?: PageContext | null,
): Promise<Conversation> {
  return apiPost('/ai/conversations', { text, ...(page ? { page } : {}) }, csrfToken)
}

export function askInConversation(
  id: number,
  text: string,
  csrfToken: string,
  page?: PageContext | null,
): Promise<Conversation> {
  return apiPost(
    `/ai/conversations/${id.toString()}/messages`,
    { text, ...(page ? { page } : {}) },
    csrfToken,
  )
}

/** Asks the last question again after an answer that could not be made. */
export function retryConversation(id: number, csrfToken: string): Promise<Conversation> {
  return apiPost(`/ai/conversations/${id.toString()}/retry`, undefined, csrfToken)
}

export function deleteConversation(id: number, csrfToken: string): Promise<undefined> {
  return apiDelete(`/ai/conversations/${id.toString()}`, csrfToken)
}
