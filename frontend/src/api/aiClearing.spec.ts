import * as client from '@/api/client'
import { fetchClearing, previewClearing, saveClearing, type ClearingDraft } from '@/api/aiClearing'
import { clearing, clearingPreview } from '@/test/aiClearing'

const DRAFT: ClearingDraft = {
  mode: 'automatic',
  minimum: 90,
  kinds: ['noise'],
  sources: [],
  ceiling: 'low',
  daily_cap: 5,
}

describe('AI clearing API', () => {
  it('asks for the settings', async () => {
    const answer = clearing()
    const get = vi.spyOn(client, 'apiGet').mockResolvedValue(answer)

    await expect(fetchClearing()).resolves.toBe(answer)
    expect(get).toHaveBeenCalledWith('/ai/clearing')
  })

  it('keeps them', async () => {
    const answer = clearing()
    const put = vi.spyOn(client, 'apiPut').mockResolvedValue(answer)

    await expect(saveClearing(DRAFT, 'a-token')).resolves.toBe(answer)
    expect(put).toHaveBeenCalledWith('/ai/clearing', DRAFT, 'a-token')
  })

  it('asks what they would have cleared', async () => {
    const answer = clearingPreview()
    const post = vi.spyOn(client, 'apiPost').mockResolvedValue(answer)

    await expect(previewClearing(DRAFT, 'a-token')).resolves.toBe(answer)
    expect(post).toHaveBeenCalledWith('/ai/clearing/preview', DRAFT, 'a-token')
  })
})
