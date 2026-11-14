import * as client from '@/api/client'
import {
  fetchRetentionSettings,
  saveRetentionSettings,
  type RetentionDraft,
} from '@/api/retentionSettings'

const DRAFT: RetentionDraft = { managed: true, keep_forever: false, days: 14, quota_gb: 20 }

describe('retention settings', () => {
  it('asks for them as they are kept', async () => {
    const get = vi.spyOn(client, 'apiGet').mockResolvedValue({ days: 30 })

    await expect(fetchRetentionSettings()).resolves.toEqual({ days: 30 })
    expect(get).toHaveBeenCalledWith('/retention-settings')
  })

  it('keeps them with the sign-in token', async () => {
    const put = vi.spyOn(client, 'apiPut').mockResolvedValue({ days: 14 })

    await expect(saveRetentionSettings(DRAFT, 'a-token')).resolves.toEqual({ days: 14 })
    expect(put).toHaveBeenCalledWith('/retention-settings', DRAFT, 'a-token')
  })
})
