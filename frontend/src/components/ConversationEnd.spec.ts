import type { Reputation } from '@/api/incidents'
import * as trustApi from '@/api/trust'
import ConversationEnd from '@/components/ConversationEnd.vue'
import ThreatRulingDialog from '@/components/ThreatRulingDialog.vue'
import { conversationEnd } from '@/test/incidents'
import { flushPromises, mountWithPlugins } from '@/test/mount'
import { trustRule } from '@/test/trust'

async function show(
  changes: Parameters<typeof conversationEnd>[0],
  side: 'client' | 'server' = 'client',
) {
  const { wrapper } = await mountWithPlugins(ConversationEnd, {
    props: { end: conversationEnd(changes), side },
  })
  return wrapper
}

const FLAGGED: Reputation = {
  judgement: 'malicious',
  reported: 'malicious',
  ruling: null,
  ruling_note: null,
  malicious: 3,
  suspicious: 1,
  engines: 84,
  owner: 'Example Hosting',
  country: 'NL',
}

describe('ConversationEnd', () => {
  it('says where a name came from only where it came from a reverse lookup', async () => {
    const looked = await show({ name: 'scanner-17.example.net', name_from: 'dns' }, 'server')
    const told = await show({ name: 'workstation', name_from: 'program' })
    const none = await show({ name: null, name_from: null })

    expect(looked.find('[data-test="end-dns"]').text()).toBe('Name from DNS')
    expect(looked.find('[data-test="end-title"]').text()).toBe('scanner-17.example.net')
    expect(told.find('[data-test="end-dns"]').exists()).toBe(false)
    expect(none.find('[data-test="end-dns"]').exists()).toBe(false)
  })

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
        reported: 'malicious',
        ruling: null,
        ruling_note: null,
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
        reported: 'suspicious',
        ruling: null,
        ruling_note: null,
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

  it('says what the pulses of AlienVault OTX name it in, with a link to read them', async () => {
    const named = await show({
      location: 'remote',
      reputation: {
        ...FLAGGED,
        judgement: 'unknown',
        reported: 'unknown',
        malicious: 0,
        suspicious: 0,
        engines: 0,
        otx: {
          judgement: 'malicious',
          pulses: 3,
          naming: 2,
          names: 'Mirai; Group X',
          link: 'https://otx.alienvault.com/indicator/ip/203.0.113.7',
        },
      },
    })
    const bare = await show({
      location: 'remote',
      reputation: {
        ...FLAGGED,
        judgement: 'unknown',
        reported: 'unknown',
        malicious: 0,
        suspicious: 0,
        engines: 0,
        otx: {
          judgement: 'suspicious',
          pulses: 1,
          naming: 0,
          names: null,
          link: 'https://otx.alienvault.com/indicator/ip/203.0.113.7',
        },
      },
    })

    expect(named.find('[data-test="end-otx"]').text()).toBe('OTX: 3 pulses, Mirai; Group X')
    expect(named.find('[data-test="end-otx"]').attributes('href')).toBe(
      'https://otx.alienvault.com/indicator/ip/203.0.113.7',
    )
    expect(named.find('[data-test="end-client"]').classes()).toContain('end--flagged')
    expect(bare.find('[data-test="end-otx"]').text()).toBe('OTX: 1 pulse')
    expect(bare.find('[data-test="end-client"]').classes()).not.toContain('end--flagged')
  })

  it('says when OTX lists the address as safe, and shows nothing of OTX when it said nothing', async () => {
    const safe = await show({
      location: 'remote',
      reputation: {
        ...FLAGGED,
        otx: {
          judgement: 'clean',
          pulses: 4,
          naming: 0,
          names: null,
          link: 'https://otx.alienvault.com/indicator/ip/203.0.113.7',
        },
      },
    })
    const silent = await show({ location: 'remote', reputation: FLAGGED })

    expect(safe.find('[data-test="end-otx"]').text()).toBe('OTX lists it as safe')
    expect(silent.find('[data-test="end-otx"]').exists()).toBe(false)
  })

  it('says what GreyNoise makes of the address, with a link to read more', async () => {
    const link = 'https://viz.greynoise.io/ip/203.0.113.7'
    const scanner = await show({
      location: 'remote',
      reputation: {
        ...FLAGGED,
        judgement: 'unknown',
        reported: 'unknown',
        malicious: 0,
        suspicious: 0,
        engines: 0,
        greynoise: {
          judgement: 'malicious',
          classification: 'malicious',
          business: null,
          actor: 'Group X',
          tags: 'Mirai, SSH Bruteforcer',
          link,
        },
      },
    })
    const bare = await show({
      location: 'remote',
      reputation: {
        ...FLAGGED,
        judgement: 'unknown',
        reported: 'unknown',
        malicious: 0,
        suspicious: 0,
        engines: 0,
        greynoise: {
          judgement: 'suspicious',
          classification: null,
          business: null,
          actor: null,
          tags: null,
          link,
        },
      },
    })
    const tagged = await show({
      location: 'remote',
      reputation: {
        ...FLAGGED,
        greynoise: {
          judgement: 'suspicious',
          classification: 'unknown',
          business: null,
          actor: null,
          tags: 'Mirai',
          link,
        },
      },
    })

    expect(scanner.find('[data-test="end-greynoise"]').text()).toBe(
      'GreyNoise: scans the internet, malicious (Group X; Mirai, SSH Bruteforcer)',
    )
    expect(scanner.find('[data-test="end-greynoise"]').attributes('href')).toBe(link)
    expect(scanner.find('[data-test="end-client"]').classes()).toContain('end--flagged')
    expect(bare.find('[data-test="end-greynoise"]').text()).toBe('GreyNoise: scans the internet')
    expect(bare.find('[data-test="end-client"]').classes()).not.toContain('end--flagged')
    expect(tagged.find('[data-test="end-greynoise"]').text()).toBe(
      'GreyNoise: scans the internet, unknown (Mirai)',
    )
  })

  it('says when GreyNoise knows the address as a business service, and shows nothing when it said nothing', async () => {
    const service = await show({
      location: 'remote',
      reputation: {
        ...FLAGGED,
        judgement: 'clean',
        reported: 'clean',
        greynoise: {
          judgement: 'clean',
          classification: 'benign',
          business: 'Cloudflare',
          actor: null,
          tags: null,
          link: 'https://viz.greynoise.io/riot/203.0.113.7',
        },
      },
    })
    const silent = await show({ location: 'remote', reputation: FLAGGED })

    expect(service.find('[data-test="end-greynoise"]').text()).toBe(
      'GreyNoise: Cloudflare, a business service',
    )
    expect(silent.find('[data-test="end-greynoise"]').exists()).toBe(false)
  })

  it('is drawn quietly when the service has nothing against it', async () => {
    const clean = await show({
      reputation: {
        judgement: 'clean',
        reported: 'clean',
        ruling: null,
        ruling_note: null,
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
        reported: 'unknown',
        ruling: null,
        ruling_note: null,
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

  it('draws an address the owner ruled safe quietly, with what the service said beside it', async () => {
    const wrapper = await show({
      location: 'remote',
      blacklisted: true,
      reputation: { ...FLAGGED, judgement: 'clean', ruling: 'safe', ruling_note: "A friend's box" },
    })

    expect(wrapper.find('[data-test="end-ruling"]').text()).toBe('You ruled it safe')
    expect(wrapper.find('[data-test="end-reputation"]').text()).toBe('4 of 84 engines flag it')
    expect(wrapper.find('[data-test="end-ruling-note"]').text()).toBe("“A friend's box”")
    expect(wrapper.find('[data-test="end-client"]').classes()).not.toContain('end--flagged')
    // What a program said is still said: it is only not drawn as a warning.
    expect(wrapper.find('[data-test="end-blacklisted"]').exists()).toBe(true)
  })

  it('draws an address the owner ruled suspicious as a warning, though no service flagged it', async () => {
    const wrapper = await show({
      location: 'remote',
      reputation: {
        ...FLAGGED,
        judgement: 'suspicious',
        reported: 'clean',
        ruling: 'suspicious',
        malicious: 0,
        suspicious: 0,
        engines: 90,
      },
    })

    expect(wrapper.find('[data-test="end-ruling"]').text()).toBe('You ruled it suspicious')
    expect(wrapper.find('[data-test="end-reputation"]').text()).toBe('No engine of 90 flags it')
    expect(wrapper.find('[data-test="end-client"]').classes()).toContain('end--flagged')
    expect(wrapper.find('[data-test="end-ruling-note"]').exists()).toBe(false)
  })

  it('says what the owner ruled of an address no service reported on', async () => {
    const wrapper = await show({
      location: 'remote',
      reputation: {
        judgement: 'suspicious',
        reported: 'unknown',
        ruling: 'suspicious',
        ruling_note: null,
        malicious: 0,
        suspicious: 0,
        engines: 0,
        owner: null,
        country: null,
      },
    })

    expect(wrapper.find('[data-test="end-ruling"]').text()).toBe('You ruled it suspicious')
    expect(wrapper.find('[data-test="end-reputation"]').text()).toBe('No report yet')
  })

  it('offers to rule on an address on the internet, and says it when the owner did', async () => {
    const wrapper = await show({ location: 'remote', reputation: FLAGGED })
    const rule = wrapper.find('[data-test="end-rule"]')
    expect(rule.text()).toBe('Rule on it')
    expect(rule.attributes('aria-label')).toBe('Rule on it for 192.168.1.20')
    expect(wrapper.findComponent(ThreatRulingDialog).props('modelValue')).toBe(false)

    await rule.trigger('click')
    await flushPromises()

    const dialog = wrapper.findComponent(ThreatRulingDialog)
    expect(dialog.props('modelValue')).toBe(true)
    expect(dialog.props('subject')).toBe('192.168.1.20')
    expect(dialog.props('ruling')).toBeNull()
    expect(dialog.props('heard')).toBe('VirusTotal said: 4 of 84 engines flag it.')

    dialog.vm.$emit('changed', null)
    expect(wrapper.emitted('ruled')).toHaveLength(1)
  })

  it('offers to change a ruling that was made, which the window starts from', async () => {
    const wrapper = await show({
      location: 'remote',
      reputation: { ...FLAGGED, judgement: 'clean', ruling: 'safe', ruling_note: 'Mine' },
    })

    expect(wrapper.find('[data-test="end-rule"]').text()).toBe('Change my ruling')
    expect(wrapper.find('[data-test="end-rule"]').attributes('aria-label')).toBe(
      'Change my ruling of 192.168.1.20',
    )
    expect(wrapper.findComponent(ThreatRulingDialog).props('ruling')).toEqual({
      verdict: 'safe',
      note: 'Mine',
    })
  })

  it('can be ruled on with nothing said of it by a service', async () => {
    const wrapper = await show({ location: 'remote', reputation: null })

    expect(wrapper.find('[data-test="end-rule"]').exists()).toBe(true)
    expect(wrapper.findComponent(ThreatRulingDialog).props('heard')).toBeNull()
  })

  it('does not offer to rule on a device on your network', async () => {
    const wrapper = await show({})

    expect(wrapper.find('[data-test="end-rule"]').exists()).toBe(false)
    expect(wrapper.findComponent(ThreatRulingDialog).exists()).toBe(false)
  })

  describe('trusting', () => {
    const inDialog = (selector: string) =>
      document.querySelector<HTMLElement>(`[data-test="${selector}"]`)

    async function remote(peer?: ReturnType<typeof conversationEnd>) {
      const mounted = await mountWithPlugins(ConversationEnd, {
        props: {
          end: conversationEnd({ address: '52.1.2.3', location: 'remote', name: null }),
          side: 'server',
          peer,
        },
        signedIn: 'admin',
        withApp: true,
      })
      const button = mounted.wrapper.find('[data-test="trust-button"]')
      return { ...mounted, button }
    }

    it('offers to trust an address on the internet', async () => {
      const { button } = await remote()

      expect(button.attributes('aria-label')).toBe('Trust 52.1.2.3')
    })

    it('does not offer it for a device on your network', async () => {
      const wrapper = await show({})

      expect(wrapper.find('[data-test="trust-button"]').exists()).toBe(false)
    })

    it('offers only the address when the other end is not a device of yours', async () => {
      const { button } = await remote(conversationEnd({ address: '8.8.8.8', location: 'remote' }))
      await button.trigger('click')
      await flushPromises()

      expect(inDialog('scope-address')).not.toBeNull()
      expect(inDialog('scope-traffic')).toBeNull()
    })

    it('offers what the device on your network sent to it, first', async () => {
      const { button } = await remote(conversationEnd({ address: '192.168.1.30', name: 'camera' }))
      await button.trigger('click')
      await flushPromises()

      expect(inDialog('scope-traffic')?.textContent).toContain('Only what camera sends to 52.1.2.3')
    })

    it('says `ruled` once it is trusted, so that the page reads the incident again', async () => {
      vi.spyOn(trustApi, 'trust').mockResolvedValue(trustRule())
      const { button, wrapper } = await remote()
      await button.trigger('click')
      await flushPromises()

      inDialog('trust-save')!.click()
      await flushPromises()
      await flushPromises()

      expect(wrapper.findComponent(ConversationEnd).emitted('ruled')).toHaveLength(1)
    })
  })
})
