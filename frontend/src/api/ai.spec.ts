import {
  fetchAi,
  fetchProviderModels,
  removeProvider,
  saveProvider,
  testProvider,
  useAi,
} from '@/api/ai'
import * as client from '@/api/client'

describe('ai', () => {
  it('lists the providers and whether AI is used', async () => {
    const get = vi.spyOn(client, 'apiGet').mockResolvedValue({ enabled: false })

    await expect(fetchAi()).resolves.toEqual({ enabled: false })
    expect(get).toHaveBeenCalledWith('/ai')
  })

  it('keeps a provider with the sign-in token', async () => {
    const put = vi.spyOn(client, 'apiPut').mockResolvedValue({ key: 'openai' })
    const settings = { model: 'gpt-6-luna', api_key: 'a-key' }

    await expect(saveProvider('openai', settings, 'a-token')).resolves.toEqual({ key: 'openai' })
    expect(put).toHaveBeenCalledWith('/ai/providers/openai', settings, 'a-token')
  })

  it('forgets a provider with the sign-in token', async () => {
    const remove = vi.spyOn(client, 'apiDelete').mockResolvedValue(undefined)

    await removeProvider('ollama', 'a-token')

    expect(remove).toHaveBeenCalledWith('/ai/providers/ollama', 'a-token')
  })

  it('tests a provider and asks an Ollama for its models, with the sign-in token', async () => {
    const post = vi.spyOn(client, 'apiPost').mockResolvedValue({ ok: true })

    await testProvider('anthropic', 'a-token')
    await fetchProviderModels('ollama_cloud', 'a-token')

    expect(post).toHaveBeenNthCalledWith(1, '/ai/providers/anthropic/test', undefined, 'a-token')
    expect(post).toHaveBeenNthCalledWith(
      2,
      '/ai/providers/ollama_cloud/models',
      undefined,
      'a-token',
    )
  })

  it('turns AI on for a provider', async () => {
    const put = vi.spyOn(client, 'apiPut').mockResolvedValue({ enabled: true })

    await useAi({ enabled: true, provider: 'anthropic' }, 'a-token')

    expect(put).toHaveBeenCalledWith('/ai/use', { enabled: true, provider: 'anthropic' }, 'a-token')
  })
})
