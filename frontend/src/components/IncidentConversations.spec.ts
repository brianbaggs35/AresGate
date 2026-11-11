import IncidentConversations from '@/components/IncidentConversations.vue'
import ConversationEnd from '@/components/ConversationEnd.vue'
import { conversation, conversationEnd } from '@/test/incidents'
import { mountWithPlugins } from '@/test/mount'

async function show(
  items = [conversation()],
  total = items.length,
): Promise<Awaited<ReturnType<typeof mountWithPlugins>>['wrapper']> {
  const { wrapper } = await mountWithPlugins(IncidentConversations, {
    props: { conversations: { items, total } },
  })
  return wrapper
}

describe('IncidentConversations', () => {
  it('says what the traffic was for, where that can be told', async () => {
    const wrapper = await show([conversation(), conversation({ purpose: null })])

    const said = wrapper.findAll('[data-test="conversation-purpose"]')
    expect(said).toHaveLength(1)
    expect(said[0]?.text().replace(/\s+/g, ' ')).toBe(
      'What it was for Looking up a name (DNS): example.com',
    )
  })

  it('draws the two ends, what it went over and how often it happened', async () => {
    const wrapper = await show()

    expect(wrapper.findAll('[data-test="conversation"]')).toHaveLength(1)
    expect(wrapper.find('[data-test="end-client"] [data-test="end-title"]').text()).toBe(
      'workstation',
    )
    expect(wrapper.find('[data-test="end-server"] [data-test="end-title"]').text()).toBe('8.8.4.4')
    // The transport, the kind of traffic and the service, each once.
    expect(
      wrapper.findAll('[data-test="conversation-over"] .v-chip').map((chip) => chip.text()),
    ).toEqual(['TCP', 'DNS', 'domain'])
    // The same word in another case is not said twice.
    const same = await show([
      conversation({ app: 'ssh', server: conversationEnd({ service: 'SSH', port: 22 }) }),
    ])
    expect(
      same.findAll('[data-test="conversation-over"] .v-chip').map((chip) => chip.text()),
    ).toEqual(['TCP', 'SSH'])
    expect(wrapper.find('[data-test="conversation-alerts"]').text().replace(/\s+/g, ' ')).toBe(
      '12 alerts of 2 kinds',
    )
    expect(wrapper.find('[data-test="severity"]').text()).toBe('Medium')
    expect(wrapper.find('[data-test="conversation-programs"]').text()).toBe(
      'Reported by ntopng and OPNsense',
    )
  })

  it('draws how much each side sent and how long it lasted', async () => {
    const wrapper = await show()

    expect(wrapper.find('[data-test="conversation-volume"]').text()).toContain('Sent 399 B')
    expect(wrapper.find('[data-test="conversation-volume"]').text()).toContain('Got back 722 B')
    expect(wrapper.find('[data-test="conversation-duration"]').text()).toBe('Lasted 1 min 1 s')
  })

  it('names what the traffic asked for', async () => {
    const wrapper = await show()

    expect(wrapper.find('[data-test="conversation-names"]').text()).toContain('Name looked up')
    expect(wrapper.find('[data-test="conversation-names"]').text()).toContain('example.com')
  })

  it('says only what is known: no volume, time, names or kind of traffic', async () => {
    const wrapper = await show([
      conversation({
        alerts: 1,
        kinds: 1,
        protocol: null,
        app: null,
        bytes_out: null,
        bytes_in: null,
        duration: null,
        names: [],
        programs: [{ source: 'wazuh', source_name: 'Wazuh' }],
        server: conversationEnd({ address: '203.0.113.9', name: null, port: 4444 }),
      }),
    ])

    expect(wrapper.find('[data-test="conversation-alerts"]').text()).toBe('1 alert')
    expect(wrapper.find('[data-test="conversation-over"]').exists()).toBe(false)
    expect(wrapper.find('[data-test="conversation-volume"]').exists()).toBe(false)
    expect(wrapper.find('[data-test="conversation-duration"]').exists()).toBe(false)
    expect(wrapper.find('[data-test="conversation-names"]').exists()).toBe(false)
    expect(wrapper.find('[data-test="conversations-left"]').exists()).toBe(false)
  })

  it('says how many more there were than are drawn', async () => {
    const one = await show([conversation()], 2)
    const many = await show([conversation()], 9)

    expect(one.find('[data-test="conversations-left"]').text()).toContain(
      'And 1 more conversation,',
    )
    expect(many.find('[data-test="conversations-left"]').text()).toContain(
      'And 8 more conversations,',
    )
  })

  it('says that an address was ruled on, from either end', async () => {
    const wrapper = await show()
    const [client, server] = wrapper.findAllComponents(ConversationEnd)

    client?.vm.$emit('ruled')
    server?.vm.$emit('ruled')

    expect(wrapper.emitted('ruled')).toHaveLength(2)
  })
})
