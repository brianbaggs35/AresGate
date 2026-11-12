import EvidenceDetails from '@/components/EvidenceDetails.vue'
import { evidence, flowEnd } from '@/test/incidents'
import { mountWithPlugins } from '@/test/mount'

async function show(changes: Parameters<typeof evidence>[0]) {
  const { wrapper } = await mountWithPlugins(EvidenceDetails, {
    props: { evidence: evidence(changes) },
  })
  return wrapper
}

describe('EvidenceDetails', () => {
  it('shows only what the program said', async () => {
    const wrapper = await show({ host: 'web1 (192.168.1.20)' })

    expect(wrapper.find('[data-test="evidence-host"]').text()).toBe('web1 (192.168.1.20)')
    for (const absent of [
      'evidence-app',
      'evidence-facts',
      'evidence-mitre',
      'evidence-named',
      'evidence-traffic',
      'evidence-tags',
      'evidence-excerpt',
    ]) {
      expect(wrapper.find(`[data-test="${absent}"]`).exists()).toBe(false)
    }
  })

  it('shows the application, the facts and the technique with its tactic', async () => {
    const wrapper = await show({
      app: 'ssh',
      facts: [
        { label: 'Rule', value: '5760' },
        { label: 'Level', value: '5' },
      ],
      mitre: [
        { id: 'T1110', tactic: 'Credential Access', technique: 'Brute Force' },
        { id: 'T1078', tactic: '', technique: 'Valid Accounts' },
      ],
    })

    expect(wrapper.find('[data-test="evidence-app"]').text()).toBe('ssh')
    expect(wrapper.find('[data-test="evidence-facts"]').text()).toContain('Rule5760')
    const techniques = wrapper.findAll('[data-test="evidence-mitre"] li').map((each) => each.text())
    expect(techniques).toEqual(['T1110 Brute Force (Credential Access)', 'T1078 Valid Accounts'])
  })

  it('groups what it named by kind, in the singular for one and the plural for more', async () => {
    const wrapper = await show({
      named: [
        { kind: 'user', value: 'root' },
        { kind: 'hostname', value: 'a.example' },
        { kind: 'hostname', value: 'b.example' },
      ],
    })

    const groups = wrapper.findAll('[data-test="evidence-named"]')
    expect(groups.map((each) => each.find('h4').text())).toEqual(['User', 'Host names'])
    expect(groups[1]?.findAll('li').map((each) => each.text())).toEqual(['a.example', 'b.example'])
  })

  it('draws how much traffic it was, and says it for those who cannot see the bars', async () => {
    const wrapper = await show({
      traffic: { packets_out: 14, packets_in: 9, bytes_out: 2048, bytes_in: null },
    })

    const volumes = wrapper.findAll('[data-test="evidence-traffic"] figure')
    expect(volumes).toHaveLength(2)
    expect(volumes[0]?.text()).toContain('Packets')
    expect(volumes[0]?.text()).toContain('Sent: 14')
    expect(volumes[0]?.text()).toContain('Received: 9')
    expect(volumes[1]?.text()).toContain('Received: not said')
    expect(volumes[0]?.find('.evidence__out').attributes('style')).toContain('width: 61%')
  })

  it('shows its tags and the log line it came from', async () => {
    const wrapper = await show({
      tags: ['syslog', 'sshd'],
      excerpt: 'sshd: Failed password for root',
    })

    expect(
      wrapper.findAll('[data-test="evidence-tags"] .v-chip').map((each) => each.text()),
    ).toEqual(['syslog', 'sshd'])
    expect(wrapper.find('[data-test="evidence-excerpt"] code').text()).toBe(
      'sshd: Failed password for root',
    )
  })

  it('says what the program says of the flow in its own plain words, with its score', async () => {
    const wrapper = await show({ summary: 'Low goodput ratio [19.7%]', score: 10 })

    expect(wrapper.find('[data-test="evidence-summary"]').text()).toBe('Low goodput ratio [19.7%]')
    expect(wrapper.find('[data-test="evidence-score"]').text()).toBe('Its own score: 10')
  })

  it('names the two ends of the flow and how long it lasted', async () => {
    const wrapper = await show({
      flow: {
        client: flowEnd({ address: '192.168.7.57', name: 'workstation' }),
        server: flowEnd({
          address: '8.8.4.4',
          port: 53,
          service: 'domain',
          country: 'US',
          blacklisted: true,
        }),
        protocol: 'tcp',
        duration: 61,
      },
    })

    expect(wrapper.find('[data-test="evidence-flow"]').text()).toBe(
      'workstation8.8.4.4, port 53 (domain) (United States) (on a blacklist)',
    )
    expect(wrapper.find('[data-test="evidence-duration"]').text()).toBe('Lasted 1 min 1 s')
  })

  it('names one end where only one is known, and no time where there is none', async () => {
    const wrapper = await show({
      flow: {
        client: null,
        server: flowEnd({ address: '8.8.4.4', blacklisted: false }),
        protocol: null,
        duration: null,
      },
    })

    expect(wrapper.find('[data-test="evidence-flow"]').text()).toBe('8.8.4.4')
    expect(wrapper.find('[data-test="evidence-duration"]').exists()).toBe(false)
  })

  it('shows what was sent where the packet was kept', async () => {
    const wrapper = await show({ payload: 'GET /admin HTTP/1.1' })

    expect(wrapper.find('[data-test="evidence-payload"] code').text()).toBe('GET /admin HTTP/1.1')
  })

  it('lays out the first bytes of the packet as a dump', async () => {
    const wrapper = await show({
      dump: [
        { offset: '0000', hex: '47 45 54 20 2f', text: 'GET /' },
        { offset: '0010', hex: '61 64 6d', text: 'adm' },
      ],
    })

    expect(wrapper.findAll('th').map((cell) => cell.text())).toEqual([
      'Offset',
      'Bytes in hexadecimal',
      'As text',
    ])
    const rows = wrapper.findAll('[data-test="evidence-dump-row"]')
    expect(rows).toHaveLength(2)
    expect(rows[0]?.findAll('td').map((cell) => cell.text())).toEqual([
      '0000',
      '47 45 54 20 2f',
      'GET /',
    ])
    expect(rows[1]?.findAll('td').map((cell) => cell.text())).toEqual(['0010', '61 64 6d', 'adm'])
  })

  it('shows no dump where the packet was not kept', async () => {
    const wrapper = await show({ host: 'web1' })

    expect(wrapper.find('[data-test="evidence-dump"]').exists()).toBe(false)
  })
})
