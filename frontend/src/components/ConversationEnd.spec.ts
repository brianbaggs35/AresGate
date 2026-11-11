import ConversationEnd from '@/components/ConversationEnd.vue'
import { conversationEnd } from '@/test/incidents'
import { mountWithPlugins } from '@/test/mount'

async function show(
  changes: Parameters<typeof conversationEnd>[0],
  role: 'client' | 'server' = 'client',
) {
  const { wrapper } = await mountWithPlugins(ConversationEnd, {
    props: { end: conversationEnd(changes), role },
  })
  return wrapper
}

describe('ConversationEnd', () => {
  it('names a device on your network by its name, with its address under it', async () => {
    const wrapper = await show({})

    expect(wrapper.find('[data-test="end-role"]').text()).toBe('Sent from')
    expect(wrapper.find('[data-test="end-title"]').text()).toBe('workstation')
    expect(wrapper.find('[data-test="end-address"]').text()).toBe('192.168.1.20')
    expect(wrapper.find('[data-test="end-location"]').text()).toBe('On your network')
    expect(wrapper.find('[data-test="end-client"]').classes()).not.toContain('end--flagged')
  })

  it('names the address when nothing gave a name, and says which end it is', async () => {
    const wrapper = await show({ name: null, address: '8.8.4.4', location: null }, 'server')

    expect(wrapper.find('[data-test="end-role"]').text()).toBe('Sent to')
    expect(wrapper.find('[data-test="end-title"]').text()).toBe('8.8.4.4')
    expect(wrapper.find('[data-test="end-address"]').text()).toBe('')
    // Where the program said nothing, the address says: this one is on the internet.
    expect(wrapper.find('[data-test="end-location"]').text()).toBe('On the internet')
  })

  it('says the port and what it is for after the address', async () => {
    const named = await show({ port: 53, service: 'domain' }, 'server')
    const bare = await show({ name: null, port: 4444, service: null }, 'server')

    expect(named.find('[data-test="end-address"]').text()).toBe('192.168.1.20, port 53 (domain)')
    expect(bare.find('[data-test="end-port"]').text()).toBe('port 4444')
  })

  it('names the country, with its flag for those who see one', async () => {
    const wrapper = await show({ country: 'NL', location: 'remote' })

    const chip = wrapper.find('[data-test="end-country"]')
    expect(chip.text()).toContain('Netherlands')
    expect(chip.find('[aria-hidden="true"]').text()).toBe('🇳🇱')
  })

  it('draws an address that is on a blacklist as a warning and says so in words', async () => {
    const wrapper = await show({ blacklisted: true, location: 'remote' }, 'server')

    expect(wrapper.find('[data-test="end-server"]').classes()).toContain('end--flagged')
    expect(wrapper.find('[data-test="end-blacklisted"]').text()).toBe('On a blacklist')
  })

  it('says what the reputation service made of it and who it belongs to', async () => {
    const flagged = await show({
      location: 'remote',
      reputation: {
        judgement: 'malicious',
        malicious: 3,
        suspicious: 1,
        engines: 84,
        owner: 'Example Hosting',
        country: 'NL',
      },
    })
    const suspicious = await show({
      reputation: {
        judgement: 'suspicious',
        malicious: 0,
        suspicious: 2,
        engines: 70,
        owner: null,
        country: null,
      },
    })

    expect(flagged.find('[data-test="end-reputation"]').text()).toBe('4 of 84 engines flag it')
    expect(flagged.find('[data-test="end-owner"]').text()).toBe('Belongs to Example Hosting')
    expect(flagged.find('[data-test="end-client"]').classes()).toContain('end--flagged')
    expect(suspicious.find('[data-test="end-reputation"]').text()).toBe('2 of 70 engines flag it')
    expect(suspicious.find('[data-test="end-owner"]').exists()).toBe(false)
  })

  it('is drawn quietly when the service has nothing against it', async () => {
    const clean = await show({
      reputation: {
        judgement: 'clean',
        malicious: 0,
        suspicious: 0,
        engines: 90,
        owner: null,
        country: null,
      },
    })
    const unknown = await show({
      reputation: {
        judgement: 'unknown',
        malicious: 0,
        suspicious: 0,
        engines: 0,
        owner: null,
        country: null,
      },
    })

    expect(clean.find('[data-test="end-reputation"]').text()).toBe('No engine of 90 flags it')
    expect(clean.find('[data-test="end-client"]').classes()).not.toContain('end--flagged')
    expect(unknown.find('[data-test="end-reputation"]').text()).toBe('No report yet')
    expect(unknown.find('[data-test="end-client"]').classes()).not.toContain('end--flagged')
  })
})
