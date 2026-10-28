import { defineComponent, reactive, ref } from 'vue'
import type { MockInstance } from 'vitest'
import { VSelect } from 'vuetify/components'

import { ApiError } from '@/api/client'
import * as integrationsApi from '@/api/integrations'
import type { LookupEntry, LookupResult } from '@/api/integrations'
import LookupField from '@/components/LookupField.vue'
import { draftFrom } from '@/integrations'
import { ntopngApi } from '@/test/integrations'
import { flushPromises, mountWithPlugins } from '@/test/mount'

const TOKEN = 'a-security-token'

const wan: LookupEntry = {
  value: '0',
  label: 'eth0',
  detail: 'live packet capture · 41 hosts, 120 flows, 912.3 MB seen',
  quiet: false,
}
const lan: LookupEntry = {
  value: '1',
  label: 'LAN (eth1)',
  detail: 'live packet capture · no traffic seen yet',
  quiet: true,
}
const listed = (entries: LookupEntry[] = [lan, wan]): LookupResult => ({
  ok: true,
  message: `ntopng lists ${entries.length} interfaces.`,
  entries,
})

async function open({
  url = 'http://192.168.1.2:3000',
  saved = false,
  chosen = '0',
  problem,
  help,
}: { url?: string; saved?: boolean; chosen?: string; problem?: string; help?: string } = {}) {
  const connection = ntopngApi()
  const found = connection.definition.fields.find(({ key }) => key === 'interface_id')!
  const field = { ...found, help: help ?? found.help }
  const draft = reactive(draftFrom(connection))
  draft.url = url
  draft.options.interface_id = chosen
  const asked = ref(0)
  const host = defineComponent({
    components: { LookupField },
    setup: () => ({ draft, definition: connection.definition, field, saved, asked, problem }),
    template: `<LookupField v-model="draft.options.interface_id" integration="ntopng"
      :definition="definition" :field="field" :draft="draft" id="api-interface_id" :saved="saved"
      :error-messages="problem" @asked="asked += 1" />`,
  })
  const mounted = await mountWithPlugins(host, { signedIn: 'admin' })
  const find = (selector: string) => mounted.wrapper.find(`[data-test="${selector}"]`)
  const click = async (selector: string) => {
    await find(selector).trigger('click')
    await flushPromises()
  }
  return { ...mounted, draft, asked, find, click }
}

