import { ApiError } from '@/api/client'
import * as collectorsApi from '@/api/collectors'
import type { CollectorsReport } from '@/api/collectors'
import CollectionCard from '@/components/CollectionCard.vue'
import { collector, report } from '@/test/collectors'
import { flushPromises, mountWithPlugins } from '@/test/mount'

const ONE = [{ key: 'api', label: 'OPNsense API' }]
const TWO = [
  { key: 'manager', label: 'Manager API' },
  { key: 'indexer', label: 'Indexer API' },
]

async function open(
  first: CollectorsReport | Error = report(),
  { connections = ONE, refresh = 0 }: { connections?: typeof ONE; refresh?: number } = {},
) {
  const fetch = vi.spyOn(collectorsApi, 'fetchCollectors')
  if (first instanceof Error) fetch.mockRejectedValue(first)
  else fetch.mockResolvedValue(first)
  const mounted = await mountWithPlugins(CollectionCard, {
    signedIn: 'admin',
    props: { integration: 'opnsense', connections, refresh },
  })
  await flushPromises()
  const find = (selector: string) => mounted.wrapper.find(`[data-test="${selector}"]`)
  const texts = (selector: string) =>
    mounted.wrapper.findAll(`[data-test="${selector}"]`).map((item) => item.text())
  return { ...mounted, fetch, find, texts }
}

describe('CollectionCard', () => {
  it('asks for the collectors of the integration', async () => {
    const { fetch } = await open()
    expect(fetch).toHaveBeenCalledOnce()
    expect(fetch).toHaveBeenCalledWith('opnsense')
  })

  it('shows a placeholder while it asks', async () => {
    vi.spyOn(collectorsApi, 'fetchCollectors').mockReturnValue(new Promise(() => {}))
    const { wrapper } = await mountWithPlugins(CollectionCard, {
      signedIn: 'admin',
      props: { integration: 'opnsense', connections: ONE, refresh: 0 },
    })
    expect(wrapper.find('[data-test="collection-loading"]').exists()).toBe(true)
  })

  it('shows what each job is, how it is doing, and when it ran and runs next', async () => {
    const { find, texts } = await open()
    expect(find('collection').exists()).toBe(true)
    expect(texts('collector-title')).toEqual(['Connection check'])
    expect(texts('collector-state')).toEqual(['Working'])
    expect(texts('collector-summary')).toEqual(['Tests the connection every few minutes.'])
    expect(texts('collector-timing')).toEqual([
      'Last ran 2 minutes ago, took 1.8 s · next run in 3 minutes',
    ])
    expect(find('collector-error').exists()).toBe(false)
    expect(find('collection-worker').exists()).toBe(false)
  })

  it('says how many things a job collected, when it counts them', async () => {
    const { texts } = await open(report([collector({ last_items: 12 })]))
    expect(texts('collector-timing')).toEqual([
      'Last ran 2 minutes ago, took 1.8 s · collected 12 · next run in 3 minutes',
    ])
  })

  it('says when a job is due, even if it is a little behind', async () => {
    const overdue = new Date(Date.now() - 10_000).toISOString()
    const { texts } = await open(report([collector({ next_run_at: overdue })]))
    expect(texts('collector-timing')[0]).toMatch(/next run within a minute$/)
  })

  it('leaves out what a job does not know', async () => {
    const { texts } = await open(report([collector({ last_duration_ms: null, next_run_at: null })]))
    expect(texts('collector-timing')).toEqual(['Last ran 2 minutes ago'])
  })

  it('says why a job failed, and marks it', async () => {
    const { texts } = await open(
      report([
        collector({
          state: 'problem',
          last_error: 'CrowdSec didn’t accept the credentials.',
          consecutive_failures: 3,
        }),
      ]),
    )
    expect(texts('collector-state')).toEqual(['Problem'])
    expect(texts('collector-error')).toEqual(['CrowdSec didn’t accept the credentials.'])
  })

  it.each([
    ['waiting', 'Waiting'],
    ['ok', 'Working'],
    ['problem', 'Problem'],
    ['late', 'Late'],
  ] as const)('says a job in the state %s is "%s"', async (state, label) => {
    const { texts } = await open(report([collector({ state })]))
    expect(texts('collector-state')).toEqual([label])
  })

  it('says a job that has not run yet is due shortly', async () => {
    const { texts } = await open(
      report([collector({ state: 'waiting', last_finished_at: null, next_run_at: null })]),
    )
    expect(texts('collector-timing')).toEqual(["Hasn't run yet. The first run is due shortly."])
  })

  it('names the connection a job reads from when the integration has several', async () => {
    const { texts } = await open(
      report([
        collector({ connection: 'manager' }),
        collector({ connection: 'indexer' }),
        collector({ connection: 'gone' }),
      ]),
      { connections: TWO },
    )
    expect(texts('collector-title')).toEqual([
      'Connection check · Manager API',
      'Connection check · Indexer API',
      'Connection check · gone',
    ])
  })

  it('says so when nothing is collected yet', async () => {
    const { find, texts } = await open(report([]))
    expect(find('collection-empty').text()).toMatch(/Nothing is being collected/)
    expect(texts('collector')).toEqual([])
  })

  it.each([
    ['stopped', 'warning', /has stopped reporting in/],
    ['unknown', 'info', /hasn't reported in yet/],
    ['off', 'info', /turned off \(ARESGATE_COLLECTORS_ENABLED is false\)/],
  ] as const)('explains a worker that is %s', async (state, type, words) => {
    const { find } = await open(report([], { state }))
    const note = find('collection-worker')
    expect(note.text()).toMatch(words)
    expect(note.find('.v-alert').classes()).toContain(`text-${type}`)
  })

  it('reloads when something made the jobs run, and when asked to', async () => {
    const { fetch, find, wrapper } = await open()
    await wrapper.setProps({ refresh: 1 })
    await flushPromises()
    expect(fetch).toHaveBeenCalledTimes(2)
    await find('collection-refresh').trigger('click')
    await flushPromises()
    expect(fetch).toHaveBeenCalledTimes(3)
  })

  it('says so when it cannot be read, and tries again', async () => {
    const { fetch, find } = await open(new ApiError(0, "Can't reach AresGate.", 'offline'))
    expect(find('collection-error').text()).toContain("Can't reach AresGate.")
    expect(find('collector').exists()).toBe(false)
    fetch.mockResolvedValue(report())
    await find('collection-retry').trigger('click')
    await flushPromises()
    expect(find('collection-error').exists()).toBe(false)
    expect(find('collector').exists()).toBe(true)
  })
})
