import * as client from '@/api/client'
import {
  askAndFollow,
  type AnswerEvent,
  deleteConversation,
  fetchConversation,
  fetchConversations,
  retryConversation,
} from '@/api/aiChat'

describe('AI chat API', () => {
  it('lists the conversations', async () => {
    const answer = [{ id: 1 }]
    const get = vi.spyOn(client, 'apiGet').mockResolvedValue(answer)

    await expect(fetchConversations()).resolves.toBe(answer)
    expect(get).toHaveBeenCalledWith('/ai/conversations')
  })

  it('opens one conversation', async () => {
    const get = vi.spyOn(client, 'apiGet').mockResolvedValue({ id: 7 })

    await fetchConversation(7)

    expect(get).toHaveBeenCalledWith('/ai/conversations/7')
  })

  it('begins a conversation by streaming a question, with the page it is asked from', async () => {
    const stream = vi.spyOn(client, 'apiStream').mockImplementation((_path, _body, _token, on) => {
      on({ name: 'conversation', data: { id: 9 } })
      on({ name: 'done', data: { id: 9, messages: [] } })
      return Promise.resolve()
    })
    const page = { kind: 'incident', id: 3 } as const

    const done = await askAndFollow(null, 'Anything?', 'a-token', page, vi.fn())

    expect(done).toEqual({ id: 9, messages: [] })
    expect(stream).toHaveBeenCalledWith(
      '/ai/conversations/stream',
      { text: 'Anything?', page },
      'a-token',
      expect.any(Function),
    )
  })

  it('asks in a conversation, and tells what happens as it happens', async () => {
    const stream = vi.spyOn(client, 'apiStream').mockImplementation((_path, _body, _token, on) => {
      on({ name: 'looked', data: { tool: 'alerts', summary: '3 alerts' } })
      on({ name: 'wrote', data: { text: 'Fine' } })
      on({ name: 'dropped', data: {} })
      on({ name: 'wrote', data: { text: 'Fine.' } })
      on({ name: 'something_new', data: {} })
      on({ name: 'done', data: { id: 4, messages: [] } })
      return Promise.resolve()
    })
    const told: AnswerEvent[] = []

    await askAndFollow(4, 'And now?', 'a-token', null, (event) => told.push(event))

    expect(stream).toHaveBeenCalledWith(
      '/ai/conversations/4/stream',
      { text: 'And now?' },
      'a-token',
      expect.any(Function),
    )
    expect(told).toEqual([
      { kind: 'looked', lookup: { tool: 'alerts', summary: '3 alerts' } },
      { kind: 'wrote', text: 'Fine' },
      { kind: 'dropped' },
      { kind: 'wrote', text: 'Fine.' },
    ])
  })

  it('is an error when the stream ends without saying the answer is kept', async () => {
    vi.spyOn(client, 'apiStream').mockResolvedValue(undefined)

    await expect(askAndFollow(4, 'And now?', 'a-token', null, vi.fn())).rejects.toMatchObject({
      code: 'cut_off',
      message: 'The answer was cut off before the end. Ask again.',
    })
  })

  it('asks the last question again', async () => {
    const post = vi.spyOn(client, 'apiPost').mockResolvedValue({ id: 4 })

    await retryConversation(4, 'a-token')

    expect(post).toHaveBeenCalledWith('/ai/conversations/4/retry', undefined, 'a-token')
  })

  it('deletes a conversation', async () => {
    const del = vi.spyOn(client, 'apiDelete').mockResolvedValue(undefined)

    await deleteConversation(4, 'a-token')

    expect(del).toHaveBeenCalledWith('/ai/conversations/4', 'a-token')
  })
})
