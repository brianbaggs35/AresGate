import { ApiError } from '@/api/client'
import * as incidentsApi from '@/api/incidents'
import * as verdictsApi from '@/api/verdicts'
import VerdictPanel from '@/components/VerdictPanel.vue'
import { useSessionStore } from '@/stores/session'
import { detail, incident, reading, signal, triage } from '@/test/incidents'
import { flushPromises, mountWithPlugins } from '@/test/mount'
import { verdict } from '@/test/verdicts'
import IncidentView from '@/views/IncidentView.vue'

const offline = () => new ApiError(0, "Can't reach AresGate.", 'offline')
const MINUTE = 60_000

interface Options {
  found?: incidentsApi.IncidentDetail | Error
  verdicts?: verdictsApi.Verdict[] | Error
}

async function open({ found = detail(), verdicts = [] }: Options = {}) {
  const fetchIncident = vi.spyOn(incidentsApi, 'fetchIncident')
  if (found instanceof Error) fetchIncident.mockRejectedValue(found)
  else fetchIncident.mockResolvedValue(found)
  const fetchVerdicts = vi.spyOn(verdictsApi, 'fetchVerdicts')
  if (verdicts instanceof Error) fetchVerdicts.mockRejectedValue(verdicts)
  else fetchVerdicts.mockResolvedValue(verdicts)
  const setStatus = vi.spyOn(incidentsApi, 'setIncidentStatus')
  const ask = vi.spyOn(incidentsApi, 'askAi').mockResolvedValue(triage())
  const mounted = await mountWithPlugins(IncidentView, {
    signedIn: 'admin',
    withApp: true,
    route: '/incidents/1',
  })
  await flushPromises()
  const find = (selector: string) => mounted.wrapper.find(`[data-test="${selector}"]`)
  const text = (selector: string) => find(selector).text()
  return { ...mounted, fetchIncident, fetchVerdicts, setStatus, ask, find, text }
}

