import * as client from '@/api/client'
import { fetchIncidentResponse, RANGE_DAYS } from '@/api/incidentResponse'

describe('incident response', () => {
  it.each([
    ['24h', 1],
    ['7d', 7],
    ['30d', 30],
  ] as const)('asks for %s as %i days', async (range, days) => {
    const answer = { days }
    const get = vi.spyOn(client, 'apiGet').mockResolvedValue(answer)

    await expect(fetchIncidentResponse(range)).resolves.toBe(answer)
    expect(get).toHaveBeenCalledWith(`/incident-response?days=${days}`)
    expect(RANGE_DAYS[range]).toBe(days)
  })
})
