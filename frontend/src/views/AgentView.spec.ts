import * as agentsApi from '@/api/agents'
import type { AgentDetail, RunDetail } from '@/api/agents'
import { ApiError } from '@/api/client'
import AgentDialog from '@/components/AgentDialog.vue'
import AgentGraph from '@/components/AgentGraph.vue'
import AgentUsage from '@/components/AgentUsage.vue'
import {
  SCANNER,
  agent,
  check,
  detail,
  finding,
  run,
  runDetail,
  proposal,
  step,
  suggestions,
  template,
  usage,
} from '@/test/agents'
import { flushPromises, mountWithPlugins } from '@/test/mount'
import AgentView from '@/views/AgentView.vue'

const TOKEN = 'a-security-token'

interface Setup {
  agent?: AgentDetail | Error
  runs?: Record<number, RunDetail>
}

async function open({ agent: shown = detail(), runs = { 7: runDetail() } }: Setup = {}) {
  const get = vi.spyOn(agentsApi, 'fetchAgent')
  if (shown instanceof Error) get.mockRejectedValue(shown)
  else get.mockResolvedValue(shown)
  const read = vi.spyOn(agentsApi, 'fetchRun').mockImplementation((_id, number) => {
    const found = runs[number]
    return found ? Promise.resolve(found) : Promise.reject(new ApiError(404, 'No such run.', 'x'))
  })
  const start = vi.spyOn(agentsApi, 'startRun').mockResolvedValue(run())
  const stop = vi.spyOn(agentsApi, 'cancelRun').mockResolvedValue(run())
  const mounted = await mountWithPlugins(AgentView, {
    signedIn: 'admin',
    withApp: true,
    route: '/agents/3',
  })
  await flushPromises()
  const find = (selector: string) => mounted.wrapper.find(`[data-test="${selector}"]`)
  const click = async (selector: string) => {
    await find(selector).trigger('click')
    await flushPromises()
    await flushPromises()
  }
  return { ...mounted, get, read, start, stop, find, click }
}

const GOING = runDetail({
  id: 8,
  status: 'running',
  node: 'act',
  started_at: new Date(Date.now() - 5000).toISOString(),
  finished_at: null,
  summary: '',
  steps: [step({ node: 'plan' })],
})
const GOING_AGENT = detail({
  state: 'running',
  runs: [run({ id: 8, status: 'running', node: 'act', finished_at: null }), run()],
})

/** Runs the body with the page's timers in the test's hands, which has to be set up before the
 * page is opened, because that is when it asks for them. */
async function ticking(body: (tick: (ms: number) => Promise<void>) => Promise<void>) {
  vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval'] })
  try {
    await body(async (ms) => {
      vi.advanceTimersByTime(ms)
      await flushPromises()
    })
  } finally {
    vi.useRealTimers()
  }
}

