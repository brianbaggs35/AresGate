import * as account from '@/api/account'
import * as client from '@/api/client'

describe('account API', () => {
  it('changes the password with the current one and the security token', async () => {
    const post = vi.spyOn(client, 'apiPost').mockResolvedValue({ ended: 2 })
    await expect(account.changePassword('the old one', 'the new one', 'a-token')).resolves.toEqual({
      ended: 2,
    })
    expect(post).toHaveBeenCalledWith(
      '/auth/password',
      { current_password: 'the old one', new_password: 'the new one' },
      'a-token',
    )
  })

  it('lists where the account is signed in', async () => {
    const list = [
      {
        id: 'a',
        current: true,
        address: '192.168.1.20',
        user_agent: null,
        started_at: '2026-01-01T00:00:00Z',
        last_seen_at: '2026-01-01T00:05:00Z',
        expires_at: '2026-01-01T00:35:00Z',
      },
    ]
    const get = vi.spyOn(client, 'apiGet').mockResolvedValue(list)
    await expect(account.fetchSignIns()).resolves.toEqual(list)
    expect(get).toHaveBeenCalledWith('/auth/sessions')
  })

  it('signs one browser out', async () => {
    const post = vi.spyOn(client, 'apiPost').mockResolvedValue(undefined)
    await account.endSignIn('some/id', 'a-token')
    expect(post).toHaveBeenCalledWith('/auth/sessions/some%2Fid/end', undefined, 'a-token')
  })

  it('signs out every other browser, and says how many there were', async () => {
    const post = vi.spyOn(client, 'apiPost').mockResolvedValue({ ended: 3 })
    await expect(account.endOtherSignIns('a-token')).resolves.toEqual({ ended: 3 })
    expect(post).toHaveBeenCalledWith('/auth/sessions/end-others', undefined, 'a-token')
  })
})
