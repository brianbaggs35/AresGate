import * as client from '@/api/client'
import { fetchKnownThreats, searchThreatIntel } from '@/api/threatIntel'

describe('threatIntel', () => {
  it('asks VirusTotal about one subject with the security token', async () => {
    const post = vi.spyOn(client, 'apiPost').mockResolvedValue({ kind: 'ip' })

    await expect(searchThreatIntel('203.0.113.7', 'a-security-token')).resolves.toEqual({
      kind: 'ip',
    })
    expect(post).toHaveBeenCalledWith(
      '/threat-intel/lookups',
      { subject: '203.0.113.7' },
      'a-security-token',
    )
  })

  it('asks VirusTotal again when a newer answer is wanted', async () => {
    const post = vi.spyOn(client, 'apiPost').mockResolvedValue({ kind: 'ip' })

    await searchThreatIntel('203.0.113.7', 'a-security-token', true)

    expect(post).toHaveBeenCalledWith(
      '/threat-intel/lookups',
      { subject: '203.0.113.7', refresh: true },
      'a-security-token',
    )
  })

  it('reads everything kept when nothing narrows it', async () => {
    const get = vi.spyOn(client, 'apiGet').mockResolvedValue({ total: 0 })

    await expect(fetchKnownThreats()).resolves.toEqual({ total: 0 })
    expect(get).toHaveBeenCalledWith('/threat-intel/subjects')
  })

  it('leaves out what is empty of a query for what is kept', async () => {
    const get = vi.spyOn(client, 'apiGet').mockResolvedValue({ total: 0 })

    await fetchKnownThreats({ q: '', kind: null, judgement: null, offset: 0 })

    expect(get).toHaveBeenCalledWith('/threat-intel/subjects')
  })

  it('narrows what is kept by text, kind and judgement, a page at a time', async () => {
    const get = vi.spyOn(client, 'apiGet').mockResolvedValue({ total: 0 })

    await fetchKnownThreats({
      q: 'example & co',
      kind: 'domain',
      judgement: 'malicious',
      limit: 50,
      offset: 25,
    })

    expect(get).toHaveBeenCalledWith(
      '/threat-intel/subjects?q=example+%26+co&kind=domain&judgement=malicious&limit=50&offset=25',
    )
  })
})
