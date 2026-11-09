import * as client from '@/api/client'
import { searchThreatIntel } from '@/api/threatIntel'

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
})
