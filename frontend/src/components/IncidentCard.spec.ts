import { ApiError } from '@/api/client'
import * as incidentsApi from '@/api/incidents'
import * as verdictsApi from '@/api/verdicts'
import IncidentCard from '@/components/IncidentCard.vue'
import { detail, incident, signal } from '@/test/incidents'
import { flushPromises, mountWithPlugins } from '@/test/mount'
import { given } from '@/test/verdicts'

async function show(changes: Parameters<typeof incident>[0] = {}, width?: number) {
  const mounted = await mountWithPlugins(IncidentCard, {
    props: { incident: incident(changes) },
    withApp: true,
    signedIn: 'admin',
    ...(width ? { width } : {}),
  })
  const text = (selector: string) => mounted.wrapper.find(`[data-test="${selector}"]`).text()
  return { ...mounted, text }
}

describe('IncidentCard', () => {
  it('leads to the incident', async () => {
    const { wrapper } = await show({ id: 7 })

    expect(wrapper.find('[data-test="incident"]').attributes('href')).toBe('/incidents/7')
  })

  it('says how serious it is, what it is and how sure AresGate is', async () => {
    const { wrapper, text } = await show()

    expect(text('severity')).toBe('High')
    expect(text('incident-title')).toBe('Brute force on ssh (93.184.216.34)')
    expect(text('confidence-level')).toBe('High confidence')
    expect(text('confidence-value')).toBe('70 of 100')
    expect(wrapper.find('[data-test="incident-card"]').attributes('style')).toContain(
      '--incident-accent: rgb(var(--v-theme-error))',
    )
  })

  it('says how many signals there were, over how long, and who saw them', async () => {
    const { text } = await show()

    expect(text('incident-signals')).toBe('3 signals over 18m')
    expect(text('incident-programs')).toBe('Seen by OPNsense, Wazuh')
  })

  it('says a single signal in the singular, with no stretch of time', async () => {
    const { text } = await show({ signal_count: 1 })

    expect(text('incident-signals')).toBe('1 signal')
  })

  it('says how long ago the last signal was, and the exact time on hover', async () => {
    const { wrapper, text } = await show()

    expect(text('incident-when')).toBe('2 minutes ago')
    expect(wrapper.find('[data-test="incident-when"]').attributes('title')).toMatch(/\d/)
    expect(wrapper.find('time').attributes('datetime')).toMatch(/^\d{4}-\d{2}-\d{2}T/)
  })

  it('names the address it is about and how many others are in it', async () => {
    const { text } = await show({ addresses: ['93.184.216.34', '192.168.1.20', '192.168.1.21'] })

    expect(text('incident-subject')).toBe('93.184.216.34 and 2 other addresses')
  })

  it('says one other address in the singular', async () => {
    const { text } = await show()

    expect(text('incident-subject')).toBe('93.184.216.34 and 1 other address')
  })

  it('names just the address when there are no others', async () => {
    const { text } = await show({ addresses: ['93.184.216.34'] })

    expect(text('incident-subject')).toBe('93.184.216.34')
  })

  describe('a bot that came back', () => {
    const sweep = {
      activities: ['scan' as const],
      waves: 3,
      port_count: 14,
      neighbours: 2,
      addresses: ['93.184.216.34', '93.184.216.35', '93.184.216.36', '192.168.1.20'],
    }

    it('says what it was doing, how many bursts it came in and how many ports it touched', async () => {
      const { text } = await show(sweep)

      expect(text('incident-activity-scan')).toBe('Scanning')
      expect(text('incident-waves')).toBe('3 waves')
      expect(text('incident-ports')).toBe('14 ports')
    })

    it('says how many of its neighbours are grouped in, and does not count them among the others', async () => {
      const { text } = await show(sweep)

      expect(text('incident-neighbours')).toBe('2 neighbouring addresses')
      expect(text('incident-subject')).toBe('93.184.216.34 and 1 other address')
    })

    it('says one neighbour in the singular, and no others when there are none', async () => {
      const { text } = await show({
        ...sweep,
        neighbours: 1,
        addresses: ['93.184.216.34', '93.184.216.35'],
      })

      expect(text('incident-neighbours')).toBe('1 neighbouring address')
      expect(text('incident-subject')).toBe('93.184.216.34')
    })

    it('says a brute force too, and "at least" for more ports than are kept', async () => {
      const { text } = await show({
        activities: ['brute_force', 'scan'],
        port_count: 1000,
        ports_capped: true,
      })

      expect(text('incident-activity-brute_force')).toBe('Brute force')
      expect(text('incident-ports')).toBe('at least 1,000 ports')
    })

    it('says nothing of any of it for a single burst on one port by one address', async () => {
      const { wrapper } = await show({ port_count: 1 })

      for (const part of ['waves', 'ports', 'neighbours', 'activity-scan']) {
        expect(wrapper.find(`[data-test="incident-${part}"]`).exists()).toBe(false)
      }
    })
  })

  it('says when it is about a rule that named no address', async () => {
    const { text } = await show({ subject: 'rule:wazuh:sshd', addresses: [] })

    expect(text('incident-subject')).toBe('A rule with no address')
  })

  it('shows what was done about it, unless nothing was', async () => {
    const open = await show()
    const resolved = await show({ status: 'resolved' })

    expect(open.wrapper.find('[data-test="incident-status"]').exists()).toBe(false)
    expect(resolved.text('incident-status')).toBe('Resolved')
  })

  it('says what you said of it, unless you said nothing', async () => {
    const plain = await show()
    const quiet = await show({ verdict: 'not_suspicious' })
    const threat = await show({ verdict: 'threat' })

    expect(plain.wrapper.find('[data-test="verdict"]').exists()).toBe(false)
    expect(quiet.text('verdict')).toBe('Not suspicious')
    expect(threat.text('verdict')).toBe('Real threat')
  })

  it('says when an address was banned', async () => {
    const plain = await show()
    const banned = await show({ banned: true })

    expect(plain.wrapper.find('[data-test="incident-banned"]').exists()).toBe(false)
    expect(banned.text('incident-banned')).toBe('Banned')
  })

  it('takes its color from how serious it is', async () => {
    const { wrapper } = await show({ severity: 'low' })

    expect(wrapper.find('[data-test="incident-card"]').attributes('style')).toContain(
      'rgb(var(--v-theme-success))',
    )
  })

  describe('saying what you think of it', () => {
    const offline = () => new ApiError(0, "Can't reach AresGate.", 'offline')

    async function judge(changes: Parameters<typeof incident>[0] = {}, width?: number) {
      const give = vi.spyOn(verdictsApi, 'giveVerdict').mockResolvedValue(given())
      const fetchIncident = vi.spyOn(incidentsApi, 'fetchIncident')
      const mounted = await show(changes, width)
      const press = async (kind: string) => {
        await mounted.wrapper.find(`[data-test="quick-${kind}"]`).trigger('click')
        await flushPromises()
      }
      const judged = () => mounted.wrapper.findComponent(IncidentCard).emitted('judged') ?? []
      return { ...mounted, give, fetchIncident, press, judged }
    }

    it('offers the three verdicts beside the link, never inside it', async () => {
      const { wrapper } = await judge()

      const buttons = wrapper.findAll('fieldset [data-test^="quick-"]')
      expect(buttons.map((button) => button.text())).toEqual([
        'Not suspicious',
        'Low priority',
        'Real threat',
      ])
      expect(wrapper.find('a [data-test^="quick-"]').exists()).toBe(false)
      expect(wrapper.find('fieldset legend').text()).toBe('Say what you think of it')
    })

    it('names what a verdict is about, for those who cannot see the card', async () => {
      const { wrapper } = await judge()

      expect(wrapper.find('[data-test="quick-threat"]').attributes('aria-label')).toBe(
        'Real threat: everything about 93.184.216.34',
      )
    })

    it('gives it about the address, with the security token, and says what it gave', async () => {
      const { give, press, judged } = await judge()

      await press('not_suspicious')

      expect(give).toHaveBeenCalledWith(
        { verdict: 'not_suspicious', address: '93.184.216.34' },
        'a-security-token',
      )
      const [[said]] = judged() as [[{ kind: string; scope: { key: string } }]]
      expect(said).toMatchObject({ kind: 'not_suspicious', scope: { key: 'address' } })
    })

    it('does not ask for the incident when it has an address', async () => {
      const { fetchIncident, press } = await judge()

      await press('low_priority')

      expect(fetchIncident).not.toHaveBeenCalled()
    })

    it('judges an incident about a rule by the first alert in it', async () => {
      const { give, fetchIncident, press } = await judge({
        id: 9,
        subject: 'rule:wazuh:Brute force on ssh',
        addresses: [],
      })
      fetchIncident.mockResolvedValue(
        detail({ subject: 'rule:wazuh:Brute force on ssh', signals: [signal()] }),
      )

      await press('low_priority')

      expect(fetchIncident).toHaveBeenCalledWith(9)
      expect(give).toHaveBeenCalledWith(
        { verdict: 'low_priority', source: 'wazuh', signature: 'Brute force on ssh' },
        'a-security-token',
      )
    })

    it('says so when an incident about a rule has nothing to judge it by', async () => {
      const { give, fetchIncident, press, text, judged } = await judge({
        subject: 'rule:wazuh:sshd',
        addresses: [],
      })
      fetchIncident.mockResolvedValue(
        detail({ subject: 'rule:wazuh:sshd', signals: [signal({ signature: null })] }),
      )

      await press('threat')

      expect(text('quick-error')).toContain('nothing to judge by')
      expect(give).not.toHaveBeenCalled()
      expect(judged()).toHaveLength(0)
    })

    it('says what went wrong, and lets it be tried again', async () => {
      const { give, press, text, judged, wrapper } = await judge()
      give.mockRejectedValueOnce(offline())

      await press('threat')
      expect(text('quick-error')).toBe("Can't reach AresGate.")
      expect(judged()).toHaveLength(0)

      await press('threat')
      expect(wrapper.find('[data-test="quick-error"]').exists()).toBe(false)
      expect(judged()).toHaveLength(1)
    })

    it('leaves the others alone while one is being given', async () => {
      const { give, wrapper } = await judge()
      give.mockReturnValue(new Promise(() => {}))

      await wrapper.find('[data-test="quick-threat"]').trigger('click')

      const disabled = wrapper
        .findAll('button[data-test^="quick-"]')
        .map((button) => button.attributes('disabled') !== undefined)
      expect(disabled).toEqual([true, true, false])
    })

    it('stacks the icon over the name on a phone', async () => {
      const { wrapper } = await judge({}, 400)

      expect(wrapper.find('[data-test="quick-threat"]').classes()).toContain('v-btn--stacked')
    })
  })

  describe('picking it', () => {
    async function pickable(props: { selectable?: boolean; selected?: boolean } = {}) {
      const mounted = await mountWithPlugins(IncidentCard, {
        props: { incident: incident(), ...props },
        withApp: true,
        signedIn: 'admin',
      })
      const box = () => mounted.wrapper.find('[data-test="incident-select"]')
      const picks = () => mounted.wrapper.findComponent(IncidentCard).emitted('select') ?? []
      return { ...mounted, box, picks }
    }

    it('has no box unless it can be picked', async () => {
      const { box, wrapper } = await pickable()

      expect(box().exists()).toBe(false)
      expect(wrapper.find('[data-test="incident-card"]').classes()).not.toContain(
        'incident-card--selectable',
      )
    })

    it('has a box that is named after it', async () => {
      const { box, wrapper } = await pickable({ selectable: true })

      expect(box().attributes('aria-label')).toBe('Select: Brute force on ssh (93.184.216.34)')
      expect((box().element as HTMLInputElement).checked).toBe(false)
      expect(wrapper.find('[data-test="incident-card"]').classes()).toContain(
        'incident-card--selectable',
      )
    })

    it('shows that it is picked, in the box and on the card', async () => {
      const { box, wrapper } = await pickable({ selectable: true, selected: true })

      expect((box().element as HTMLInputElement).checked).toBe(true)
      expect(wrapper.find('[data-test="incident-card"]').classes()).toContain(
        'incident-card--selected',
      )
    })

    it('says when it was ticked, and whether the shift key was held', async () => {
      const { box, picks } = await pickable({ selectable: true })

      await box().trigger('click')
      await box().trigger('click', { shiftKey: true })

      expect(picks()).toEqual([[false], [true]])
    })
  })
})