describe('AgentView', () => {
  it('shows placeholders while it loads', async () => {
    vi.spyOn(agentsApi, 'fetchAgent').mockReturnValue(new Promise(() => {}))
    const { wrapper } = await mountWithPlugins(AgentView, {
      signedIn: 'admin',
      withApp: true,
      route: '/agents/3',
    })

    expect(wrapper.find('[data-test="agent-loading"]').exists()).toBe(true)
  })

  it('says why it could not load, and tries again', async () => {
    const { find, click, get } = await open({
      agent: new ApiError(404, 'There is no such agent.', 'x'),
    })

    expect(find('agent-error').text()).toContain('no such agent')
    get.mockResolvedValue(detail())

    await click('agent-retry')

    expect(find('agent-error').exists()).toBe(false)
    expect(find('agent-run').exists()).toBe(true)
  })

  it('names the agent and what it is doing, with the way back', async () => {
    const { wrapper, find } = await open()

    expect(wrapper.find('[data-test="page-heading"]').text()).toBe('Night watch')
    expect(find('agent-state').text()).toBe('Ready')
    expect(wrapper.find('[data-test="back"]').attributes('href')).toBe('/agents')
  })

  it('shows the last run: its graph, what it said and what it did', async () => {
    const { wrapper, find } = await open()

    expect(find('run-status').text()).toBe('Finished')
    expect(find('run-meta').text()).toContain('Started by you')
    expect(find('run-summary').text()).toBe('All quiet.')
    expect(wrapper.findComponent(AgentGraph).props('steps')).toHaveLength(4)
    expect(wrapper.findAll('[data-test="timeline-step"]')).toHaveLength(4)
    expect(find('run-nothing').text()).toBe('Nothing needed your attention.')
  })

  it('says what a run used of the AI and who answered, once it is over', async () => {
    const { find } = await open()

    expect(find('run-usage').text().replace(/\s+/g, ' ')).toBe(
      '1 request · 1,200 tokens · $0.0006 · claude-haiku-5-5',
    )
  })

  it('says it used no AI when none was asked, and not who answered', async () => {
    const { find } = await open({
      runs: { 7: runDetail({ usage: usage({ calls: 0 }), model: null, provider: null }) },
    })

    expect(find('run-usage').text()).toBe('Used no AI')
  })

  it('has no usage line while a run is still going', async () => {
    const { find } = await open({ agent: GOING_AGENT, runs: { 8: GOING } })

    expect(find('run-usage').exists()).toBe(false)
  })

  it('shows what the agent costs over 30 days', async () => {
    const { wrapper, find } = await open()

    expect(wrapper.findComponent(AgentUsage).props('usage')).toEqual(usage())
    expect(wrapper.findComponent(AgentUsage).props('days')).toHaveLength(30)
    expect(find('agent-usage').exists()).toBe(true)
  })

  it('shows what a run found, and the AI it did without', async () => {
    const { wrapper, find } = await open({
      runs: {
        7: runDetail({ findings_list: [finding()], findings: 1, ai: 'No AI provider is set up.' }),
      },
    })

    expect(wrapper.findAll('[data-test="finding"]')).toHaveLength(1)
    expect(find('run-nothing').exists()).toBe(false)
    expect(find('run-ai').text()).toContain('No AI provider is set up.')
  })

  it('says why a run failed', async () => {
    const { find } = await open({
      agent: detail({ runs: [run({ status: 'failed' })] }),
      runs: { 7: runDetail({ status: 'failed', error: 'It broke.', summary: '' }) },
    })

    expect(find('run-error').text()).toBe('It broke.')
    expect(find('run-status').text()).toBe('Failed')
    expect(find('run-nothing').exists()).toBe(false)
  })

  it('says it has not run yet, and offers to start it', async () => {
    const { find, wrapper } = await open({
      agent: detail({ runs: [], last_run: null, recent: [] }),
    })

    expect(find('agent-no-runs').exists()).toBe(true)
    expect(find('agent-run').exists()).toBe(false)
    expect(wrapper.find('[data-test="agent-tile-last"]').text()).toContain('Never')
    expect(find('agent-history').exists()).toBe(false)
    expect(find('agent-start').attributes('disabled')).toBeUndefined()
  })

  it('shows how it is going in four tiles', async () => {
    const { find } = await open({
      agent: detail({
        runs: [
          run({ id: 9, findings: 2, worst: 'high' }),
          run({ id: 8, status: 'failed' }),
          run({ id: 7 }),
        ],
      }),
      runs: { 9: runDetail({ id: 9 }) },
    })

    expect(find('agent-tile-last').text()).toContain('Finished')
    expect(find('agent-tile-next').text()).toContain('Every hour')
    expect(find('agent-tile-findings').text()).toContain('2')
    expect(find('agent-tile-reliable').text()).toContain('2 of 3')
  })

  it('shows tiles that are not scheduled or have nothing yet', async () => {
    const { find } = await open({
      agent: detail({
        interval_minutes: null,
        next_run_at: null,
        runs: [run({ status: 'cancelled' })],
      }),
    })

    expect(find('agent-tile-next').text()).toContain('Not scheduled')
    expect(find('agent-tile-reliable').text()).toContain('–')
  })

  it('is not scheduled while it is paused', async () => {
    const { find } = await open({
      agent: detail({ enabled: false, state: 'paused', next_run_at: '2026-11-10T13:00:00Z' }),
    })

    expect(find('agent-tile-next').text()).toContain('Not scheduled')
    expect(find('setup-schedule').text()).toBe('Paused (every hour)')
  })

  it.each([
    ['nothing was found', 0, null, 'text-success'],
    ['something worth a look was found', 1, 'medium', 'text-warning'],
    ['something serious was found', 1, 'critical', 'text-error'],
  ])('colors the findings tile when %s', async (_says, findings, worst, color) => {
    const { find } = await open({ agent: detail({ runs: [run({ findings, worst })] }) })

    expect(find('agent-tile-findings').find('.v-icon').classes()).toContain(color)
  })

  describe('while a run goes', () => {
    it('follows it: lit step, steps so far, how long and a way to stop it', async () => {
      const { wrapper, find } = await open({
        agent: GOING_AGENT,
        runs: { 8: GOING, 7: runDetail() },
      })

      expect(find('agent-state').text()).toBe('Running now')
      expect(find('run-status').text()).toBe('Running')
      expect(find('run-meta').text()).toMatch(/Started by you · .* · \d+(\.\d+)? s/)
      expect(wrapper.findAll('[data-test="graph-node"]')[1]!.attributes('data-state')).toBe(
        'active',
      )
      expect(find('timeline-working').exists()).toBe(true)
      expect(find('agent-stop').exists()).toBe(true)
      expect(find('agent-start').exists()).toBe(false)
    })

    it('stops the run when asked', async () => {
      const { find, click, stop } = await open({
        agent: GOING_AGENT,
        runs: { 8: GOING, 7: runDetail() },
      })

      await click('agent-stop')

      expect(stop).toHaveBeenCalledWith(3, 8, TOKEN)
      expect(find('agent-problem').exists()).toBe(false)
    })

    it('looks again every couple of seconds and shows what the run has done since', async () => {
      vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval'] })
      try {
        const { wrapper, read } = await open({
          agent: GOING_AGENT,
          runs: { 8: GOING, 7: runDetail() },
        })
        expect(wrapper.findAll('[data-test="timeline-step"]')).toHaveLength(1)
        read.mockResolvedValue({
          ...GOING,
          steps: [step({ node: 'plan' }), step({ seq: 2, node: 'act' })],
        })

        vi.advanceTimersByTime(2000)
        await flushPromises()

        expect(wrapper.findAll('[data-test="timeline-step"]')).toHaveLength(2)
      } finally {
        vi.useRealTimers()
      }
    })

    it('says a run is waiting to start', async () => {
      const { find } = await open({
        agent: detail({
          state: 'queued',
          runs: [run({ id: 8, status: 'queued', started_at: null, finished_at: null })],
        }),
        runs: {
          8: runDetail({
            id: 8,
            status: 'queued',
            started_at: null,
            finished_at: null,
            steps: [],
            summary: '',
          }),
        },
      })

      expect(find('run-status').text()).toBe('Waiting to start')
      expect(find('run-meta').text()).not.toMatch(/ s$/)
      expect(find('timeline-working').exists()).toBe(true)
    })
  })

  describe('asking for a run', () => {
    it('starts one and follows it', async () => {
      const { find, click, start, get } = await open()

      await click('agent-start')

      expect(start).toHaveBeenCalledWith(3, TOKEN)
      expect(get).toHaveBeenCalledTimes(2)
      expect(find('agent-problem').exists()).toBe(false)
    })

    it('says why it was refused, in the words it was given', async () => {
      const { find, click, start } = await open()
      start.mockRejectedValue(
        new ApiError(409, 'This agent already has a run waiting or going.', 'x'),
      )

      await click('agent-start')

      expect(find('agent-problem').text()).toContain('already has a run')
    })

    it('cannot start an agent that tests the network until it is allowed', async () => {
      const { find } = await open({
        agent: detail({
          template: 'exposure_scanner',
          template_info: SCANNER,
          active: true,
          allow_active: false,
          interval_minutes: null,
        }),
      })

      expect(find('agent-blocked').text()).toContain('not allowed to yet')
      expect(find('agent-start').attributes('disabled')).toBeDefined()
      expect(find('setup-allow').text()).toBe('Not allowed yet')
    })

    it('says it is allowed once it is', async () => {
      const { find } = await open({
        agent: detail({
          template_info: SCANNER,
          active: true,
          allow_active: true,
          interval_minutes: null,
        }),
      })

      expect(find('agent-blocked').exists()).toBe(false)
      expect(find('setup-allow').text()).toBe('Allowed')
      expect(find('setup-schedule').text()).toBe('Only when you start it')
    })
  })

  describe('earlier runs', () => {
    const second = detail({
      runs: [
        run({ id: 9, findings: 1, worst: 'low' }),
        run({ id: 7, status: 'failed', error: 'It broke.' }),
      ],
    })
    const runs = {
      9: runDetail({ id: 9, findings_list: [finding({ title: 'Newest finding' })], findings: 1 }),
      7: runDetail({ id: 7, status: 'failed', error: 'It broke.', findings_list: [] }),
    }

    it('lists them, newest first, with what each came to', async () => {
      const { wrapper } = await open({ agent: second, runs })

      const rows = wrapper.findAll('[data-test="history-run"]')
      expect(rows.map((row) => row.text())).toEqual([
        expect.stringContaining('Run 9 · 1 finding'),
        expect.stringContaining('Run 7 · It broke.'),
      ])
      expect(rows[0]!.attributes('aria-pressed')).toBe('true')
    })

    it('shows the one that is picked, and stays on it as newer ones arrive', async () => {
      await ticking(async (tick) => {
        const { wrapper, find, get, read } = await open({ agent: second, runs })

        await wrapper.findAll('[data-test="history-run"]')[1]!.trigger('click')
        await flushPromises()
        expect(find('run-error').text()).toBe('It broke.')
        expect(wrapper.findAll('[data-test="history-run"]')[1]!.attributes('aria-pressed')).toBe(
          'true',
        )

        get.mockResolvedValue(detail({ runs: [run({ id: 10 }), ...second.runs] }))
        await tick(2000)

        expect(read).toHaveBeenLastCalledWith(3, 7)
        expect(find('run-error').text()).toBe('It broke.')
        expect(wrapper.findAll('[data-test="history-run"]')).toHaveLength(3)
      })
    })

    it('goes back to following the newest when it is picked again', async () => {
      await ticking(async (tick) => {
        const { wrapper, get, read } = await open({ agent: second, runs })
        await wrapper.findAll('[data-test="history-run"]')[1]!.trigger('click')
        await flushPromises()

        await wrapper.findAll('[data-test="history-run"]')[0]!.trigger('click')
        await flushPromises()
        get.mockResolvedValue(detail({ runs: [run({ id: 11 }), ...second.runs] }))
        read.mockResolvedValue(runDetail({ id: 11 }))
        await tick(2000)

        expect(wrapper.find('.run__title').text()).toBe('Run 11')
      })
    })

    it('says why a run could not be read, and keeps what was on screen', async () => {
      const { wrapper, find } = await open({ agent: second, runs: { 9: runs[9] } })

      await wrapper.findAll('[data-test="history-run"]')[1]!.trigger('click')
      await flushPromises()

      expect(find('agent-problem').text()).toContain('No such run.')
    })

    it('stays quiet about a run that a refresh could not read', async () => {
      await ticking(async (tick) => {
        const { find, read } = await open({ agent: second, runs })
        read.mockRejectedValue(new ApiError(0, 'Gone.', 'offline'))

        await tick(2000)

        expect(find('agent-problem').exists()).toBe(false)
        expect(find('run-meta').exists()).toBe(true)
      })
    })

    it('ignores the answer for a run that is no longer the one on screen', async () => {
      const { wrapper, find, read } = await open({ agent: second, runs })
      let late: (value: RunDetail) => void = () => {}
      read.mockReturnValueOnce(new Promise<RunDetail>((resolve) => (late = resolve)))

      const picking = wrapper.findAll('[data-test="history-run"]')[1]!.trigger('click')
      await flushPromises()
      read.mockResolvedValue(runs[9])
      await wrapper.findAll('[data-test="history-run"]')[0]!.trigger('click')
      await flushPromises()
      late(runs[7])
      await picking
      await flushPromises()

      expect(find('run-error').exists()).toBe(false)
    })
  })

  it('says how it is set up, and what the owner asked of it', async () => {
    const { find } = await open()

    expect(find('setup-kind').text()).toBe('Threat hunter')
    expect(find('setup-schedule').text()).toBe('Every hour')
    expect(find('setup-goal').text()).toBe('Watch the cameras.')
    expect(find('setup-allow').exists()).toBe(false)
  })

  it('says whether what its kind needs is there', async () => {
    const { find } = await open({
      agent: detail({
        template_info: template({
          ready: false,
          checks: [check({ ok: false, fix: 'Add a free VirusTotal key.' })],
        }),
      }),
    })

    expect(find('setup-title').text()).toBe('It needs a little setup first')
    expect(find('setup-check').text()).toContain('Add a free VirusTotal key.')
  })

  it('shows what a cleanup agent suggests, and only for one that does', async () => {
    const plain = await open()
    expect(plain.find('agent-suggestions').exists()).toBe(false)

    const { find } = await open({
      agent: detail({
        template_info: template({ proposes: true }),
        suggestions: suggestions({ pending: [proposal()] }),
      }),
    })

    expect(find('agent-suggestions').text()).toContain('3 open incidents say the same thing')
  })

  it('says there are no instructions when there are none', async () => {
    const { find } = await open({ agent: detail({ goal: '' }) })

    expect(find('setup-goal').text()).toBe('None. It does what its kind does.')
  })

  describe('changing it', () => {
    it('opens the sheet to edit it, and says so when it is saved', async () => {
      const { wrapper, click, get } = await open()
      vi.spyOn(agentsApi, 'changeAgent').mockResolvedValue(agent())

      await click('agent-edit')
      expect(wrapper.findComponent(AgentDialog).props('agent')).toMatchObject({ id: 3 })
      document.body
        .querySelector<HTMLElement>('.v-overlay--active [data-test="dialog-save"]')!
        .click()
      await flushPromises()
      await flushPromises()

      expect(get).toHaveBeenCalledTimes(2)
      expect(document.body.querySelector('[data-test="undo-notice-text"]')!.textContent).toContain(
        'saved.',
      )
    })

    it('goes back to the agents once it is removed', async () => {
      const { router, click } = await open()
      vi.spyOn(agentsApi, 'removeAgent').mockResolvedValue(undefined)

      await click('agent-edit')
      document.body
        .querySelector<HTMLElement>('.v-overlay--active [data-test="dialog-remove"]')!
        .click()
      await flushPromises()
      document.body
        .querySelector<HTMLElement>('.v-overlay--active [data-test="confirm-accept"]')!
        .click()
      await flushPromises()
      await flushPromises()

      await vi.waitFor(() => {
        expect(router.currentRoute.value.name).toBe('agents')
      })
    })
  })

  it('keeps what is on screen when a refresh fails', async () => {
    await ticking(async (tick) => {
      const { find, get } = await open()
      get.mockRejectedValue(new ApiError(0, 'Gone.', 'offline'))

      await tick(2000)

      expect(find('agent-error').exists()).toBe(false)
      expect(find('agent-run').exists()).toBe(true)
    })
  })

  it('keeps saying why the first look failed when a refresh fails too', async () => {
    vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval'] })
    try {
      vi.spyOn(agentsApi, 'fetchAgent').mockRejectedValue(new ApiError(0, 'Gone.', 'offline'))
      const { wrapper } = await mountWithPlugins(AgentView, {
        signedIn: 'admin',
        withApp: true,
        route: '/agents/3',
      })
      await flushPromises()
      vi.advanceTimersByTime(2000)
      await flushPromises()

      expect(wrapper.find('[data-test="agent-error"]').text()).toContain('Gone.')
    } finally {
      vi.useRealTimers()
    }
  })
})
