import * as client from '@/api/client'
import {
  disconnectIntegration,
  fetchCalls,
  fetchIntegration,
  fetchIntegrations,
  lookUpCertificate,
  saveIntegration,
  testIntegration,
  type ConnectionSettings,
} from '@/api/integrations'

const TOKEN = 'a-security-token'

describe('integrations', () => {
  it('lists them', async () => {
    const get = vi.spyOn(client, 'apiGet').mockResolvedValue([{ key: 'opnsense' }])
    await expect(fetchIntegrations()).resolves.toEqual([{ key: 'opnsense' }])
    expect(get).toHaveBeenCalledWith('/integrations')
  })

  it('reads one', async () => {
    const get = vi.spyOn(client, 'apiGet').mockResolvedValue({ key: 'ntopng' })
    await expect(fetchIntegration('ntopng')).resolves.toEqual({ key: 'ntopng' })
    expect(get).toHaveBeenCalledWith('/integrations/ntopng')
  })

  it('keeps a name from changing the address it asks for', async () => {
    const get = vi.spyOn(client, 'apiGet').mockResolvedValue({})
    await fetchIntegration('a/b?c')
    expect(get).toHaveBeenCalledWith('/integrations/a%2Fb%3Fc')
  })

  it('saves the connections, with the security token', async () => {
    const put = vi.spyOn(client, 'apiPut').mockResolvedValue({ key: 'crowdsec' })
    const lapi: ConnectionSettings = {
      url: 'http://192.168.1.2:8080',
      tls_mode: 'system',
      tls_ca_pem: null,
      tls_fingerprint: null,
      options: {},
      disabled_modules: [],
      secrets: { api_key: 'a-key' },
    }
    await expect(saveIntegration('crowdsec', { lapi }, TOKEN)).resolves.toEqual({
      key: 'crowdsec',
    })
    expect(put).toHaveBeenCalledWith('/integrations/crowdsec', { connections: { lapi } }, TOKEN)
  })

  it('disconnects, with the security token', async () => {
    const remove = vi.spyOn(client, 'apiDelete').mockResolvedValue(undefined)
    await expect(disconnectIntegration('wazuh', TOKEN)).resolves.toBeUndefined()
    expect(remove).toHaveBeenCalledWith('/integrations/wazuh', TOKEN)
  })

  it('tests, with the security token and nothing to send', async () => {
    const post = vi.spyOn(client, 'apiPost').mockResolvedValue({ ok: true })
    await expect(testIntegration('wazuh', TOKEN)).resolves.toEqual({ ok: true })
    expect(post).toHaveBeenCalledWith('/integrations/wazuh/test', undefined, TOKEN)
  })

  it('looks up the certificate at an address', async () => {
    const post = vi.spyOn(client, 'apiPost').mockResolvedValue({ fingerprint: 'AA:BB' })
    await expect(lookUpCertificate('opnsense', 'https://192.168.1.1', TOKEN)).resolves.toEqual({
      fingerprint: 'AA:BB',
    })
    expect(post).toHaveBeenCalledWith(
      '/integrations/opnsense/certificate',
      { url: 'https://192.168.1.1' },
      TOKEN,
    )
  })

  describe('the API log', () => {
    it('asks for the newest calls when not told anything else', async () => {
      const get = vi.spyOn(client, 'apiGet').mockResolvedValue({ calls: [], next_before: null })
      await expect(fetchCalls('opnsense')).resolves.toEqual({ calls: [], next_before: null })
      expect(get).toHaveBeenCalledWith('/integrations/opnsense/calls')
    })

    it('narrows it to what was asked, leaving out what was not', async () => {
      const get = vi.spyOn(client, 'apiGet').mockResolvedValue({ calls: [], next_before: null })
      await fetchCalls('opnsense', {
        connection: 'api',
        method: 'GET',
        failed: false,
        since: '2026-03-04T00:00:00.000Z',
        before: 12,
        limit: 25,
      })
      const requested = new URL(`http://x${String(get.mock.calls[0]?.[0])}`)
      expect(requested.pathname).toBe('/integrations/opnsense/calls')
      expect(Object.fromEntries(requested.searchParams)).toEqual({
        connection: 'api',
        method: 'GET',
        failed: 'false',
        since: '2026-03-04T00:00:00.000Z',
        before: '12',
        limit: '25',
      })
      await fetchCalls('opnsense', { connection: undefined, failed: true })
      expect(get).toHaveBeenLastCalledWith('/integrations/opnsense/calls?failed=true')
    })
  })
})
