import * as client from '@/api/client'
import { fetchIncident, fetchIncidents, setIncidentStatus } from '@/api/incidents'

describe('incidents', () => {
  it('lists them all when asked for nothing in particular', async () => {
    const get = vi.spyOn(client, 'apiGet').mockResolvedValue({ total: 0, items: [], counts: {} })

    await fetchIncidents()

    expect(get).toHaveBeenCalledWith('/incidents')
  })

  it('narrows the list by what is asked for', async () => {
    const get = vi.spyOn(client, 'apiGet').mockResolvedValue({ total: 0, items: [], counts: {} })

    await fetchIncidents({
      statuses: ['open', 'investigating'],
      minSeverity: 'high',
      minConfidence: 65,
      address: '93.184.216.34',
      limit: 25,
      offset: 50,
    })

    expect(get).toHaveBeenCalledWith(
      '/incidents?status=open&status=investigating&min_severity=high&min_confidence=65' +
        '&address=93.184.216.34&limit=25&offset=50',
    )
  })

  it('narrows the list by what the owner said of the incidents', async () => {
    const get = vi.spyOn(client, 'apiGet').mockResolvedValue({ total: 0, items: [], counts: {} })

    await fetchIncidents({ verdicts: ['none', 'threat'] })

    expect(get).toHaveBeenCalledWith('/incidents?verdict=none&verdict=threat')
  })

  it('can ask for the most serious first', async () => {
    const get = vi.spyOn(client, 'apiGet').mockResolvedValue({ total: 0, items: [], counts: {} })

    await fetchIncidents({ order: 'priority', limit: 3 })

    expect(get).toHaveBeenCalledWith('/incidents?limit=3&order=priority')
  })

  it('leaves out what means everything', async () => {
    const get = vi.spyOn(client, 'apiGet').mockResolvedValue({ total: 0, items: [], counts: {} })

    await fetchIncidents({ statuses: [], minConfidence: 0, offset: 0, limit: 10 })

    expect(get).toHaveBeenCalledWith('/incidents?limit=10')
  })

  it('reads one incident', async () => {
    const get = vi.spyOn(client, 'apiGet').mockResolvedValue({ id: 7 })

    await expect(fetchIncident(7)).resolves.toEqual({ id: 7 })
    expect(get).toHaveBeenCalledWith('/incidents/7')
  })

  it('says what is being done about one, with the sign-in token', async () => {
    const patch = vi.spyOn(client, 'apiPatch').mockResolvedValue({ id: 7, status: 'resolved' })

    await expect(setIncidentStatus(7, 'resolved', 'a-token')).resolves.toEqual({
      id: 7,
      status: 'resolved',
    })
    expect(patch).toHaveBeenCalledWith('/incidents/7', { status: 'resolved' }, 'a-token')
  })
})
