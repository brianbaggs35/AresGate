import * as client from '@/api/client'
import { takeCapture } from '@/api/captures'

describe('captures', () => {
  it('asks for the host and the seconds with the sign-in token', async () => {
    const post = vi.spyOn(client, 'apiPost').mockResolvedValue({ total: 3 })

    await expect(takeCapture('192.168.1.20', 10, 'a-token')).resolves.toEqual({ total: 3 })
    expect(post).toHaveBeenCalledWith('/captures', { host: '192.168.1.20', seconds: 10 }, 'a-token')
  })
})
