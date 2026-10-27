import * as client from '@/api/client'
import {
  changeIncidents,
  fetchIncident,
  fetchIncidents,
  setIncidentStatus,
  undoChange,
} from '@/api/incidents'

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

  it('asks for a search in words, with the time zone it is in', async () => {
    const get = vi.spyOn(client, 'apiGet').mockResolvedValue({ total: 0, items: [], counts: {} })

    await fetchIncidents({ q: 'severity>=high -port:22', tz: 'America/Halifax' })

    expect(get).toHaveBeenCalledWith(
      '/incidents?q=severity%3E%3Dhigh+-port%3A22&tz=America%2FHalifax',
    )
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

  describe('changing many at once', () => {
    const result = { preview: false, incidents: 2, signals: 5, changed: 2, undo: null }

    it('changes the ones that were picked in one request', async () => {
      const post = vi.spyOn(client, 'apiPost').mockResolvedValue(result)

      await expect(
        changeIncidents({ ids: [4, 7] }, { status: 'resolved' }, 'a-token'),
      ).resolves.toEqual(result)

      expect(post).toHaveBeenCalledWith(
        '/incidents/bulk',
        { ids: [4, 7], status: 'resolved' },
        'a-token',
      )
    })

    it('gives a verdict, with a note, and can only ask what it would do', async () => {
      const post = vi.spyOn(client, 'apiPost').mockResolvedValue(result)

      await changeIncidents(
        { ids: [4] },
        { verdict: 'threat', note: 'Seen it before' },
        'a-token',
        true,
      )

      expect(post).toHaveBeenCalledWith(
        '/incidents/bulk',
        { ids: [4], verdict: 'threat', note: 'Seen it before', preview: true },
        'a-token',
      )
    })

    it('changes all that a list would show, said as the list was asked', async () => {
      const post = vi.spyOn(client, 'apiPost').mockResolvedValue(result)

      await changeIncidents(
        {
          matching: {
            statuses: ['open'],
            verdicts: ['none', 'threat'],
            minSeverity: 'high',
            minConfidence: 65,
            address: '93.184.216.34',
            q: 'ssh',
            tz: 'America/Halifax',
            limit: 25,
          },
        },
        { status: 'dismissed' },
        'a-token',
      )

      expect(post).toHaveBeenCalledWith(
        '/incidents/bulk',
        {
          matching: {
            status: ['open'],
            verdict: ['none', 'threat'],
            min_severity: 'high',
            min_confidence: 65,
            address: '93.184.216.34',
            q: 'ssh',
            tz: 'America/Halifax',
          },
          status: 'dismissed',
        },
        'a-token',
      )
    })

    it('says only what a list was narrowed to', async () => {
      const post = vi.spyOn(client, 'apiPost').mockResolvedValue(result)

      await changeIncidents({ matching: {} }, { status: 'open' }, 'a-token')

      expect(post).toHaveBeenCalledWith(
        '/incidents/bulk',
        { matching: { status: [], verdict: [], min_confidence: 0 }, status: 'open' },
        'a-token',
      )
    })

    it('takes a change back as it said how', async () => {
      const post = vi.spyOn(client, 'apiPost').mockResolvedValue({ incidents: 2, verdicts: 0 })
      const undo = { statuses: { open: [4, 7] }, rules: [] }

      await expect(undoChange(undo, 'a-token')).resolves.toEqual({ incidents: 2, verdicts: 0 })

      expect(post).toHaveBeenCalledWith('/incidents/bulk/undo', undo, 'a-token')
    })
  })
})
