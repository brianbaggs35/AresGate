import { describePort, serviceOf } from '@/ports'

describe('ports', () => {
  it('names the service of a well-known port, and nothing for another', () => {
    expect(serviceOf(443)).toBe('HTTPS')
    expect(serviceOf(40123)).toBeNull()
  })

  it('shows a port with its transport and its service', () => {
    expect(describePort(443, 'tcp')).toBe('443/tcp HTTPS')
    expect(describePort(53, null)).toBe('53 DNS')
    expect(describePort(40123, 'udp')).toBe('40123/udp')
    expect(describePort(40123, null)).toBe('40123')
  })
})
