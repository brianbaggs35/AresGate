import {
  expectPlace,
  fetchBaselineInterfaces,
  fetchBaselinePlaces,
  fetchBaselineTalkers,
  forgetPlace,
} from '@/api/baselines'
import * as client from '@/api/client'

describe('baselines API', () => {
  it('reads what is usual for the interfaces and which devices have places', async () => {
    const get = vi.spyOn(client, 'apiGet').mockResolvedValue({})

    await fetchBaselineInterfaces()
    await fetchBaselineTalkers()

    expect(get).toHaveBeenNthCalledWith(1, '/baselines/interfaces')
    expect(get).toHaveBeenNthCalledWith(2, '/baselines/devices')
  })

  it('reads the places of a device, with its address made safe for a path', async () => {
    const get = vi.spyOn(client, 'apiGet').mockResolvedValue({})

    await fetchBaselinePlaces('fd00::5')

    expect(get).toHaveBeenCalledWith('/baselines/devices/fd00%3A%3A5')
  })

  it('says a place is expected, and forgets one', async () => {
    const put = vi.spyOn(client, 'apiPut').mockResolvedValue({})
    const post = vi.spyOn(client, 'apiPost').mockResolvedValue(undefined)
    const place = { network: '198.51.100.0/24', port: 443 }

    await expectPlace('192.168.1.20', { ...place, expected: true }, 'token')
    await forgetPlace('192.168.1.20', place, 'token')

    expect(put).toHaveBeenCalledWith(
      '/baselines/devices/192.168.1.20/places',
      { ...place, expected: true },
      'token',
    )
    expect(post).toHaveBeenCalledWith('/baselines/devices/192.168.1.20/forget', place, 'token')
  })
})
