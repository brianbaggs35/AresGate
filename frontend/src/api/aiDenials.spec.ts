import * as client from '@/api/client'
import {
  denyProposal,
  fetchDenials,
  forgetAllDenials,
  forgetDenial,
  type DenyDraft,
} from '@/api/aiDenials'
import { denials } from '@/test/aiDenials'

describe('AI denials API', () => {
  it('asks what stands denied', async () => {
    const answer = denials()
    const get = vi.spyOn(client, 'apiGet').mockResolvedValue(answer)

    await expect(fetchDenials()).resolves.toBe(answer)
    expect(get).toHaveBeenCalledWith('/ai/denials')
  })

  it('remembers a denial', async () => {
    const post = vi.spyOn(client, 'apiPost').mockResolvedValue({ recorded: 2 })
    const draft: DenyDraft = { kind: 'status', value: 'dismissed', incident_ids: [1, 2] }

    await expect(denyProposal(draft, 'a-token')).resolves.toEqual({ recorded: 2 })
    expect(post).toHaveBeenCalledWith('/ai/denials', draft, 'a-token')
  })

  it('forgets one', async () => {
    const del = vi.spyOn(client, 'apiDelete').mockResolvedValue(undefined)

    await forgetDenial(7, 'a-token')

    expect(del).toHaveBeenCalledWith('/ai/denials/7', 'a-token')
  })

  it('forgets all', async () => {
    const del = vi.spyOn(client, 'apiDelete').mockResolvedValue({ forgotten: 3 })

    await expect(forgetAllDenials('a-token')).resolves.toEqual({ forgotten: 3 })
    expect(del).toHaveBeenCalledWith('/ai/denials', 'a-token')
  })
})
