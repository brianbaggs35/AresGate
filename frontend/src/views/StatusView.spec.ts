import { ApiError } from '@/api/client'
import * as statusApi from '@/api/status'
import { useSessionStore } from '@/stores/session'
import { flushPromises, mountWithPlugins } from '@/test/mount'
import StatusView from '@/views/StatusView.vue'

const GB = 1024 ** 3
const MINUTE = 60_000

/** An install that is doing well, with everything the report can hold. */
function healthy(): statusApi.StatusReport {
  return {
    aresgate: {
      version: '0.0.1',
      commit: '0123456789abcdef0123456789abcdef01234567',
      built_at: '2026-10-20T09:30:00Z',
      environment: 'production',
      started_at: '2026-10-22T08:00:00Z',
      uptime_seconds: 2 * 86400 + 5 * 3600 + 7 * 60,
    },
    stack: {
      python: '3.14.8',
      nginx: '1.29.2',
      database: {
        status: 'ok',
        version: '18.1',
        size_bytes: 12 * 1024 * 1024,
        connections: 4,
        max_connections: 100,
        migration: '0008',
        migration_head: '0008',
      },
      certificate: {
        subject: 'aresgate.home',
        issuer: 'AresGate local CA',
        names: ['aresgate.home', 'aresgate.local'],
        not_before: '2026-09-01T00:00:00Z',
        not_after: '2027-09-01T00:00:00Z',
        days_left: 312,
        self_signed: false,
      },
    },
    container: {
      cpus: 2,
      load: [0.5, 0.25, 0.1],
      memory: { used_bytes: 1 * GB, limit_bytes: 4 * GB, total_bytes: 16 * GB },
      disk: { used_bytes: 2 * GB, total_bytes: 10 * GB },
      server_time: new Date().toISOString(),
    },
    parts: [
      {
        key: 'opnsense',
        name: 'OPNsense',
        group: 'integration',
        state: 'ok',
        detail: null,
        last_success_at: new Date(Date.now() - 5 * MINUTE).toISOString(),
      },
      {
        key: 'wazuh',
        name: 'Wazuh',
        group: 'integration',
        state: 'off',
        detail: 'Not connected.',
        last_success_at: null,
      },
    ],
    diagnostics: 'AresGate diagnostics\nVersion: 0.0.1',
  }
}

/** The same install running from source, where much can't be told. */
function bare(): statusApi.StatusReport {
  const report = healthy()
  report.aresgate.commit = null
  report.aresgate.built_at = null
  report.stack.nginx = null
  report.stack.certificate = null
  report.stack.database = {
    ...report.stack.database,
    version: null,
    size_bytes: null,
    connections: null,
    max_connections: null,
    migration: null,
    migration_head: null,
  }
  report.container = {
    cpus: null,
    load: null,
    memory: { used_bytes: 3 * GB, limit_bytes: null, total_bytes: null },
    disk: null,
    server_time: report.container.server_time,
  }
  return report
}

async function open(report: statusApi.StatusReport | Error = healthy()) {
  const fetch = vi.spyOn(statusApi, 'fetchStatus')
  if (report instanceof Error) fetch.mockRejectedValue(report)
  else fetch.mockResolvedValue(report)
  const mounted = await mountWithPlugins(StatusView, { route: '/status', signedIn: 'admin' })
  await flushPromises()
  const find = (selector: string) => mounted.wrapper.find(`[data-test="${selector}"]`)
  const texts = (selector: string) =>
    mounted.wrapper.findAll(`[data-test="${selector}"]`).map((item) => item.text())
  /** What a card says, as label then value for each fact. */
  const facts = (card: string) =>
    Object.fromEntries(
      mounted.wrapper
        .findAll(`[data-test="${card}"] dl > div`)
        .map((row) => [row.find('dt').text(), row.find('dd').text()]),
    )
  return { ...mounted, fetch, find, texts, facts }
}

const offline = () => new ApiError(0, "Can't reach AresGate.", 'offline')

