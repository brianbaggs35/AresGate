import { looking, pageOf, startersFor } from '@/pageContext'

const at = (
  name: string | symbol | undefined,
  params: Record<string, string> = {},
  query: Record<string, string> = {},
  meta: Record<string, unknown> = {},
) => pageOf({ name, params, query, meta })

describe('pageOf', () => {
  it('is the incident on screen', () => {
    expect(at('incident', { id: '12' })).toEqual({ kind: 'incident', id: 12 })
  })

  it('is nothing for an incident whose number is not one', () => {
    expect(at('incident', { id: 'abc' })).toBeNull()
    expect(at('incident', { id: '0' })).toBeNull()
  })

  it('is the device an asset page is about', () => {
    expect(at('asset', { key: 'device-7' })).toEqual({ kind: 'device', id: 7 })
  })

  it('is only the assets for one that is not a device', () => {
    expect(at('asset', { key: 'unknown' })).toEqual({ kind: 'other', title: 'Assets' })
  })

  it('is the device by its address', () => {
    expect(at('device', { address: ' 192.168.1.9 ' })).toEqual({
      kind: 'device',
      address: '192.168.1.9',
    })
    expect(at('device', { address: ' ' })).toEqual({ kind: 'other', title: 'Devices' })
  })

  it('is the search on the logs and the incidents', () => {
    expect(at('logs', {}, { q: 'ssh' })).toEqual({ kind: 'logs', query: 'ssh' })
    expect(at('logs')).toEqual({ kind: 'logs' })
    expect(at('incidents', {}, { q: 'scan'.repeat(100) })).toEqual({
      kind: 'incidents',
      query: 'scan'.repeat(100).slice(0, 200),
    })
    expect(at('incidents', {}, { q: 5 as unknown as string })).toEqual({ kind: 'incidents' })
  })

  it('is nothing on the assistant, which is the conversation itself', () => {
    expect(at('assistant')).toBeNull()
    expect(at('assistant-chat', { id: '3' })).toBeNull()
  })

  it("is the page's title for any other, and nothing for one without", () => {
    expect(at('dashboard', {}, {}, { title: 'Dashboard' })).toEqual({
      kind: 'other',
      title: 'Dashboard',
    })
    expect(at('dashboard')).toBeNull()
    expect(at(undefined, {}, {}, { title: 'Somewhere' })).toEqual({
      kind: 'other',
      title: 'Somewhere',
    })
  })
})

describe('looking', () => {
  it('says what the panel is looking at', () => {
    expect(looking({ kind: 'incident', id: 4 })).toBe('Looking at incident 4')
    expect(looking({ kind: 'incident' })).toBe('Looking at incident 0')
    expect(looking({ kind: 'device', id: 2 })).toBe('Looking at device 2')
    expect(looking({ kind: 'device', address: '10.0.0.1' })).toBe('Looking at this device')
    expect(looking({ kind: 'logs', query: 'ssh' })).toBe('Looking at the logs: ssh')
    expect(looking({ kind: 'logs' })).toBe('Looking at the logs')
    expect(looking({ kind: 'incidents', query: 'x' })).toBe('Looking at the incidents: x')
    expect(looking({ kind: 'incidents' })).toBe('Looking at the incidents')
    expect(looking({ kind: 'other', title: 'Settings' })).toBe('On the Settings page')
  })

  it('says nothing where there is nothing to say', () => {
    expect(looking(null)).toBeNull()
    expect(looking({ kind: 'other' })).toBeNull()
  })
})

describe('startersFor', () => {
  it('starts with a question about the page, then the general ones', () => {
    const starters = startersFor({ kind: 'incident', id: 1 })
    expect(starters[0]).toContain('this incident')
    expect(starters.length).toBeGreaterThan(2)
  })

  it('is the general ones alone where there is nothing about the page', () => {
    expect(startersFor(null).length).toBeGreaterThan(0)
    expect(startersFor({ kind: 'other', title: 'X' })).toEqual(startersFor(null))
    expect(startersFor({ kind: 'incidents' }).length).toBeGreaterThan(1)
  })
})
