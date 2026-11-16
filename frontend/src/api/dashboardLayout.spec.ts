import * as client from '@/api/client'
import { LIVE_PATH, fetchLayout, resetLayout, saveLayout } from '@/api/dashboardLayout'

describe('dashboard layout api', () => {
  it('asks for the layout', async () => {
    const get = vi.spyOn(client, 'apiGet').mockResolvedValue({ widgets: [] })

    await expect(fetchLayout()).resolves.toEqual({ widgets: [] })
    expect(get).toHaveBeenCalledWith('/dashboard/layout')
  })

  it('saves the layout with the sign-in token', async () => {
    const put = vi.spyOn(client, 'apiPut').mockResolvedValue({ widgets: [] })
    const layout = {
      preset: null,
      widgets: [{ id: 'traffic', size: 'half' as const, hidden: false }],
    }

    await saveLayout(layout, 'token')

    expect(put).toHaveBeenCalledWith('/dashboard/layout', layout, 'token')
  })

  it('puts the first preset back with the sign-in token', async () => {
    const remove = vi.spyOn(client, 'apiDelete').mockResolvedValue(undefined)

    await resetLayout('token')

    expect(remove).toHaveBeenCalledWith('/dashboard/layout', 'token')
  })

  it('listens for changes at the stream the API serves', () => {
    expect(LIVE_PATH).toBe('/api/dashboard/stream')
  })
})