describe('IncidentView', () => {
  it('asks for the incident that is in the address of the page', async () => {
    const { fetchIncident } = await open()

    expect(fetchIncident).toHaveBeenCalledTimes(1)
    expect(fetchIncident).toHaveBeenCalledWith(1)
  })

  it('shows a skeleton until the answer arrives', async () => {
    vi.spyOn(incidentsApi, 'fetchIncident').mockReturnValue(new Promise(() => {}))
    const { wrapper } = await mountWithPlugins(IncidentView, {
      signedIn: 'admin',
      route: '/incidents/1',
    })

    expect(wrapper.find('[data-test="incident-loading"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="incident-hero"]').exists()).toBe(false)
  })

  describe('the top of the page', () => {
    it('names the incident and leads back to the list', async () => {
      const { wrapper } = await open()

      expect(wrapper.find('h1').text()).toBe('Brute force on ssh (93.184.216.34)')
      const back = wrapper.find('a[href="/incidents"]')
      expect(back.text()).toContain('Incidents')
    })

    it('says how serious it is, what became of it and how sure AresGate is', async () => {
      const { wrapper, text } = await open()

      expect(wrapper.find('[data-test="severity"]').text()).toBe('High')
      expect(wrapper.find('[data-test="incident-status"]').text()).toBe('Open')
      expect(text('confidence-chip')).toBe('High confidence')
    })

    it('says when it began and when it last did something', async () => {
      const { text } = await open()

      expect(text('incident-when')).toMatch(/^First signal .+, the last 2 minutes ago\.$/)
    })

    it('says what its status means', async () => {
      const { text } = await open()

      expect(text('incident-meaning')).toBe("Open: Nobody has said they're looking at it.")
    })

    it('says when its status was set, once someone set it', async () => {
      const changed = new Date(Date.now() - 5 * MINUTE).toISOString()
      const { text } = await open({
        found: detail({ status: 'investigating', status_changed_at: changed }),
      })

      expect(text('incident-meaning')).toBe(
        "Investigating: You're looking into it. Set 5 minutes ago.",
      )
    })
  })

  describe('your verdicts', () => {
    it('has a panel to give them in, told which apply to it', async () => {
      const rules = [verdict({ id: 4, address: '93.184.216.34' })]
      const { wrapper, fetchVerdicts } = await open({
        found: detail({ verdict: 'not_suspicious' }),
        verdicts: rules,
      })

      expect(fetchVerdicts).toHaveBeenCalledTimes(1)
      const panel = wrapper.findComponent(VerdictPanel)
      expect(panel.exists()).toBe(true)
      expect(panel.props('verdicts')).toEqual(rules)
    })

    it('puts what you said of the incident at the top, next to how serious it is', async () => {
      const { wrapper } = await open({ found: detail({ verdict: 'threat' }) })

      expect(wrapper.find('.incident__chips [data-test="verdict"]').text()).toBe('Real threat')
    })

    it('says no such thing for an incident you have said nothing of', async () => {
      const { wrapper } = await open()

      expect(wrapper.find('.incident__chips [data-test="verdict"]').exists()).toBe(false)
    })

    it('says how many signals are left out of the count', async () => {
      const { text } = await open({
        found: detail({ verdict_counts: { not_suspicious: 2 } }),
      })

      expect(text('tile-signals')).toContain('over 18m, 2 not counted')
    })

    it('goes on without them when they cannot be loaded', async () => {
      const { text, wrapper } = await open({ verdicts: offline() })

      expect(text('tile-signals')).toContain('3')
      expect(wrapper.findComponent(VerdictPanel).props('verdicts')).toEqual([])
    })

    it('asks for the incident and the verdicts again after one is given or taken back', async () => {
      const { wrapper, fetchIncident, fetchVerdicts, text } = await open()
      fetchIncident.mockResolvedValue(detail({ verdict: 'not_suspicious' }))
      fetchVerdicts.mockResolvedValue([verdict()])

      wrapper.findComponent(VerdictPanel).vm.$emit('changed')
      await flushPromises()

      expect(fetchIncident).toHaveBeenCalledTimes(2)
      expect(fetchVerdicts).toHaveBeenCalledTimes(2)
      expect(wrapper.findComponent(VerdictPanel).props('verdicts')).toHaveLength(1)
      expect(wrapper.find('.incident__chips [data-test="verdict"]').text()).toBe('Not suspicious')
      expect(text('verdict-standing')).toContain('will not raise an alarm')
    })
  })

  describe('the hero', () => {
    it('says what happened: that the programs agree, and who reported what', async () => {
      const { text } = await open()

      expect(text('incident-hero-eyebrow')).toBe('What happened')
      expect(text('incident-hero-title')).toBe('2 programs agree')
      expect(text('incident-hero-detail')).toContain(
        'OPNsense and Wazuh reported 3 signals about 93.184.216.34',
      )
    })

    it('draws the confidence as a ring and says it in figures', async () => {
      const { find, text } = await open({ found: detail({ confidence: 70 }) })

      expect(text('confidence-score')).toContain('70')
      expect(text('confidence-score')).toContain('of 100')
      expect(find('incident-hero').find('.hero__arc').attributes('style')).toContain(
        'stroke-dashoffset: 30',
      )
    })

    it('is the color of how serious it is, and urgent while a serious one is not over', async () => {
      const { find } = await open({ found: detail({ severity: 'critical', status: 'open' }) })

      expect(find('incident-hero').attributes('style')).toContain('--v-theme-error')
      expect(find('incident-hero').attributes('data-mood')).toBe('urgent')
    })

    it('is calm for one that is not serious', async () => {
      const { find } = await open({ found: detail({ severity: 'medium' }) })

      expect(find('incident-hero').attributes('style')).toContain('--v-theme-warning')
      expect(find('incident-hero').attributes('data-mood')).toBe('calm')
    })

    it.each([
      ['resolved', 'success'],
      ['dismissed', 'secondary'],
    ] as const)('is the color of its status once it is %s, and calm', async (status, color) => {
      const { find } = await open({ found: detail({ severity: 'critical', status }) })

      expect(find('incident-hero').attributes('style')).toContain(`--v-theme-${color}`)
      expect(find('incident-hero').attributes('data-mood')).toBe('calm')
    })
  })

  describe('the tiles', () => {
    it('count the signals, and say over how long they came in', async () => {
      const { text } = await open()

      expect(text('tile-signals')).toContain('Signals')
      expect(text('tile-signals')).toContain('3')
      expect(text('tile-signals')).toContain('over 18m')
    })

    it('name the programs that saw it', async () => {
      const { text } = await open()

      expect(text('tile-programs')).toContain('2')
      expect(text('tile-programs')).toContain('OPNsense, Wazuh')
    })

    it('count the addresses, and how many of them are devices on the network', async () => {
      const { text } = await open()

      expect(text('tile-addresses')).toContain('2')
      expect(text('tile-addresses')).toContain('1 on your network')
    })

    it('say when there is only the one address', async () => {
      const { text } = await open({
        found: detail({ addresses: ['93.184.216.34'], devices: [] }),
      })

      expect(text('tile-addresses')).toContain('Only the one it is about')
    })

    it('count the firewall blocks of its address around then', async () => {
      const { text } = await open({ found: detail({ blocked: 1_250 }) })

      expect(text('tile-blocked')).toContain('1,250')
      expect(text('tile-blocked')).toContain('Of its address, around then')
    })

    it('say there are none to count when it is about a rule, with no address', async () => {
      const { text } = await open({
        found: detail({ blocked: null, subject: 'rule:wazuh:5710', addresses: [] }),
      })

      expect(text('tile-blocked')).toContain('None')
      expect(text('tile-blocked')).toContain('It is about a rule')
    })
  })

  describe('the reasons, the addresses and the timeline', () => {
    it('add up the reasons for the confidence', async () => {
      const { text } = await open()

      expect(text('reasons-card')).toContain('Why AresGate is this sure')
      expect(text('reasons-card')).toContain('Most serious signal')
      expect(text('reasons-card')).toContain('Other programs agree')
      expect(text('reasons-card')).toContain('It keeps happening')
    })

    it('name the devices behind the addresses', async () => {
      const { text } = await open()

      expect(text('addresses-card')).toContain('On your network')
      expect(text('addresses-card')).toContain('nas')
      expect(text('addresses-card')).toContain('Not a device AresGate knows.')
    })

    it('list every signal, oldest first', async () => {
      const { wrapper, text } = await open()

      expect(text('timeline-card')).toContain('Timeline')
      expect(wrapper.findAll('[data-test="signal"]')).toHaveLength(3)
    })
  })

  describe('why the signals are one incident', () => {
    it('says it in a line to a fact', async () => {
      const { wrapper, text } = await open()

      expect(text('grouping-card')).toContain('Why these signals are one incident')
      const lines = wrapper.findAll('[data-test="grouping-line"]')
      expect(lines).toHaveLength(2)
      expect(lines[0]?.text()).toBe(
        'Everything in it is about 93.184.216.34, whichever program saw it.',
      )
    })

    it('says what the activity was and how many waves it came in', async () => {
      const { find, text } = await open({
        found: detail({ activities: ['scan'], waves: 3, ports: [22, 80, 443] }),
      })

      expect(text('grouping-activity-scan')).toBe('Scanning')
      expect(text('waves')).toBe('3 waves')
      expect(find('ports-title').text()).toBe('The 3 ports it touched')
    })

    it('says nothing of waves for one that came in a single burst', async () => {
      const { find, text } = await open({ found: detail({ activities: ['brute_force'] }) })

      expect(text('grouping-activity-brute_force')).toBe('Brute force')
      expect(find('waves').exists()).toBe(false)
    })

    it('says the waves of an incident whose signals say nothing of what it was', async () => {
      const { find, text } = await open({ found: detail({ waves: 2 }) })

      expect(text('waves')).toBe('2 waves')
      expect(find('grouping-activity-scan').exists()).toBe(false)
    })

    it('has no chips for an incident of no particular activity in one wave', async () => {
      const { find } = await open()

      expect(find('waves').exists()).toBe(false)
      expect(find('grouping-activity-scan').exists()).toBe(false)
    })

    it('has no list of ports when it touched only the one', async () => {
      const { find } = await open()

      expect(find('ports').exists()).toBe(false)
    })
  })

  describe('the chart of signals over time', () => {
    it('counts them by program, and says how wide a bar is', async () => {
      const { wrapper, text } = await open()

      expect(text('spread-card')).toContain('Signals over time')
      expect(text('spread-card')).toContain(
        'Signals in each 1 minute, by the program that reported them.',
      )
      const labels = wrapper.findAll('[data-test="spread-card"] [data-test="chart-legend-label"]')
      expect(labels.map((label) => label.text())).toEqual(['OPNsense', 'Wazuh'])
    })

    it('says it only counts those that are listed when more were kept out', async () => {
      const { text } = await open({ found: detail({ signal_count: 1_500 }) })

      expect(text('spread-card')).toContain('Only those listed below.')
    })

    it('is left out when a single signal makes no story over time', async () => {
      const { find } = await open({
        found: detail({ signal_count: 1, signals: [signal()] }),
      })

      expect(find('spread-card').exists()).toBe(false)
    })
  })

  describe('what can be done', () => {
    it.each([
      ['open', ['investigating', 'resolved', 'dismissed']],
      ['investigating', ['resolved', 'dismissed', 'open']],
      ['resolved', ['open']],
      ['dismissed', ['open']],
    ] as const)(
      'offers, for an incident that is %s, the changes that make sense',
      async (status, offered) => {
        const { wrapper } = await open({ found: detail({ status }) })

        const buttons = wrapper.findAll('[data-test^="action-"]')
        expect(buttons.map((button) => button.attributes('data-test'))).toEqual(
          offered.map((one) => `action-${one}`),
        )
      },
    )

    it('changes the status when a change is chosen, with the sign-in’s security token', async () => {
      const { find, setStatus, ask, text } = await open()
      setStatus.mockResolvedValue(detail({ status: 'investigating' }))
      ask.mockResolvedValue(
        triage({ incident: detail({ status: 'investigating', reading: reading() }) }),
      )

      await find('action-investigating').trigger('click')
      await flushPromises()

      expect(setStatus).toHaveBeenCalledWith(1, 'investigating', 'a-security-token')
      expect(text('incident-meaning')).toContain('Investigating')
      expect(text('notice')).toBe('Marked as investigating.')
      expect(find('action-resolved').exists()).toBe(true)
      expect(find('action-investigating').exists()).toBe(false)
    })

    it('says an incident that was reopened is reopened', async () => {
      const { find, setStatus, text } = await open({ found: detail({ status: 'resolved' }) })
      setStatus.mockResolvedValue(detail({ status: 'open' }))

      await find('action-open').trigger('click')
      await flushPromises()

      expect(text('notice')).toBe('Reopened.')
    })

    it('shows that the change is under way, and lets no other be started meanwhile', async () => {
      const { find, setStatus } = await open()
      setStatus.mockReturnValue(new Promise(() => {}))

      await find('action-resolved').trigger('click')
      await flushPromises()

      expect(find('action-resolved').classes()).toContain('v-btn--loading')
      expect(find('action-dismissed').attributes('disabled')).toBeDefined()
      expect(find('action-investigating').attributes('disabled')).toBeDefined()
    })

    it('says why a change was not made, and keeps what it has', async () => {
      const { find, setStatus, text } = await open()
      setStatus.mockRejectedValue(offline())

      await find('action-resolved').trigger('click')
      await flushPromises()

      expect(text('change-error')).toContain("Can't reach AresGate.")
      expect(find('notice').exists()).toBe(false)
      expect(text('incident-meaning')).toContain('Open')
      expect(find('action-resolved').attributes('disabled')).toBeUndefined()
    })

    it('forgets the failure of a change when the next is made', async () => {
      const { find, setStatus } = await open()
      setStatus.mockRejectedValueOnce(offline())
      await find('action-resolved').trigger('click')
      await flushPromises()

      setStatus.mockResolvedValue(detail({ status: 'dismissed' }))
      await find('action-dismissed').trigger('click')
      await flushPromises()

      expect(find('change-error').exists()).toBe(false)
      expect(find('notice').exists()).toBe(true)
    })

    it('lets the failure be closed', async () => {
      const { find, wrapper, setStatus } = await open()
      setStatus.mockRejectedValue(offline())
      await find('action-resolved').trigger('click')
      await flushPromises()

      await wrapper.find('[data-test="change-error"] button').trigger('click')

      expect(find('change-error').exists()).toBe(false)
    })

    it('goes to the sign-in page when the sign-in has ended', async () => {
      const { find, setStatus, pinia } = await open()
      setStatus.mockRejectedValue(new ApiError(401, 'Sign in.', 'unauthenticated'))

      await find('action-resolved').trigger('click')
      await flushPromises()

      expect(useSessionStore(pinia).expired).toBe(true)
    })
  })

  describe('the AI', () => {
    it('says it has not read an incident, and offers to ask', async () => {
      const { text, find } = await open()

      expect(text('ai-unread')).toContain('The AI has not read this incident')
      expect(find('ai-ask').exists()).toBe(true)
      expect(find('ai-chip').exists()).toBe(false)
    })

    it('says which lane it is in, and shows the call on it beside how serious it is', async () => {
      const { wrapper } = await open({
        found: detail({
          lane: 'background',
          call: { classification: 'probe', confidence: 92, basis: 'family' },
        }),
      })

      expect(wrapper.find('.incident__chips [data-test="lane-chip"]').text()).toBe('Background')
      expect(wrapper.find('.incident__chips [data-test="call-chip"]').text()).toBe(
        'AI: Probe, 92% sure',
      )
      expect(wrapper.find('.incident__chips [data-test="ai-chip"]').exists()).toBe(false)
    })

    it('has no lane to show for one that is over', async () => {
      const { wrapper } = await open({ found: detail({ lane: null }) })

      expect(wrapper.find('.incident__chips [data-test="lane-chip"]').exists()).toBe(false)
    })

    it('says where it stands and why', async () => {
      const { find, text } = await open()

      expect(text('where-why')).toBe("AresGate's rules are 70% sure it is a real attack.")
      expect(find('where-open').attributes('href')).toBe('/threats/kinds/7')
    })

    it('shows what kept happening only when something did', async () => {
      const none = await open()
      expect(none.find('occurrences-card').exists()).toBe(false)

      const repeated = await open({
        found: detail({
          occurrences: [
            { signal: signal(), count: 40, last_at: new Date().toISOString(), duplicates: 0 },
          ],
        }),
      })
      expect(repeated.find('occurrences-card').exists()).toBe(true)

      const twice = await open({
        found: detail({
          occurrences: [
            { signal: signal(), count: 1, last_at: new Date().toISOString(), duplicates: 1 },
          ],
        }),
      })
      expect(twice.find('occurrences-card').exists()).toBe(true)
    })

    it('says what it made of an incident it has read, beside how serious it is', async () => {
      const { text, wrapper } = await open({
        found: detail({ reading: reading(), ai: { classification: 'probe', confidence: 91 } }),
      })

      expect(text('ai-headline')).toBe('An internet scanner tried ssh on one device')
      expect(wrapper.find('.incident__chips [data-test="ai-chip"]').text()).toBe(
        'AI: Probe, 91% sure',
      )
    })

    it('asks when it is asked to, and shows what it made of the incident', async () => {
      const { find, text, ask } = await open()

      await find('ai-ask').trigger('click')
      await flushPromises()

      expect(ask).toHaveBeenCalledWith(1, 'a-security-token')
      expect(text('ai-class')).toBe('Probe')
      expect(find('ai-failure').exists()).toBe(false)
      expect(find('ai-busy').exists()).toBe(false)
    })

    it('shows that the AI is reading it while it does', async () => {
      const { find, ask } = await open()
      ask.mockReturnValue(new Promise(() => {}))

      await find('ai-ask').trigger('click')
      await flushPromises()

      expect(find('ai-busy').exists()).toBe(true)
      expect(find('ai-ask').exists()).toBe(false)
    })

    it('says why the AI could not be asked, and the incident is as it was', async () => {
      const { find, text, ask } = await open()
      ask.mockResolvedValue(
        triage({
          ok: false,
          reason: 'AI is turned off. Turn it on under Settings > AI to use it.',
          incident: detail(),
        }),
      )

      await find('ai-ask').trigger('click')
      await flushPromises()

      expect(text('ai-failure')).toContain('AI is turned off.')
      expect(find('ai-reading').exists()).toBe(false)
    })

    it('says why when the request itself failed', async () => {
      const { find, text, ask } = await open()
      ask.mockRejectedValue(offline())

      await find('ai-ask').trigger('click')
      await flushPromises()

      expect(text('ai-failure')).toContain("Can't reach AresGate.")
    })

    it('forgets why it could not be asked when it is asked again', async () => {
      const { find, ask } = await open()
      ask.mockRejectedValueOnce(offline())
      await find('ai-ask').trigger('click')
      await flushPromises()

      await find('ai-ask').trigger('click')
      await flushPromises()

      expect(find('ai-failure').exists()).toBe(false)
      expect(find('ai-reading').exists()).toBe(true)
    })

    it('reads an incident when you start investigating it', async () => {
      const { find, setStatus, ask, text } = await open()
      setStatus.mockResolvedValue(detail({ status: 'investigating' }))
      ask.mockResolvedValue(
        triage({ incident: detail({ status: 'investigating', reading: reading() }) }),
      )

      await find('action-investigating').trigger('click')
      await flushPromises()

      expect(ask).toHaveBeenCalledWith(1, 'a-security-token')
      expect(text('notice')).toBe('Marked as investigating.')
      expect(text('ai-class')).toBe('Probe')
    })

    it('says plainly that the AI is off when you start investigating without it', async () => {
      const { find, setStatus, ask, text } = await open()
      setStatus.mockResolvedValue(detail({ status: 'investigating' }))
      ask.mockResolvedValue(
        triage({
          ok: false,
          reason: 'AI is turned off.',
          incident: detail({ status: 'investigating' }),
        }),
      )

      await find('action-investigating').trigger('click')
      await flushPromises()

      expect(text('ai-failure')).toContain('AI is turned off.')
      expect(text('incident-meaning')).toContain('Investigating')
    })

    it('does not read again an incident the AI has read in full', async () => {
      const read = detail({ reading: reading({ signals_read: 3 }) })
      const { find, setStatus, ask } = await open({ found: read })
      setStatus.mockResolvedValue({ ...read, status: 'investigating' })

      await find('action-investigating').trigger('click')
      await flushPromises()

      expect(ask).not.toHaveBeenCalled()
    })

    it('reads it again when signals came in after the AI read it', async () => {
      const grown = detail({ signal_count: 9, reading: reading({ signals_read: 3 }) })
      const { find, setStatus, ask } = await open({ found: grown })
      setStatus.mockResolvedValue({ ...grown, status: 'investigating' })

      await find('action-investigating').trigger('click')
      await flushPromises()

      expect(ask).toHaveBeenCalledTimes(1)
    })

    it('does not ask the AI about a status that was not changed', async () => {
      const { find, setStatus, ask } = await open()
      setStatus.mockRejectedValue(offline())

      await find('action-investigating').trigger('click')
      await flushPromises()

      expect(ask).not.toHaveBeenCalled()
    })

    it('does not ask the AI when it is resolved or dismissed', async () => {
      const { find, setStatus, ask } = await open()
      setStatus.mockResolvedValue(detail({ status: 'resolved' }))

      await find('action-resolved').trigger('click')
      await flushPromises()

      expect(ask).not.toHaveBeenCalled()
    })

    it('asks for the incident and the verdicts again after the AI’s verdict is given', async () => {
      const { find, fetchIncident, fetchVerdicts } = await open({
        found: detail({ reading: reading() }),
      })
      vi.spyOn(verdictsApi, 'giveVerdict').mockResolvedValue({
        ...verdict({ id: 3 }),
        replaced: null,
      })

      await find('ai-accept').trigger('click')
      await flushPromises()

      expect(fetchIncident).toHaveBeenCalledTimes(2)
      expect(fetchVerdicts).toHaveBeenCalledTimes(2)
    })

    it('does not let a refresh that was already on its way undo what the AI said', async () => {
      vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval'] })
      try {
        const { find, text, fetchIncident, ask } = await open()
        let settle: (value: incidentsApi.Triage) => void = () => {}
        ask.mockReturnValue(new Promise((resolve) => (settle = resolve)))
        await find('ai-ask').trigger('click')
        fetchIncident.mockResolvedValue(detail())

        vi.advanceTimersByTime(30_000)
        await flushPromises()
        settle(triage())
        await flushPromises()

        expect(text('ai-class')).toBe('Probe')
      } finally {
        vi.useRealTimers()
      }
    })
  })

  describe('when it cannot be loaded', () => {
    it('says so, and tries again', async () => {
      const { find, text, fetchIncident } = await open({ found: offline() })

      expect(text('incident-error')).toContain("Can't reach AresGate.")
      expect(find('incident-hero').exists()).toBe(false)

      fetchIncident.mockResolvedValue(detail())
      await find('retry').trigger('click')
      await flushPromises()

      expect(find('incident-error').exists()).toBe(false)
      expect(find('incident-hero').exists()).toBe(true)
    })

    it('says an incident that is not there may have been removed, and does not offer to try again', async () => {
      const { find, text } = await open({
        found: new ApiError(404, 'No such incident.', 'not_found'),
      })

      expect(text('incident-error')).toContain('No such incident. It may have been removed.')
      expect(find('retry').exists()).toBe(false)
    })

    it('leads back to the list from the page that says so', async () => {
      const { wrapper } = await open({ found: new ApiError(404, 'No such incident.', 'not_found') })

      expect(wrapper.find('a[href="/incidents"]').exists()).toBe(true)
    })

    it('keeps what it has while a refresh fails, and says how old it is', async () => {
      vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval'] })
      try {
        const { find, text, fetchIncident } = await open()
        fetchIncident.mockRejectedValue(offline())

        vi.advanceTimersByTime(30_000)
        await flushPromises()

        expect(text('incident-stale')).toContain("Can't reach AresGate.")
        expect(text('incident-stale')).toMatch(/is from \d/)
        expect(find('incident-hero').exists()).toBe(true)

        fetchIncident.mockResolvedValue(detail())
        vi.advanceTimersByTime(30_000)
        await flushPromises()
        expect(find('incident-stale').exists()).toBe(false)
      } finally {
        vi.useRealTimers()
      }
    })

    it('says it was removed when a refresh finds it gone', async () => {
      vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval'] })
      try {
        const { find, text, fetchIncident } = await open()
        fetchIncident.mockRejectedValue(new ApiError(404, 'No such incident.', 'not_found'))

        vi.advanceTimersByTime(30_000)
        await flushPromises()

        expect(text('incident-stale')).toContain('No such incident.')
        expect(find('incident-hero').exists()).toBe(true)
      } finally {
        vi.useRealTimers()
      }
    })
  })

  describe('refreshing', () => {
    it('asks again every half minute while the page is open, and shows what changed', async () => {
      vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval'] })
      try {
        const { fetchIncident, text } = await open()
        expect(text('tile-signals')).toContain('3')
        fetchIncident.mockResolvedValue(detail({ signal_count: 4, signals: [signal(), signal()] }))

        vi.advanceTimersByTime(30_000)
        await flushPromises()

        expect(fetchIncident).toHaveBeenCalledTimes(2)
        expect(text('tile-signals')).toContain('4')
      } finally {
        vi.useRealTimers()
      }
    })

    it('says when the numbers on screen arrived', async () => {
      const { text } = await open()

      expect(text('updated')).toMatch(/^Updated \d/)
      expect(text('updated')).toContain('every 30 seconds')
    })

    it('does not let an answer that was already on its way undo a change just made', async () => {
      vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval'] })
      try {
        const { find, text, fetchIncident, setStatus } = await open()
        let settle: (value: incidentsApi.IncidentDetail) => void = () => {}
        setStatus.mockReturnValue(new Promise((resolve) => (settle = resolve)))
        await find('action-resolved').trigger('click')
        fetchIncident.mockResolvedValue(detail({ status: 'open' }))

        vi.advanceTimersByTime(30_000)
        await flushPromises()
        settle(detail({ status: 'resolved' }))
        await flushPromises()

        expect(text('incident-meaning')).toContain('Resolved')
      } finally {
        vi.useRealTimers()
      }
    })

    it('ignores an old answer that arrives after a newer one', async () => {
      vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval'] })
      try {
        const fetchIncident = vi.spyOn(incidentsApi, 'fetchIncident')
        let late: (value: incidentsApi.IncidentDetail) => void = () => {}
        fetchIncident.mockReturnValueOnce(new Promise((resolve) => (late = resolve)))
        fetchIncident.mockResolvedValue(detail({ status: 'investigating' }))
        const { text } = await (async () => {
          const mounted = await mountWithPlugins(IncidentView, {
            signedIn: 'admin',
            withApp: true,
            route: '/incidents/1',
          })
          vi.advanceTimersByTime(30_000)
          await flushPromises()
          return {
            ...mounted,
            text: (id: string) => mounted.wrapper.find(`[data-test="${id}"]`).text(),
          }
        })()

        late(detail({ status: 'open' }))
        await flushPromises()

        expect(text('incident-meaning')).toContain('Investigating')
      } finally {
        vi.useRealTimers()
      }
    })

    it('ignores the failure of an old request that arrives after a newer answer', async () => {
      vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval'] })
      try {
        const fetchIncident = vi.spyOn(incidentsApi, 'fetchIncident')
        let fail: (reason: Error) => void = () => {}
        fetchIncident.mockReturnValueOnce(new Promise((_, reject) => (fail = reject)))
        fetchIncident.mockResolvedValue(detail())
        const { wrapper } = await mountWithPlugins(IncidentView, {
          signedIn: 'admin',
          withApp: true,
          route: '/incidents/1',
        })
        vi.advanceTimersByTime(30_000)
        await flushPromises()

        fail(offline())
        await flushPromises()

        expect(wrapper.find('[data-test="incident-stale"]').exists()).toBe(false)
        expect(wrapper.find('[data-test="incident-error"]').exists()).toBe(false)
      } finally {
        vi.useRealTimers()
      }
    })
  })

  it('keeps the incident it was given and does not mix it with another', async () => {
    const { text } = await open({
      found: detail({ ...incident({ id: 1, title: 'Port scan (198.51.100.7)' }) }),
    })

    expect(text('incident-meaning')).toContain('Open')
    expect(text('tile-signals')).toContain('3')
  })
})
