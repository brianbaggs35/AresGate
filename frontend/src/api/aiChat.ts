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

export interface ChatMessage {
  id: number
  role: 'user' | 'assistant'
  text: string
  /** False for an answer that could not be made: its text says why. */
  ok: boolean
  created_at: string
  lookups: ChatLookup[]
  cites: ChatCite[]
  /** The requests to the provider that made it, to read under Settings > AI usage. */
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
export function startConversation(text: string, csrfToken: string): Promise<Conversation> {
  return apiPost('/ai/conversations', { text }, csrfToken)
}

export function askInConversation(
  id: number,
  text: string,
  csrfToken: string,
): Promise<Conversation> {
  return apiPost(`/ai/conversations/${id.toString()}/messages`, { text }, csrfToken)
}

/** Asks the last question again after an answer that could not be made. */
export function retryConversation(id: number, csrfToken: string): Promise<Conversation> {
  return apiPost(`/ai/conversations/${id.toString()}/retry`, undefined, csrfToken)
}

export function deleteConversation(id: number, csrfToken: string): Promise<undefined> {
  return apiDelete(`/ai/conversations/${id.toString()}`, csrfToken)
}
