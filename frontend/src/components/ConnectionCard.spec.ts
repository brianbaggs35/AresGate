import { defineComponent, reactive } from 'vue'

import type { Connection } from '@/api/integrations'
import ConnectionCard from '@/components/ConnectionCard.vue'
import { WHOLE, draftFrom } from '@/integrations'
import { module, ntopngApi, opnsense } from '@/test/integrations'
import { flushPromises, mountWithPlugins } from '@/test/mount'

async function open(connection: Connection = ntopngApi(), problems: Record<string, string> = {}) {
  const draft = reactive(draftFrom(connection))
  const host = defineComponent({
    components: { ConnectionCard },
    setup: () => ({ connection, draft, problems }),
    template:
      '<ConnectionCard v-model="draft" integration="ntopng" :connection="connection" :problems="problems" />',
  })
  const mounted = await mountWithPlugins(host, { signedIn: 'admin' })
  const find = (selector: string) => mounted.wrapper.find(`[data-test="${selector}"]`)
  const input = (selector: string) => find(selector).find('input')
  return { ...mounted, draft, find, input }
}

const [, zenarmor] = opnsense().connections

describe('ConnectionCard', () => {
  it('names the connection and says what it is', async () => {
    const { wrapper, find } = await open()
    expect(wrapper.find('h2').text()).toBe('REST API')
    expect(find('connection-summary').text()).toBe('What REST API is.')
  })

  it('takes the address, and says where an example of one is', async () => {
    const { find, input, draft } = await open()
    expect(input('connection-url').attributes('placeholder')).toBe('http://192.168.1.2:3000')
    expect(input('connection-url').attributes('id')).toBe('api-url')
    expect(find('connection-url').text()).toContain('with http:// or https:// and the port')
    await input('connection-url').setValue('https://192.168.1.2:3001')
    expect(draft.url).toBe('https://192.168.1.2:3001')
  })

  it('says when only https is accepted', async () => {
    const { find } = await open(opnsense().connections[0])
    expect(find('connection-url').text()).toContain('with https:// and the port')
  })

  it('warns about an address that is plain http, and about nothing else', async () => {
    const { find, input } = await open()
    expect(find('connection-plain-http').exists()).toBe(false)
    await input('connection-url').setValue('http://192.168.1.2:3000')
    expect(find('connection-plain-http').text()).toContain('sent without encryption')
    await input('connection-url').setValue('https://192.168.1.2:3001')
    expect(find('connection-plain-http').exists()).toBe(false)
  })

  describe('the fields', () => {
    it('shows the ones that apply to the way of signing in that is chosen', async () => {
      const { find, draft } = await open()
      expect(find('field-token').exists()).toBe(true)
      expect(find('field-username').exists()).toBe(false)
      expect(find('field-password').exists()).toBe(false)
      expect(find('field-auth').text()).toContain('Authentication token')

      draft.options.auth = 'basic'
      await flushPromises()

      expect(find('field-token').exists()).toBe(false)
      expect(find('field-username').exists()).toBe(true)
      expect(find('field-password').exists()).toBe(true)
    })

    it('changes the way of signing in with the radio buttons', async () => {
      const { find, draft } = await open()
      await find('field-auth').findAll('input')[1]?.setValue(true)
      expect(draft.options.auth).toBe('basic')
    })

    it('takes text, numbers and secrets', async () => {
      const { find, input, draft } = await open(ntopngApi({ options: { auth: 'basic' } }))
      await input('field-username').setValue('reader')
      await input('field-password').setValue('a-password')
      await input('field-interface_id').setValue('3')
      expect(draft.options.username).toBe('reader')
      expect(draft.secrets.password).toBe('a-password')
      expect(draft.options.interface_id).toBe('3')
      expect(input('field-password').attributes('type')).toBe('password')
      expect(input('field-interface_id').attributes('type')).toBe('number')
      expect(input('field-interface_id').attributes('max')).toBe('999')
      expect(input('field-interface_id').attributes('min')).toBe('0')
      expect(find('field-interface_id').text()).toContain('The ifid of the interface to read.')
    })

    it('does not mark a field as a number, or limit it, unless it is one', async () => {
      const { input } = await open(ntopngApi({ options: { auth: 'basic' } }))
      expect(input('field-username').attributes('type')).toBe('text')
      expect(input('field-username').attributes('min')).toBeUndefined()
      expect(input('field-username').attributes('inputmode')).toBeUndefined()
    })

    it('gives each field an id that names its connection, for moving the focus to it', async () => {
      const { input } = await open(ntopngApi({ options: { auth: 'basic' } }))
      expect(input('field-username').attributes('id')).toBe('api-username')
      expect(input('field-password').attributes('id')).toBe('api-password')
    })

    it('says that a secret is saved, without ever having it', async () => {
      const { find, input } = await open(ntopngApi({ url: 'http://x', secrets_set: ['token'] }))
      expect(input('field-token').attributes('placeholder')).toBe('Saved')
      expect(find('field-token').text()).toContain('Leave this empty to keep it')
      expect(input('field-token').element.value).toBe('')
    })

    it('shows a secret that was typed as it is typed', async () => {
      const { input, draft } = await open()
      draft.secrets.token = 'typed-token'
      await flushPromises()
      expect(input('field-token').element.value).toBe('typed-token')
    })
  })

  describe('what is wrong', () => {
    it('is shown at the field it is about', async () => {
      const { find } = await open(ntopngApi({ options: { auth: 'basic' } }), {
        url: 'That address is not on a private network.',
        username: 'Enter a value.',
        password: 'Enter a value.',
        interface_id: 'Enter a whole number from 0 to 999.',
      })
      expect(find('connection-url').text()).toContain('That address is not on a private network.')
      expect(find('field-username').text()).toContain('Enter a value.')
      expect(find('field-password').text()).toContain('Enter a value.')
      expect(find('field-interface_id').text()).toContain('Enter a whole number from 0 to 999.')
    })

    it('is shown for a choice', async () => {
      const { find } = await open(ntopngApi(), { auth: 'Choose one of the options.' })
      expect(find('field-auth').text()).toContain('Choose one of the options.')
    })

    it('is shown for the whole connection', async () => {
      const { find } = await open(ntopngApi(), { [WHOLE]: 'Fill in this connection.' })
      expect(find('connection-problem').text()).toBe('Fill in this connection.')
    })

    it('is not shown when nothing is wrong', async () => {
      const { find } = await open()
      expect(find('connection-problem').exists()).toBe(false)
    })
  })

  describe('how it is', () => {
    it('has no status until it has been saved', async () => {
      const { find } = await open()
      expect(find('connection-status').exists()).toBe(false)
      expect(find('connection-last-error').exists()).toBe(false)
      expect(find('connection-last-success').exists()).toBe(false)
    })

    it('says whether it works, and when it last did', async () => {
      const when = new Date(Date.now() - 3 * 3600 * 1000).toISOString()
      const { find } = await open(
        ntopngApi({ url: 'http://x', status: 'connected', last_success_at: when }),
      )
      expect(find('connection-status').text()).toBe('Connected')
      expect(find('connection-last-success').text()).toBe('Last successful call 3 hours ago')
    })

    it('says why the last test failed', async () => {
      const { find } = await open(
        ntopngApi({
          url: 'http://x',
          status: 'problem',
          last_error: 'ntopng redirected to its login page.',
          last_success_at: new Date().toISOString(),
        }),
      )
      expect(find('connection-status').text()).toBe('Problem')
      expect(find('connection-last-error').text()).toContain('The last test failed')
      expect(find('connection-last-error').text()).toContain('ntopng redirected to its login page.')
      expect(find('connection-last-success').exists()).toBe(false)
    })
  })

  describe('the certificate', () => {
    it('is decided about for an address that is https, or not yet given', async () => {
      const { find, input } = await open()
      expect(find('api-tls').exists()).toBe(true)
      await input('connection-url').setValue('https://192.168.1.2:3001')
      expect(find('api-tls').exists()).toBe(true)
    })

    it('is nothing to decide about for plain http', async () => {
      const { find, input } = await open()
      await input('connection-url').setValue('http://192.168.1.2:3000')
      expect(find('api-tls').exists()).toBe(false)
    })

    it('is chosen, and filled in, on the connection’s form', async () => {
      const { find, draft } = await open(ntopngApi({ url: 'https://192.168.1.2:3001' }))
      await find('tls-ca').find('input').setValue(true)
      expect(draft.tlsMode).toBe('ca')
      await find('tls-ca-pem').find('textarea').setValue('-----BEGIN CERTIFICATE-----')
      expect(draft.tlsCaPem).toBe('-----BEGIN CERTIFICATE-----')
      await find('tls-pinned').find('input').setValue(true)
      expect(draft.tlsMode).toBe('pinned')
      await find('tls-fingerprint').find('input').setValue('AA:BB')
      expect(draft.tlsFingerprint).toBe('AA:BB')
    })

    it('shows what is wrong with it', async () => {
      const { find } = await open(ntopngApi({ tls_mode: 'pinned' }), {
        tls_fingerprint: 'That is not a SHA-256 fingerprint.',
      })
      expect(find('tls-fingerprint').text()).toContain('That is not a SHA-256 fingerprint.')
    })
  })

  describe('the services', () => {
    it('lists them when the connection has any', async () => {
      const { find, draft } = await open(opnsense().connections[0])
      expect(find('modules').exists()).toBe(true)
      await find('modules').findAll('input')[1]?.setValue(false)
      expect(draft.disabledModules).toEqual(['suricata'])
    })

    it('has no list when it has none', async () => {
      const { find } = await open()
      expect(find('modules').exists()).toBe(false)
    })

    it('follows what testing found', async () => {
      const connection = opnsense().connections[0]!
      const { find } = await open({
        ...connection,
        modules: [module({ key: 'suricata', label: 'Suricata', state: 'running' })],
      })
      expect(find('module-state').text()).toBe('Running')
    })
  })

  describe('a connection that not everyone has', () => {
    it('is left out until it is switched on', async () => {
      const { find, draft } = await open(zenarmor)
      expect(draft.enabled).toBe(false)
      expect(find('connection-url').exists()).toBe(false)
      expect(find('connection-forget').exists()).toBe(false)

      await find('connection-enabled').find('input').setValue(true)

      expect(draft.enabled).toBe(true)
      expect(find('connection-url').exists()).toBe(true)
      expect(find('field-user').exists()).toBe(true)
      expect(find('field-api_key').exists()).toBe(true)
    })

    it('says that switching a saved one off forgets it', async () => {
      const { find, draft } = await open({ ...zenarmor!, url: 'https://192.168.1.1:8090' })
      expect(draft.enabled).toBe(true)
      expect(find('connection-forget').exists()).toBe(false)

      await find('connection-enabled').find('input').setValue(false)

      expect(find('connection-forget').text()).toBe('Saving forgets its address and key.')
      expect(find('connection-url').exists()).toBe(false)
    })

    it('has no such switch for a connection everyone needs', async () => {
      const { find } = await open()
      expect(find('connection-enabled').exists()).toBe(false)
    })
  })
})
