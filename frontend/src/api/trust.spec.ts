import * as client from '@/api/client'
import {
  changeTrust,
  fetchSuggestions,
  fetchTrust,
  fetchTrusted,
  revokeManyTrust,
  revokeTrust,
  trust,
  trustSuggestions,
} from '@/api/trust'

describe('trust api', () => {
  it('lists the decisions', async () => {
    const get = vi.spyOn(client, 'apiGet').mockResolvedValue({ items: [], safe: 0 })

    await expect(fetchTrust()).resolves.toEqual({ items: [], safe: 0 })
    expect(get).toHaveBeenCalledWith('/trust')
  })

  it('reads the suggestions as their list', async () => {
    const get = vi.spyOn(client, 'apiGet').mockResolvedValue({ items: [{ incident_id: 9 }] })

    await expect(fetchSuggestions()).resolves.toEqual([{ incident_id: 9 }])
    expect(get).toHaveBeenCalledWith('/trust/suggestions')
  })

  it('reads one decision', async () => {
    const get = vi.spyOn(client, 'apiGet').mockResolvedValue({ id: 4 })

    await expect(fetchTrusted(4)).resolves.toEqual({ id: 4 })
    expect(get).toHaveBeenCalledWith('/trust/4')
  })

  it('trusts, with the sign-in token', async () => {
    const post = vi.spyOn(client, 'apiPost').mockResolvedValue({ id: 5 })

    await expect(trust({ address: '52.1.2.3' }, 'a-token')).resolves.toEqual({ id: 5 })
    expect(post).toHaveBeenCalledWith('/trust', { address: '52.1.2.3' }, 'a-token')
  })

  it('changes a decision, with the sign-in token', async () => {
    const put = vi.spyOn(client, 'apiPut').mockResolvedValue({ id: 5 })

    await expect(changeTrust(5, { note: '' }, 'a-token')).resolves.toEqual({ id: 5 })
    expect(put).toHaveBeenCalledWith('/trust/5', { note: '' }, 'a-token')
  })

  it('takes one back, with the sign-in token', async () => {
    const remove = vi.spyOn(client, 'apiDelete').mockResolvedValue(undefined)

    await revokeTrust(5, 'a-token')

    expect(remove).toHaveBeenCalledWith('/trust/5', 'a-token')
  })

  it('takes many back at once, with the sign-in token', async () => {
    const post = vi.spyOn(client, 'apiPost').mockResolvedValue({ done: 2, skipped: 0 })

    await expect(revokeManyTrust([5, 6], 'a-token')).resolves.toEqual({ done: 2, skipped: 0 })
    expect(post).toHaveBeenCalledWith('/trust/take-back', { ids: [5, 6] }, 'a-token')
  })

  it('trusts many suggestions as the AI read them', async () => {
    const post = vi.spyOn(client, 'apiPost').mockResolvedValue({ done: 2, skipped: 1 })

    await expect(trustSuggestions([7, 8, 9], 'a-token')).resolves.toEqual({ done: 2, skipped: 1 })
    expect(post).toHaveBeenCalledWith('/trust/accept', { incident_ids: [7, 8, 9] }, 'a-token')
  })

  it('trusts many suggestions as one level, when the owner says so', async () => {
    const post = vi.spyOn(client, 'apiPost').mockResolvedValue({ done: 1, skipped: 0 })

    await trustSuggestions([7], 'a-token', 'low_priority')

    expect(post).toHaveBeenCalledWith(
      '/trust/accept',
      { incident_ids: [7], verdict: 'low_priority' },
      'a-token',
    )
  })
})
