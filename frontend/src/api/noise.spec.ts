import * as client from '@/api/client'
import { fetchNoiseFilters, previewNoiseFilters, saveNoiseFilters } from '@/api/noise'

const DRAFT = {
  confidence_floor: 50,
  quiet_inside: true,
  source_floors: { wazuh: 'high' },
  scan_gap_hours: 8,
  brute_force_gap_hours: 2,
  thin_low_signals: 3,
} as const

describe('noise filters', () => {
  it('asks for them as they are kept', async () => {
    const get = vi.spyOn(client, 'apiGet').mockResolvedValue({ confidence_floor: 35 })

    await expect(fetchNoiseFilters()).resolves.toEqual({ confidence_floor: 35 })
    expect(get).toHaveBeenCalledWith('/noise-filters')
  })

  it('keeps them with the sign-in token', async () => {
    const put = vi.spyOn(client, 'apiPut').mockResolvedValue({ confidence_floor: 50 })

    await expect(saveNoiseFilters(DRAFT, 'a-token')).resolves.toEqual({ confidence_floor: 50 })
    expect(put).toHaveBeenCalledWith('/noise-filters', DRAFT, 'a-token')
  })

  it('asks what they would do with the sign-in token', async () => {
    const post = vi.spyOn(client, 'apiPost').mockResolvedValue({ now: {}, after: {} })

    await expect(previewNoiseFilters(DRAFT, 'a-token')).resolves.toEqual({ now: {}, after: {} })
    expect(post).toHaveBeenCalledWith('/noise-filters/preview', DRAFT, 'a-token')
  })
})
