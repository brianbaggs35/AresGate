import { createPinia, setActivePinia } from 'pinia'

import * as aiApi from '@/api/ai'
import * as chatApi from '@/api/aiChat'
import { ApiError } from '@/api/client'
import { MAX_QUESTION } from '@/chat'
import { useAssistantStore } from '@/stores/assistant'
import { useSessionStore } from '@/stores/session'
import { ai as aiSettings } from '@/test/ai'
import { answer, conversation } from '@/test/aiChat'

function store() {
  setActivePinia(createPinia())
  useSessionStore().$patch({ known: true, username: 'admin', csrfToken: 'token' })
  return useAssistantStore()
}

describe('assistant store', () => {
  it('opens and closes, and asks whether an AI is set up the first time it opens', async () => {
    const fetchAi = vi
      .spyOn(aiApi, 'fetchAi')
      .mockResolvedValue(aiSettings({ enabled: true, provider: 'anthropic' }))
    const assistant = store()

    assistant.toggle()
    expect(assistant.open).toBe(true)
    await vi.waitFor(() => {
      expect(assistant.ready).toBe(true)
    })
    assistant.toggle()
    expect(assistant.open).toBe(false)
    assistant.show()
    expect(fetchAi).toHaveBeenCalledTimes(1)
  })

  it('knows when there is no provider, and leaves it unknown when it cannot ask', async () => {
    vi.spyOn(aiApi, 'fetchAi').mockResolvedValue(aiSettings({ enabled: true, provider: null }))
    const off = store()
    off.show()
    await vi.waitFor(() => {
      expect(off.ready).toBe(false)
    })

    vi.spyOn(aiApi, 'fetchAi').mockRejectedValue(new Error('offline'))
    const unknown = store()
    unknown.show()
    await new Promise((resolve) => setTimeout(resolve))
    expect(unknown.ready).toBeNull()
  })

  it('will not send an empty, a too long or a busy question', () => {
    const assistant = store()
    expect(assistant.canSend).toBe(false)
    assistant.draft = 'x'.repeat(MAX_QUESTION + 1)
    expect(assistant.tooLong).toBe(true)
    expect(assistant.canSend).toBe(false)
    assistant.draft = 'Hello'
    expect(assistant.canSend).toBe(true)
    assistant.sending = true
    expect(assistant.canSend).toBe(false)
  })

  it('starts a conversation with the page it is asked from, then carries it on', async () => {
    const start = vi.spyOn(chatApi, 'askAndFollow').mockResolvedValue(conversation())
    const assistant = store()
    const page = { kind: 'incident', id: 3 } as const

    assistant.draft = '  Is this bad?  '
    const sent = assistant.send(page)
    expect(assistant.sending).toBe(true)
    expect(assistant.pending).toBe('Is this bad?')
    await sent

    expect(start).toHaveBeenCalledWith(null, 'Is this bad?', 'token', page, expect.any(Function))
    expect(assistant.current?.id).toBe(5)
    expect(assistant.draft).toBe('')
    expect(assistant.sending).toBe(false)
    expect(assistant.pending).toBeNull()

    assistant.draft = 'And?'
    await assistant.send(null)
    expect(start).toHaveBeenLastCalledWith(5, 'And?', 'token', null, expect.any(Function))
  })

  it('keeps what the answer has looked at and written while it is made, and clears it after', async () => {
    let finish: (found: chatApi.Conversation) => void = () => undefined
    let follow: (event: chatApi.AnswerEvent) => void = () => undefined
    vi.spyOn(chatApi, 'askAndFollow').mockImplementation((_id, _text, _token, _page, onEvent) => {
      follow = onEvent
      return new Promise((resolve) => {
        finish = resolve
      })
    })
    const assistant = store()
    assistant.draft = 'Hello'
    const sent = assistant.send(null)

    follow({ kind: 'looked', lookup: { tool: 'open_incidents', summary: '2 open incidents' } })
    follow({ kind: 'wrote', text: 'Start ' })
    follow({ kind: 'wrote', text: 'with 3.' })
    expect(assistant.looked).toEqual([{ tool: 'open_incidents', summary: '2 open incidents' }])
    expect(assistant.writing).toBe('Start with 3.')

    finish(conversation())
    await sent
    expect(assistant.looked).toEqual([])
    expect(assistant.writing).toBe('')
  })

  it('does nothing where it may not send', async () => {
    const start = vi.spyOn(chatApi, 'askAndFollow')
    await store().send(null)
    expect(start).not.toHaveBeenCalled()
  })

  it('keeps the question in the box when it could not be answered', async () => {
    vi.spyOn(chatApi, 'askAndFollow').mockRejectedValue(
      new ApiError(0, "Can't reach AresGate.", 'offline'),
    )
    const assistant = store()
    assistant.draft = 'Hello'
    await assistant.send(null)
    expect(assistant.failure).toBe("Can't reach AresGate.")
    expect(assistant.draft).toBe('Hello')
    expect(assistant.sending).toBe(false)
  })

  it('offers to ask again only for a failed last answer, and asks', async () => {
    const failed = conversation({ messages: [answer({ id: 9, ok: false })] })
    const retried = vi.spyOn(chatApi, 'retryConversation').mockResolvedValue(conversation())
    const assistant = store()
    expect(assistant.retryable).toBeNull()

    assistant.current = failed
    expect(assistant.retryable).toBe(9)
    await assistant.retry()
    expect(retried).toHaveBeenCalledWith(5, 'token')
    expect(assistant.retryable).toBeNull()
  })

  it('begins a new conversation, leaving the old one on the Assistant page', () => {
    const assistant = store()
    assistant.current = conversation()
    assistant.draft = 'half'
    assistant.failure = 'x'
    assistant.begin()
    expect(assistant.current).toBeNull()
    expect(assistant.draft).toBe('')
    expect(assistant.failure).toBeNull()
  })

  it('forgets everything on sign-out', () => {
    const assistant = store()
    assistant.open = true
    assistant.current = conversation()
    assistant.draft = 'x'
    assistant.ready = true
    assistant.writing = 'half an answer'
    assistant.reset()
    expect(assistant.writing).toBe('')
    expect(assistant.open).toBe(false)
    expect(assistant.current).toBeNull()
    expect(assistant.draft).toBe('')
    expect(assistant.ready).toBeNull()
  })
})
