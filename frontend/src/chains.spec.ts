import { certainty, deviceTitle, LINK, ROLE } from '@/chains'

describe('chains', () => {
  it('names a device by what it is called and its address, or by the address alone', () => {
    expect(deviceTitle({ device: '192.168.1.20', device_name: 'Kitchen camera' })).toBe(
      'Kitchen camera (192.168.1.20)',
    )
    expect(deviceTitle({ device: '192.168.1.20', device_name: null })).toBe('192.168.1.20')
  })

  it('says how sure a chain is, in a sentence', () => {
    expect(certainty({ confirmed: true })).toContain('doing what a taken-over device does')
    expect(certainty({ confirmed: false })).toContain('a guess')
  })

  it('gives a seen link and an inferred one each a word and a meaning', () => {
    expect(LINK.confirmed.label).toBe('Seen')
    expect(LINK.inferred.label).toBe('Inferred')
    expect(LINK.inferred.meaning).toContain('coincidence')
  })

  it('says what each step did', () => {
    expect(ROLE.attacker.title).toBe('Got in from the internet')
    expect(ROLE.callout.title).toBe('Then the device called out')
  })
})
