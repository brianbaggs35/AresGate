import { exportAddress } from '@/api/exports'
import * as search from '@/search'

describe('exportAddress', () => {
  it('points at the list’s own file with the filters it was asked with', () => {
    const address = exportAddress('incidents', 'csv', new URLSearchParams('status=open&q=ssh'))
    const [path, query] = address.split('?') as [string, string]
    const params = new URLSearchParams(query)

    expect(path).toBe('/api/incidents/export')
    expect(params.get('status')).toBe('open')
    expect(params.get('q')).toBe('ssh')
    expect(params.get('format')).toBe('csv')
  })

  it('asks for the times in this browser’s time zone', () => {
    const zone = Intl.DateTimeFormat().resolvedOptions().timeZone
    const params = new URLSearchParams(
      exportAddress('devices', 'json', new URLSearchParams()).split('?')[1],
    )

    expect(params.get('tz')).toBe(zone)
    expect(params.get('format')).toBe('json')
  })

  it('leaves out the page, since the file holds all of it', () => {
    const address = exportAddress(
      'assets',
      'csv',
      new URLSearchParams('limit=30&offset=60&before=9&new=true'),
    )

    expect(address).not.toMatch(/limit|offset|before/)
    expect(address).toContain('new=true')
  })

  it('has a file for each list', () => {
    const paths = (['incidents', 'alerts', 'devices', 'assets'] as const).map(
      (list) => exportAddress(list, 'csv', new URLSearchParams()).split('?')[0],
    )

    expect(paths).toEqual([
      '/api/incidents/export',
      '/api/alerts/deliveries/export',
      '/api/devices/export',
      '/api/assets/export',
    ])
  })

  it('leaves the time zone out when the browser does not say', () => {
    vi.spyOn(search, 'zone').mockReturnValue('')

    const address = exportAddress('devices', 'json', new URLSearchParams())

    expect(address).toBe('/api/devices/export?format=json')
  })
})
