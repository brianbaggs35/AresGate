import * as client from '@/api/client'
import {
  askInConversation,
  deleteConversation,
  fetchConversation,
  fetchConversations,
  retryConversation,
  startConversation,
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

  it('begins a conversation with a question and the security token', async () => {
    const post = vi.spyOn(client, 'apiPost').mockResolvedValue({ id: 1 })

    await startConversation('Anything?', 'a-token')

    expect(post).toHaveBeenCalledWith('/ai/conversations', { text: 'Anything?' }, 'a-token')
  })

  it('asks in a conversation', async () => {
    const post = vi.spyOn(client, 'apiPost').mockResolvedValue({ id: 4 })

    await askInConversation(4, 'And now?', 'a-token')

    expect(post).toHaveBeenCalledWith(
      '/ai/conversations/4/messages',
      { text: 'And now?' },
      'a-token',
    )
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
