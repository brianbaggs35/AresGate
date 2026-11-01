import type { ChatMessage, Conversation, ConversationSummary } from '@/api/aiChat'

/** What the chat API answers, for tests of the pages that show it. */

export function question(over: Partial<ChatMessage> = {}): ChatMessage {
  return {
    id: 1,
    role: 'user',
    text: 'What needs my attention right now?',
    ok: true,
    created_at: '2026-11-01T10:00:00Z',
    lookups: [],
    cites: [],
    call_ids: [],
    ...over,
  }
}

export function answer(over: Partial<ChatMessage> = {}): ChatMessage {
  return {
    id: 2,
    role: 'assistant',
    text: 'Start with [incident 3]: it is the one that needs you most.',
    ok: true,
    created_at: '2026-11-01T10:00:20Z',
    lookups: [{ tool: 'open_incidents', summary: '2 open incidents' }],
    cites: [{ kind: 'incident', key: '3', label: 'Incident 3' }],
    call_ids: [11, 12],
    ...over,
  }
}

export function conversation(over: Partial<Conversation> = {}): Conversation {
  return {
    id: 5,
    title: 'What needs my attention right now?',
    created_at: '2026-11-01T10:00:00Z',
    updated_at: '2026-11-01T10:00:20Z',
    messages: [question(), answer()],
    ...over,
  }
}

export function summary(over: Partial<ConversationSummary> = {}): ConversationSummary {
  return {
    id: 5,
    title: 'What needs my attention right now?',
    updated_at: '2026-11-01T10:00:20Z',
    messages: 2,
    ...over,
  }
}
