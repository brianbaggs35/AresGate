import { ApiError, apiDelete, apiGet, apiPost, apiStream } from '@/api/client'

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

/** What happens while the assistant answers: a lookup it has run, and what it found in a few
 * words, then the answer as it is written. `dropped` says that what was written was not the answer
 * after all (the assistant went to look something up, or failed). */
export type AnswerEvent =
  { kind: 'looked'; lookup: ChatLookup } | { kind: 'wrote'; text: string } | { kind: 'dropped' }

/** Asks a question, in a conversation or (with no `id`) to begin one, and tells what happens as it
 * happens. Resolves with the conversation as it is kept, once the answer has ended; a connection
 * that broke before that is an error, and nothing was kept. */
export async function askAndFollow(
  id: number | null,
  text: string,
  csrfToken: string,
  page: PageContext | null,
  onEvent: (event: AnswerEvent) => void,
): Promise<Conversation> {
  const result: { conversation?: Conversation } = {}
  const path =
    id === null ? '/ai/conversations/stream' : `/ai/conversations/${id.toString()}/stream`
  await apiStream(path, { text, ...(page ? { page } : {}) }, csrfToken, ({ name, data }) => {
    if (name === 'done') result.conversation = data as Conversation
    else if (name === 'looked') onEvent({ kind: 'looked', lookup: data as ChatLookup })
    else if (name === 'wrote') onEvent({ kind: 'wrote', text: (data as { text: string }).text })
    else if (name === 'dropped') onEvent({ kind: 'dropped' })
  })
  if (result.conversation === undefined) {
    throw new ApiError(0, 'The answer was cut off before the end. Ask again.', 'cut_off')
  }
  return result.conversation
}

/** Asks the last question again after an answer that could not be made. */
export function retryConversation(id: number, csrfToken: string): Promise<Conversation> {
  return apiPost(`/ai/conversations/${id.toString()}/retry`, undefined, csrfToken)
}

export function deleteConversation(id: number, csrfToken: string): Promise<undefined> {
  return apiDelete(`/ai/conversations/${id.toString()}`, csrfToken)
}
