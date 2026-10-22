import * as auth from '@/api/auth'
import * as client from '@/api/client'

const session = { username: 'admin', csrf_token: 'a-token', expires_at: '2026-01-01T12:00:00Z' }

describe('auth API', () => {
  it('asks whether the install needs setting up', async () => {
    const get = vi.spyOn(client, 'apiGet').mockResolvedValue({ setup_required: true })
    await expect(auth.fetchSetupRequired()).resolves.toBe(true)
    expect(get).toHaveBeenCalledWith('/setup/status')
  })

  it("reads who is signed in from the API's session", async () => {
    const get = vi.spyOn(client, 'apiGet').mockResolvedValue(session)
    await expect(auth.fetchSession()).resolves.toEqual(session)
    expect(get).toHaveBeenCalledWith('/auth/session')
  })

  it('creates the account with the setup code', async () => {
    const post = vi.spyOn(client, 'apiPost').mockResolvedValue(session)
    const setup = { code: 'K7QD-3MWX-9HPA', username: 'admin', password: 'a long enough phrase' }
    await expect(auth.setUp(setup)).resolves.toEqual(session)
    expect(post).toHaveBeenCalledWith('/setup', setup)
  })

  it('signs in', async () => {
    const post = vi.spyOn(client, 'apiPost').mockResolvedValue(session)
    const credentials = { username: 'admin', password: 'a long enough phrase' }
    await expect(auth.logIn(credentials)).resolves.toEqual(session)
    expect(post).toHaveBeenCalledWith('/auth/login', credentials)
  })

  it('signs out with the security token', async () => {
    const post = vi.spyOn(client, 'apiPost').mockResolvedValue(undefined)
    await auth.logOut('a-token')
    expect(post).toHaveBeenCalledWith('/auth/logout', undefined, 'a-token')
  })
})
