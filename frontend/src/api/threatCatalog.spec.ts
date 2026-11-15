import * as client from '@/api/client'
import { fetchCves, fetchDeviceIntel } from '@/api/threatCatalog'

describe('threatCatalog', () => {
  it('reads the CVEs that are kept when nothing narrows them', async () => {
    const get = vi.spyOn(client, 'apiGet').mockResolvedValue({ total: 0 })

    await expect(fetchCves()).resolves.toEqual({ total: 0 })
    expect(get).toHaveBeenCalledWith('/threat-intel/cves')
  })

  it('leaves out what is empty of a query for CVEs', async () => {
    const get = vi.spyOn(client, 'apiGet').mockResolvedValue({ total: 0 })

    await fetchCves({ q: '', rating: null, exploited: false, offset: 0 })

    expect(get).toHaveBeenCalledWith('/threat-intel/cves')
  })

  it('narrows the CVEs by text, rating and whether they are exploited, a page at a time', async () => {
    const get = vi.spyOn(client, 'apiGet').mockResolvedValue({ total: 0 })

    await fetchCves({ q: 'CWE-77 & co', rating: 'high', exploited: true, limit: 50, offset: 25 })

    expect(get).toHaveBeenCalledWith(
      '/threat-intel/cves?q=CWE-77+%26+co&rating=high&exploited=true&limit=50&offset=25',
    )
  })

  it('reads the devices that were asked about when nothing narrows them', async () => {
    const get = vi.spyOn(client, 'apiGet').mockResolvedValue({ total: 0 })

    await expect(fetchDeviceIntel()).resolves.toEqual({ total: 0 })
    expect(get).toHaveBeenCalledWith('/threat-intel/devices')
  })

  it('leaves out what is empty of a query for devices', async () => {
    const get = vi.spyOn(client, 'apiGet').mockResolvedValue({ total: 0 })

    await fetchDeviceIntel({ q: '', state: null, offset: 0 })

    expect(get).toHaveBeenCalledWith('/threat-intel/devices')
  })

  it('narrows the devices by text and by what Fingerbank made of them, a page at a time', async () => {
    const get = vi.spyOn(client, 'apiGet').mockResolvedValue({ total: 0 })

    await fetchDeviceIntel({ q: 'nest cam', state: 'identified', limit: 50, offset: 25 })

    expect(get).toHaveBeenCalledWith(
      '/threat-intel/devices?q=nest+cam&state=identified&limit=50&offset=25',
    )
  })
})
