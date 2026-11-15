import * as client from '@/api/client'
import { fetchDevice, fetchDevices } from '@/api/devices'

describe('devices', () => {
  it('lists the devices when asked for nothing in particular', async () => {
    const get = vi.spyOn(client, 'apiGet').mockResolvedValue({ items: [], total: 0 })

    await expect(fetchDevices()).resolves.toEqual({ items: [], total: 0 })

    expect(get).toHaveBeenCalledWith('/devices')
  })

  it('narrows the devices by what is asked for', async () => {
    const get = vi.spyOn(client, 'apiGet').mockResolvedValue({ items: [], total: 0 })

    await fetchDevices({
      q: 'nas',
      scope: 'local',
      direction: 'outgoing',
      flagged: true,
      sort: 'busiest',
      limit: 25,
      offset: 50,
    })

    expect(get).toHaveBeenCalledWith(
      '/devices?q=nas&scope=local&direction=outgoing&flagged=true&sort=busiest&limit=25&offset=50',
    )
  })

  it('leaves out what means everything, and the first page', async () => {
    const get = vi.spyOn(client, 'apiGet').mockResolvedValue({ items: [], total: 0 })

    await fetchDevices({ q: '', flagged: false, limit: 0, offset: 0 })

    expect(get).toHaveBeenCalledWith('/devices?limit=0')
  })

  it('asks for one device by its address, which is written so it fits in a path', async () => {
    const get = vi.spyOn(client, 'apiGet').mockResolvedValue({ device: {} })

    await fetchDevice('fe80::1')

    expect(get).toHaveBeenCalledWith('/devices/fe80%3A%3A1')
  })
})
