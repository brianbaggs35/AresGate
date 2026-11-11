import * as client from '@/api/client'
import {
  fetchKnownThreats,
  fetchRulings,
  ruleOnThreat,
  searchThreatIntel,
  takeBackRuling,
} from '@/api/threatIntel'

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

  it('reads everything the owner has ruled', async () => {
    const get = vi.spyOn(client, 'apiGet').mockResolvedValue({ items: [] })

    await expect(fetchRulings()).resolves.toEqual({ items: [] })
    expect(get).toHaveBeenCalledWith('/threat-intel/overrides')
  })

  it('rules a subject safe or suspicious, with a reason or none, with the security token', async () => {
    const put = vi.spyOn(client, 'apiPut').mockResolvedValue({ verdict: 'safe' })

    await expect(
      ruleOnThreat('203.0.113.7', 'safe', 'A friend', 'a-security-token'),
    ).resolves.toEqual({ verdict: 'safe' })
    await ruleOnThreat('example.com', 'suspicious', null, 'a-security-token')

    expect(put).toHaveBeenNthCalledWith(
      1,
      '/threat-intel/overrides',
      { subject: '203.0.113.7', verdict: 'safe', note: 'A friend' },
      'a-security-token',
    )
    expect(put).toHaveBeenNthCalledWith(
      2,
      '/threat-intel/overrides',
      { subject: 'example.com', verdict: 'suspicious', note: null },
      'a-security-token',
    )
  })

  it('takes a ruling back by its subject, which is made safe to put in an address', async () => {
    const remove = vi.spyOn(client, 'apiDelete').mockResolvedValue(undefined)

    await takeBackRuling('https://example.com/a?b=1', 'a-security-token')

    expect(remove).toHaveBeenCalledWith(
      '/threat-intel/overrides?subject=https%3A%2F%2Fexample.com%2Fa%3Fb%3D1',
      'a-security-token',
    )
  })
})