describe('LookupField', () => {
  let lookUp: MockInstance<typeof integrationsApi.lookUpField>

  beforeEach(() => {
    lookUp = vi.spyOn(integrationsApi, 'lookUpField').mockResolvedValue(listed())
  })

  it('shows the choice kept, and says how to get the list', async () => {
    const { wrapper, find } = await open({ chosen: '3' })

    expect(wrapper.text()).toContain('Interface')
    expect(find('lookup-fetch').text()).toBe('Fetch interfaces')
    expect(find('field-interface_id').text()).toContain(
      'The interface ntopng watches that AresGate reads.',
    )
    expect(wrapper.find('input[id]').attributes('id')).toBe('api-interface_id')
    expect(lookUp).not.toHaveBeenCalled()
  })

  it('has no hint when the field has no help to give', async () => {
    const { find } = await open({ help: '' })
    expect(find('field-interface_id').find('.v-messages').text()).toBe('')
  })

  it('cannot ask until there is an address, and says so', async () => {
    const { find } = await open({ url: '  ' })

    expect(find('lookup-fetch').attributes('disabled')).toBeDefined()
    expect(find('lookup-needs-url').text()).toBe('Fill in the address and how to sign in first.')
  })

  it('asks with the address and sign-in filled in so far, and lists what comes back', async () => {
    const { find, click, draft, asked } = await open()
    draft.secrets.token = 'typed-token'

    await click('lookup-fetch')

    expect(lookUp).toHaveBeenCalledOnce()
    const [integration, connection, field, settings, token] = lookUp.mock.calls[0]!
    expect([integration, connection, field, token]).toEqual([
      'ntopng',
      'api',
      'interface_id',
      TOKEN,
    ])
    expect(settings.url).toBe('http://192.168.1.2:3000')
    expect(settings.secrets).toEqual({ token: 'typed-token' })
    expect(find('lookup-message').text()).toBe('ntopng lists 2 interfaces.')
    expect(find('lookup-error').exists()).toBe(false)
    expect(asked.value).toBe(1)
  })

  it('names each interface with its ID and what it holds', async () => {
    const { wrapper, find, click } = await open()
    await click('lookup-fetch')

    await find('lookup-select').find('.v-field').trigger('mousedown')
    await flushPromises()

    const text = document.body.textContent
    expect(text).toContain('LAN (eth1)')
    expect(text).toContain('ID 1 · live packet capture · no traffic seen yet')
    expect(text).toContain('ID 0 · live packet capture · 41 hosts, 120 flows, 912.3 MB seen')
    wrapper.unmount()
  })

  it('shows the name of the interface that is chosen, not just its number', async () => {
    const { find, click } = await open({ chosen: '1', saved: true })
    await click('lookup-fetch')

    expect(find('lookup-select').text()).toContain('LAN (eth1)')
  })

  it('changes the choice', async () => {
    const { wrapper, draft, click } = await open({ saved: true })
    await click('lookup-fetch')
    expect(draft.options.interface_id).toBe('0')

    const select = wrapper.findComponent(VSelect)
    select.vm.$emit('update:modelValue', '1')
    await flushPromises()
    expect(draft.options.interface_id).toBe('1')

    select.vm.$emit('update:modelValue', null)
    await flushPromises()
    expect(draft.options.interface_id).toBe('')
  })

  describe('a connection that is not saved yet', () => {
    it('keeps the choice when the list has it', async () => {
      const { draft, click } = await open({ chosen: '1' })
      await click('lookup-fetch')
      expect(draft.options.interface_id).toBe('1')
    })

    it('chooses the first interface that has seen traffic when the choice is not on the list', async () => {
      const { draft, click } = await open({ chosen: '7' })
      await click('lookup-fetch')
      expect(draft.options.interface_id).toBe('0')
    })

    it('chooses the first one when none has seen anything', async () => {
      lookUp.mockResolvedValue(listed([{ ...lan, value: '4' }]))
      const { draft, click } = await open({ chosen: '7' })
      await click('lookup-fetch')
      expect(draft.options.interface_id).toBe('4')
    })

    it('does not ask when the page opens', async () => {
      await open()
      expect(lookUp).not.toHaveBeenCalled()
    })
  })

  describe('a connection that is saved', () => {
    it('asks when the page opens, so the interfaces are named at once', async () => {
      const { find, asked } = await open({ saved: true })

      expect(lookUp).toHaveBeenCalledOnce()
      expect(find('lookup-message').text()).toBe('ntopng lists 2 interfaces.')
      expect(asked.value).toBe(1)
    })

    it('does not ask without an address', async () => {
      await open({ saved: true, url: '' })
      expect(lookUp).not.toHaveBeenCalled()
    })

    it('does not swap a saved choice that has gone for another one, and says so', async () => {
      const { draft, find } = await open({ saved: true, chosen: '7' })

      expect(draft.options.interface_id).toBe('7')
      expect(find('lookup-gone').text()).toBe(
        "The saved choice (ID 7) isn't on the list REST API gave now. Choose one from it.",
      )
    })

    it('does not make a choice when the list is empty', async () => {
      lookUp.mockResolvedValue({ ok: true, message: 'Nothing listed.', entries: [] })
      const { draft, find } = await open({ saved: true, chosen: '7' })

      expect(draft.options.interface_id).toBe('7')
      expect(find('lookup-gone').exists()).toBe(false)
    })
  })

  describe('an interface that has seen nothing', () => {
    it('is said to be quiet when it is the one chosen', async () => {
      const { find } = await open({ saved: true, chosen: '1' })

      expect(find('lookup-quiet').text()).toBe(
        "LAN (eth1) hasn't seen any traffic yet, so nothing will come in from it until it does. If it isn't the one you mean, choose another.",
      )
    })

    it('is not warned about when another one is chosen', async () => {
      const { find } = await open({ saved: true, chosen: '0' })
      expect(find('lookup-quiet').exists()).toBe(false)
    })
  })

  describe('when it cannot be listed', () => {
    it('says why in the words the system gave, and keeps the choice', async () => {
      lookUp.mockResolvedValue({
        ok: false,
        message: 'ntopng redirected to its login page, so it did not accept the token.',
        entries: [],
      })
      const { draft, find, click } = await open({ chosen: '5' })

      await click('lookup-fetch')

      expect(find('lookup-error').text()).toContain('did not accept the token')
      expect(find('lookup-message').exists()).toBe(false)
      expect(draft.options.interface_id).toBe('5')
    })

    it('says what to fix first, from the API’s reply', async () => {
      lookUp.mockRejectedValue(
        new ApiError(
          422,
          'Fill in the connection first. Authentication token: Enter a value.',
          'invalid',
        ),
      )
      const { find, click } = await open()

      await click('lookup-fetch')

      expect(find('lookup-error').text()).toBe(
        'Fill in the connection first. Authentication token: Enter a value.',
      )
    })

    it('says so when AresGate itself cannot be reached', async () => {
      lookUp.mockRejectedValue(new ApiError(0, "Can't reach AresGate.", 'offline'))
      const { find, click } = await open()

      await click('lookup-fetch')

      expect(find('lookup-error').text()).toBe("Can't reach AresGate.")
    })

    it('clears an earlier failure when it tries again', async () => {
      lookUp.mockRejectedValueOnce(new ApiError(0, 'Offline.', 'offline'))
      const { find, click } = await open()
      await click('lookup-fetch')
      expect(find('lookup-error').exists()).toBe(true)

      await click('lookup-fetch')

      expect(find('lookup-error').exists()).toBe(false)
      expect(find('lookup-message').exists()).toBe(true)
    })

    it('still counts the request, so the log of requests is reloaded', async () => {
      lookUp.mockRejectedValue(new ApiError(0, 'Offline.', 'offline'))
      const { click, asked } = await open()
      await click('lookup-fetch')
      expect(asked.value).toBe(1)
    })
  })

  it('forgets the list when the address changes, since it belongs to the old one', async () => {
    const { find, click, draft } = await open({ saved: true })
    await click('lookup-fetch')
    expect(find('lookup-message').exists()).toBe(true)

    draft.url = 'http://192.168.1.9:3000'
    await flushPromises()

    expect(find('lookup-message').exists()).toBe(false)
    expect(find('lookup-quiet').exists()).toBe(false)
  })

  it('shows what is wrong with the choice itself', async () => {
    const { find } = await open({ problem: 'Enter a whole number from 0 to 999.' })
    expect(find('field-interface_id').text()).toContain('Enter a whole number from 0 to 999.')
  })
})
