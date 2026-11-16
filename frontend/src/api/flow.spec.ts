import * as client from '@/api/client'
import { FLOW_DIRECTIONS, FLOW_HOURS, fetchFlow } from '@/api/flow'
import { flow } from '@/test/flow'

describe('flow API', () => {
  it('asks for the window and the direction', async () => {
    const answer = flow()
    const get = vi.spyOn(client, 'apiGet').mockResolvedValue(answer)

    await expect(fetchFlow(6, 'incoming')).resolves.toBe(answer)
    expect(get).toHaveBeenCalledWith('/flow?hours=6&direction=incoming')
  })

  it('has the choices the API has', () => {
    expect(FLOW_HOURS).toEqual([1, 6, 24, 168])
    expect(FLOW_DIRECTIONS).toEqual(['all', 'outgoing', 'incoming', 'inside'])
  })
})
