import * as client from '@/api/client'
import {
  fetchThreatSettings,
  previewThreatSettings,
  saveThreatSettings,
  type ThreatDraft,
} from '@/api/threatSettings'

const DRAFT: ThreatDraft = {
  threat_from: 70,
  ai_may_clear: true,
  clear_from: 85,
  ai_confirms: true,
  exposure: 'some',
  exposed_ports: [443],
  notes: 'A web server',
  important_drop: 15,
  low_raise: 5,
}

describe('threat settings', () => {
  it('asks for them as they are kept', async () => {
    const get = vi.spyOn(client, 'apiGet').mockResolvedValue({ threat_from: 65 })

    await expect(fetchThreatSettings()).resolves.toEqual({ threat_from: 65 })
    expect(get).toHaveBeenCalledWith('/threat-settings')
  })

  it('keeps them with the sign-in token', async () => {
    const put = vi.spyOn(client, 'apiPut').mockResolvedValue({ threat_from: 70 })

    await expect(saveThreatSettings(DRAFT, 'a-token')).resolves.toEqual({ threat_from: 70 })
    expect(put).toHaveBeenCalledWith('/threat-settings', DRAFT, 'a-token')
  })

  it('asks what they would do with the sign-in token', async () => {
    const post = vi.spyOn(client, 'apiPost').mockResolvedValue({ now: {}, after: {} })

    await expect(previewThreatSettings(DRAFT, 'a-token')).resolves.toEqual({ now: {}, after: {} })
    expect(post).toHaveBeenCalledWith('/threat-settings/preview', DRAFT, 'a-token')
  })
})