describe('StatusView', () => {
  describe('looking at it', () => {
    it('shows a placeholder while it asks', async () => {
      vi.spyOn(statusApi, 'fetchStatus').mockReturnValue(new Promise(() => {}))
      const { wrapper } = await mountWithPlugins(StatusView, { signedIn: 'admin' })
      expect(wrapper.find('[data-test="status-loading"]').exists()).toBe(true)
      expect(wrapper.find('[data-test="status-aresgate"]').exists()).toBe(false)
    })

    it('has a title and says everything checks out when it does', async () => {
      const { find } = await open()
      expect(find('page-heading').text()).toBe('Status')
      expect(find('status-fine').text()).toBe('Everything checks out.')
      expect(find('status-attention').exists()).toBe(false)
    })

    it('tells which version this is and how long it has run', async () => {
      const { facts } = await open()
      expect(facts('status-aresgate')).toEqual({
        Version: '0.0.1',
        Commit: '0123456789ab',
        Built: expect.stringMatching(/2026/),
        Environment: 'production',
        Started: expect.stringMatching(/2026/),
        'Running for': '2d 5h 7m',
      })
    })

    it('tells what it runs on, down to the database', async () => {
      const { facts } = await open()
      expect(facts('status-software')).toEqual({
        Python: '3.14.8',
        nginx: '1.29.2',
        PostgreSQL: '18.1',
        'Database size': '12.0 MB',
        Connections: '4 of 100',
        Migration: '0008 (up to date)',
      })
    })

    it('tells about the certificate browsers are shown', async () => {
      const { facts, find } = await open()
      expect(find('status-certificate').exists()).toBe(true)
      expect(facts('status-certificate')).toEqual({
        Names: 'aresgate.home, aresgate.local',
        'Issued by': 'AresGate local CA',
        'Valid from': expect.stringMatching(/2026/),
        'Valid until': expect.stringMatching(/2027.*\(expires in 312 days\)$/),
      })
    })

    it('says so when the certificate signed itself', async () => {
      const report = healthy()
      report.stack.certificate!.self_signed = true
      const { facts } = await open(report)
      expect(facts('status-certificate')['Issued by']).toBe('Itself (self-signed)')
    })

    it('tells about the container, with bars for memory and disk', async () => {
      const { facts, wrapper } = await open()
      expect(facts('status-container')).toEqual({
        CPUs: '2',
        'Load (1, 5, 15 minutes)': '0.50 · 0.25 · 0.10',
        Clock: 'In step with this computer',
      })
      const meters = wrapper.findAll('[data-test="usage-meter"]').map((meter) => meter.text())
      expect(meters).toEqual([
        expect.stringContaining('Memory1.0 GB of 4.0 GB · 25%'),
        expect.stringContaining('Data disk2.0 GB of 10.0 GB · 20%'),
      ])
    })

    it("measures memory against the computer's when nothing limits the container", async () => {
      const report = healthy()
      report.container.memory = { used_bytes: 2 * GB, limit_bytes: null, total_bytes: 8 * GB }
      const { wrapper } = await open(report)
      expect(wrapper.find('[data-test="usage-meter"]').text()).toContain('2.0 GB of 8.0 GB · 25%')
    })

    it('lists the parts with how each is doing', async () => {
      const { find, texts, wrapper } = await open()
      expect(find('status-parts').exists()).toBe(true)
      expect(texts('part-name')).toEqual(['OPNsense', 'Wazuh'])
      expect(texts('part-state')).toEqual(['Working', 'Off'])
      const details = texts('part-detail')
      expect(details[0]).toMatch(/^Last worked 5 minutes ago$/)
      expect(details[1]).toBe('Not connected.')
      const links = wrapper.findAll('[data-test="part-open"]')
      expect(links.map((link) => link.attributes('href'))).toEqual([
        '/integrations/opnsense',
        '/integrations/wazuh',
      ])
      expect(links[0]?.attributes('aria-label')).toBe('Open OPNsense')
    })

    it.each([
      ['ok', 'Working'],
      ['problem', 'Problem'],
      ['unknown', 'Not tested yet'],
      ['off', 'Off'],
    ] as const)('says a part in the state %s is "%s"', async (state, label) => {
      const report = healthy()
      report.parts = [
        {
          key: 'wazuh',
          name: 'Wazuh',
          group: 'integration',
          state,
          detail: null,
          last_success_at: null,
        },
      ]
      const { texts } = await open(report)
      expect(texts('part-state')).toEqual([label])
    })

    it('shows why a part has a problem, and when it last worked', async () => {
      const report = healthy()
      report.parts = [
        {
          key: 'wazuh',
          name: 'Wazuh',
          group: 'integration',
          state: 'problem',
          detail: 'The certificate was refused.',
          last_success_at: new Date(Date.now() - 3 * 3600_000).toISOString(),
        },
      ]
      const { texts } = await open(report)
      expect(texts('part-detail')).toEqual([
        'The certificate was refused. · Last worked 3 hours ago',
      ])
    })

    it('says nothing about a part that has nothing to say', async () => {
      const report = healthy()
      report.parts = [
        {
          key: 'wazuh',
          name: 'Wazuh',
          group: 'integration',
          state: 'ok',
          detail: null,
          last_success_at: null,
        },
      ]
      const { find } = await open(report)
      expect(find('part-name').text()).toBe('Wazuh')
      expect(find('part-detail').exists()).toBe(false)
    })

    it('says what it can when it is running from source', async () => {
      const { facts, find, wrapper } = await open(bare())
      expect(facts('status-aresgate')).toMatchObject({
        Commit: 'Not recorded',
        Built: 'Not recorded',
      })
      expect(facts('status-software')).toEqual({
        Python: '3.14.8',
        nginx: 'Not found',
        PostgreSQL: 'Unknown',
        Migration: 'none (up to date)',
      })
      expect(find('status-certificate').exists()).toBe(false)
      expect(facts('status-container')).toEqual({
        CPUs: 'Unknown',
        'Load (1, 5, 15 minutes)': 'Unknown',
        Clock: 'In step with this computer',
        'Memory in use': '3.0 GB',
      })
      expect(wrapper.find('[data-test="usage-meter"]').exists()).toBe(false)
    })

    it('has no memory figure where the container reports none', async () => {
      const report = healthy()
      report.container.memory = null
      const { facts, wrapper } = await open(report)
      expect(facts('status-container')).not.toHaveProperty('Memory in use')
      expect(wrapper.findAll('[data-test="usage-meter"]')).toHaveLength(1)
    })
  })

  describe('what needs a look', () => {
    const items = async (report: statusApi.StatusReport) =>
      (await open(report)).texts('status-attention-item')

    it('says when the database is not answering, and leaves out its facts', async () => {
      const report = healthy()
      report.stack.database = {
        status: 'unavailable',
        version: null,
        size_bytes: null,
        connections: null,
        max_connections: null,
        migration: null,
        migration_head: '0008',
      }
      const { find, facts } = await open(report)
      expect(find('status-attention').text()).toContain('One thing needs a look')
      expect(await items(report)).toEqual(["The database isn't answering."])
      expect(facts('status-software')).toEqual({
        Python: '3.14.8',
        nginx: '1.29.2',
        PostgreSQL: 'Not answering',
      })
    })

    it('says when the database and this version disagree about the migration', async () => {
      const report = healthy()
      report.stack.database.migration = '0007'
      const { facts } = await open(report)
      expect(await items(report)).toEqual([
        'The database is at migration 0007, but this version of AresGate expects 0008.',
      ])
      expect(facts('status-software').Migration).toBe('0007, expected 0008')
    })

    it('says so when the database has no migration yet', async () => {
      const report = healthy()
      report.stack.database.migration = null
      expect(await items(report)).toEqual([
        'The database is at migration none, but this version of AresGate expects 0008.',
      ])
    })

    it.each([
      [14, 'The certificate expires in 14 days.'],
      [2, 'The certificate expires in 2 days.'],
      [1, 'The certificate expires in 1 day.'],
      [0, 'The certificate expires within a day.'],
      [-3, 'The certificate has expired.'],
    ])('says when the certificate has %d days left', async (days, said) => {
      const report = healthy()
      report.stack.certificate!.days_left = days
      expect(await items(report)).toEqual([said])
    })

    it('leaves a certificate with time left alone', async () => {
      const report = healthy()
      report.stack.certificate!.days_left = 15
      expect(await items(report)).toEqual([])
    })

    it('says which part has a problem', async () => {
      const report = healthy()
      report.parts[0]!.state = 'problem'
      expect(await items(report)).toEqual(['OPNsense has a problem.'])
    })

    it('says when AresGate runs behind this computer', async () => {
      const report = healthy()
      report.container.server_time = new Date(Date.now() - 5 * MINUTE).toISOString()
      const { facts, texts } = await open(report)
      expect(texts('status-attention-item')).toEqual([
        "AresGate's clock is 5m behind this computer.",
      ])
      expect(facts('status-container').Clock).toBe('5m behind this computer')
    })

    it('says when AresGate runs ahead of this computer', async () => {
      const report = healthy()
      report.container.server_time = new Date(Date.now() + 2 * 3600_000).toISOString()
      const { facts } = await open(report)
      expect(facts('status-container').Clock).toMatch(/^(1h 59m|2h 0m) ahead of this computer$/)
    })

    it('puts up with a clock a little off', async () => {
      const report = healthy()
      report.container.server_time = new Date(Date.now() - 50_000).toISOString()
      expect((await open(report)).find('status-fine').exists()).toBe(true)
    })

    it('lists every one of several', async () => {
      const report = healthy()
      report.stack.certificate!.days_left = 3
      report.parts[0]!.state = 'problem'
      const { find } = await open(report)
      expect(find('status-attention').text()).toContain('Some things need a look')
      expect(await items(report)).toHaveLength(2)
    })
  })

  describe('asking again', () => {
    it('reads the report again when asked to', async () => {
      const { fetch, find, texts } = await open()
      const next = healthy()
      next.parts[0]!.state = 'problem'
      fetch.mockResolvedValue(next)
      await find('status-refresh').trigger('click')
      await flushPromises()
      expect(fetch).toHaveBeenCalledTimes(2)
      expect(texts('part-state')).toEqual(['Problem', 'Off'])
    })

    it('says so when it cannot be read, and tries again', async () => {
      const { fetch, find } = await open(offline())
      expect(find('status-error').text()).toContain("Can't reach AresGate.")
      expect(find('status-aresgate').exists()).toBe(false)
      fetch.mockResolvedValue(healthy())
      await find('status-retry').trigger('click')
      await flushPromises()
      expect(find('status-error').exists()).toBe(false)
      expect(find('status-aresgate').exists()).toBe(true)
    })

    it('drops what it showed when asking again fails, so that nothing out of date is shown', async () => {
      const { fetch, find } = await open()
      fetch.mockRejectedValue(offline())
      await find('status-refresh').trigger('click')
      await flushPromises()
      expect(find('status-error').exists()).toBe(true)
      expect(find('status-aresgate').exists()).toBe(false)
    })

    it('notes that the sign-in is over when the API says so', async () => {
      await open(new ApiError(401, 'Sign in again.', 'unauthenticated'))
      expect(useSessionStore().expired).toBe(true)
    })
  })

  describe('copying it for a bug report', () => {
    afterEach(() => {
      Reflect.deleteProperty(navigator, 'clipboard')
    })

    const withClipboard = (writeText: (text: string) => Promise<void>) =>
      Object.defineProperty(navigator, 'clipboard', { value: { writeText }, configurable: true })

    it('shows the text', async () => {
      const { find } = await open()
      expect(find('diagnostics').text()).toBe('AresGate diagnostics\nVersion: 0.0.1')
      expect(find('status-copied').exists()).toBe(false)
      expect(find('status-copy-failed').exists()).toBe(false)
    })

    it('copies it, and says so', async () => {
      const writeText = vi.fn().mockResolvedValue(undefined)
      withClipboard(writeText)
      const { find } = await open()
      await find('status-copy').trigger('click')
      await flushPromises()
      expect(writeText).toHaveBeenCalledWith('AresGate diagnostics\nVersion: 0.0.1')
      expect(find('status-copied').text()).toBe('Copied.')
    })

    it('says to copy it by hand when the browser would not', async () => {
      withClipboard(vi.fn().mockRejectedValue(new DOMException('No', 'NotAllowedError')))
      const { find } = await open()
      await find('status-copy').trigger('click')
      await flushPromises()
      expect(find('status-copy-failed').text()).toContain('copy it yourself')
      expect(find('status-copied').exists()).toBe(false)
    })

    it('says the same when the browser has no clipboard to offer', async () => {
      const { find } = await open()
      await find('status-copy').trigger('click')
      await flushPromises()
      expect(find('status-copy-failed').exists()).toBe(true)
    })
  })
})
