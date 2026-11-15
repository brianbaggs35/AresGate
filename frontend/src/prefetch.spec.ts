import * as collectorsApi from '@/api/collectors'
import * as dashboardApi from '@/api/dashboard'
import { ApiError } from '@/api/client'
import { KEEP_MS, prefetchDashboard, takePrefetched } from '@/prefetch'

const dashboard = { window: { key: '24h' } } as unknown as dashboardApi.Dashboard
const report = { collectors: [] } as unknown as collectorsApi.CollectorsReport

describe('fetching the dashboard ahead', () => {
  beforeEach(() => {
    vi.spyOn(dashboardApi, 'fetchDashboard').mockResolvedValue(dashboard)
    vi.spyOn(collectorsApi, 'fetchCollectors').mockResolvedValue(report)
    // Whatever an earlier test left unclaimed.
    takePrefetched('24h')
  })

  it('asks for the 24 hours and the collectors, and hands them to the page once', async () => {
    prefetchDashboard()
    expect(dashboardApi.fetchDashboard).toHaveBeenCalledExactlyOnceWith('24h')
    expect(collectorsApi.fetchCollectors).toHaveBeenCalledOnce()

    const early = takePrefetched('24h')
    expect(await early?.dashboard).toBe(dashboard)
    expect(await early?.collectors).toBe(report)
    expect(takePrefetched('24h')).toBeNull()
  })

  it('has nothing for a window that was not asked for', () => {
    prefetchDashboard()
    expect(takePrefetched('7d')).toBeNull()
    // Asking for another window uses it up: the page asks for itself from then on.
    expect(takePrefetched('24h')).toBeNull()
  })

  it('has nothing to give when nothing was asked for', () => {
    expect(takePrefetched('24h')).toBeNull()
  })

  it('has nothing to give once it has waited too long', () => {
    prefetchDashboard(1000)
    expect(takePrefetched('24h', 1000 + KEEP_MS + 1)).toBeNull()
  })

  it('gives what it has up to the moment it is too old', () => {
    prefetchDashboard(1000)
    expect(takePrefetched('24h', 1000 + KEEP_MS)).not.toBeNull()
  })

  it('lets the page see a failure, and reports none if the page never asks', async () => {
    const failure = new ApiError(401, "You're not signed in.", 'unauthenticated')
    vi.spyOn(dashboardApi, 'fetchDashboard').mockRejectedValue(failure)
    const unhandled = vi.fn()
    process.on('unhandledRejection', unhandled)

    prefetchDashboard()
    await new Promise((resolve) => setTimeout(resolve, 0))
    expect(unhandled).not.toHaveBeenCalled()

    prefetchDashboard()
    await expect(takePrefetched('24h')?.dashboard).rejects.toBe(failure)
    process.off('unhandledRejection', unhandled)
  })
})
