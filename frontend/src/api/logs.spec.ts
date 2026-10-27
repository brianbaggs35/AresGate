import * as client from '@/api/client'
import { exportAddress, fetchLog, fetchLogs } from '@/api/logs'

describe('logs', () => {
  it('lists the newest when asked for nothing in particular', async () => {
    const get = vi.spyOn(client, 'apiGet').mockResolvedValue({ items: [] })

    await fetchLogs()

    expect(get).toHaveBeenCalledWith('/logs')
  })

  it('asks for a search in words, with the time zone it is in', async () => {
    const get = vi.spyOn(client, 'apiGet').mockResolvedValue({ items: [] })

    await fetchLogs({ q: 'severity>=high -port:22', tz: 'America/Halifax', limit: 100 })

    expect(get).toHaveBeenCalledWith(
      '/logs?q=severity%3E%3Dhigh+-port%3A22&tz=America%2FHalifax&limit=100',
    )
  })

  it('pages back from an event, or forward from one, and can leave the summary out', async () => {
    const get = vi.spyOn(client, 'apiGet').mockResolvedValue({ items: [] })

    await fetchLogs({ before: '1793000000000000.12', summary: false })
    await fetchLogs({ after: '1793000000000000.12', summary: true })

    expect(get).toHaveBeenNthCalledWith(1, '/logs?before=1793000000000000.12&summary=false')
    expect(get).toHaveBeenNthCalledWith(2, '/logs?after=1793000000000000.12')
  })

  it('reads one event whole by where it is in the order', async () => {
    const answer = { id: 4 }
    const get = vi.spyOn(client, 'apiGet').mockResolvedValue(answer)

    await expect(fetchLog('1793000000000000.12')).resolves.toBe(answer)
    expect(get).toHaveBeenCalledWith('/logs/1793000000000000.12')
  })

  it('gives the address of a file of what a search finds', () => {
    expect(exportAddress('csv')).toBe('/api/logs/export?format=csv')
    expect(exportAddress('json', { q: 'kind:alert', tz: 'Europe/Paris' })).toBe(
      '/api/logs/export?format=json&q=kind%3Aalert&tz=Europe%2FParis',
    )
  })
})
