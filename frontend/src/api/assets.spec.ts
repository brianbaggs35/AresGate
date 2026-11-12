import { classifyAsset, fetchAsset, fetchAssets, fetchKinds, unclassifyAsset } from '@/api/assets'
import * as client from '@/api/client'

describe('fetchAsset', () => {
  it('asks for the page of one asset by its key', async () => {
    const get = vi.spyOn(client, 'apiGet').mockResolvedValue({})

    await fetchAsset('device-12')

    expect(get).toHaveBeenCalledWith('/assets/device-12')
  })

  it('keeps the key to one path segment', async () => {
    const get = vi.spyOn(client, 'apiGet').mockResolvedValue({})

    await fetchAsset('a/b?c')

    expect(get).toHaveBeenCalledWith('/assets/a%2Fb%3Fc')
  })
})

describe('fetchAssets', () => {
  it('asks for everything when nothing is asked', async () => {
    const get = vi.spyOn(client, 'apiGet').mockResolvedValue({})

    await fetchAssets()

    expect(get).toHaveBeenCalledWith('/assets')
  })

  it('asks for what was chosen, and repeats a source for each', async () => {
    const get = vi.spyOn(client, 'apiGet').mockResolvedValue({})

    await fetchAssets({
      q: 'laptop',
      status: 'online',
      sources: ['opnsense', 'wazuh'],
      interface: 4,
      new: true,
      unidentified: true,
      kind: 'camera',
      sort: 'name',
      limit: 30,
      offset: 60,
    })

    const [path] = get.mock.calls[0] as [string]
    const params = new URLSearchParams(path.split('?')[1])
    expect(path.startsWith('/assets?')).toBe(true)
    expect(params.get('q')).toBe('laptop')
    expect(params.get('status')).toBe('online')
    expect(params.getAll('source')).toEqual(['opnsense', 'wazuh'])
    expect(params.get('interface')).toBe('4')
    expect(params.get('new')).toBe('true')
    expect(params.get('unidentified')).toBe('true')
    expect(params.get('kind')).toBe('camera')
    expect(params.get('sort')).toBe('name')
    expect(params.get('limit')).toBe('30')
    expect(params.get('offset')).toBe('60')
  })

  it('leaves out what is not narrowed', async () => {
    const get = vi.spyOn(client, 'apiGet').mockResolvedValue({})

    await fetchAssets({ q: '', new: false, unidentified: false, offset: 0, limit: 10 })

    expect(get).toHaveBeenCalledWith('/assets?limit=10')
  })
})

describe('fetchKinds', () => {
  it('asks for the kinds an owner can pick', async () => {
    const get = vi.spyOn(client, 'apiGet').mockResolvedValue([])

    await fetchKinds()

    expect(get).toHaveBeenCalledWith('/assets/kinds')
  })
})

describe('classifyAsset', () => {
  it('says what the asset is and what it is for, with the security token', async () => {
    const put = vi.spyOn(client, 'apiPut').mockResolvedValue({})

    await classifyAsset('device/1', 'camera', 'Watches the door', 'token')

    expect(put).toHaveBeenCalledWith(
      '/assets/device%2F1/profile',
      { kind: 'camera', purpose: 'Watches the door' },
      'token',
    )
  })
})

describe('unclassifyAsset', () => {
  it('takes back what was said', async () => {
    const del = vi.spyOn(client, 'apiDelete').mockResolvedValue(undefined)

    await unclassifyAsset('device-1', 'token')

    expect(del).toHaveBeenCalledWith('/assets/device-1/profile', 'token')
  })
})
