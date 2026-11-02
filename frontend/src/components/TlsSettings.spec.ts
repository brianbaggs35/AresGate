import { defineComponent, ref } from 'vue'

import { ApiError } from '@/api/client'
import * as integrationsApi from '@/api/integrations'
import type { TlsMode } from '@/api/integrations'
import TlsSettings from '@/components/TlsSettings.vue'
import { certificateReview } from '@/test/integrations'
import { flushPromises, mountWithPlugins } from '@/test/mount'

const TOKEN = 'a-security-token'
const certificate = certificateReview()

async function open({
  mode = 'system',
  url = 'https://192.168.1.1',
  problems = {},
  note,
  canTest = false,
}: {
  mode?: TlsMode
  url?: string
  problems?: Record<string, string>
  note?: string
  canTest?: boolean
} = {}) {
  const chosen = ref(mode)
  const authority = ref('')
  const fingerprint = ref('')
  const address = ref(url)
  const trusted = vi.fn()
  const settings = ref<{ review: () => Promise<void> } | null>(null)
  const host = defineComponent({
    components: { TlsSettings },
    setup: () => ({
      chosen,
      authority,
      fingerprint,
      address,
      problems,
      note,
      canTest,
      trusted,
      settings,
    }),
    template: `<TlsSettings ref="settings" v-model:mode="chosen" v-model:authority="authority"
      v-model:fingerprint="fingerprint" integration="opnsense" :url="address" id-prefix="api"
      :problems="problems" :note="note" :can-test="canTest" @trusted="trusted" />`,
  })
  const mounted = await mountWithPlugins(host, { signedIn: 'admin' })
  const find = (selector: string) => mounted.wrapper.find(`[data-test="${selector}"]`)
  const click = async (selector: string) => {
    await find(selector).trigger('click')
    await flushPromises()
  }
  return { ...mounted, chosen, authority, fingerprint, address, trusted, settings, find, click }
}

describe('TlsSettings', () => {
  it('offers the three ways, with the certificates the computer trusts first', async () => {
    const { wrapper, find } = await open()
    expect(wrapper.find('fieldset legend').text()).toBe('Certificate')
    expect(find('tls-system').find<HTMLInputElement>('input').element.checked).toBe(true)
    expect(find('tls-ca').find<HTMLInputElement>('input').element.checked).toBe(false)
    expect(find('tls-pinned').find<HTMLInputElement>('input').element.checked).toBe(false)
    expect(find('tls-ca-pem').exists()).toBe(false)
    expect(find('tls-fingerprint').exists()).toBe(false)
  })

  it('says nothing more unless the product has something to add', async () => {
    const { find } = await open()
    expect(find('tls-note').exists()).toBe(false)
  })

  it('shows what the product adds about its certificate beside the choice', async () => {
    const { find } = await open({
      note: 'Its Let’s Encrypt certificate is for the dashboard only.',
    })
    expect(find('tls-note').text()).toBe('Its Let’s Encrypt certificate is for the dashboard only.')
  })

  it('takes a certificate authority that is pasted, and says what is wrong with it', async () => {
    const { find, chosen, authority } = await open({
      mode: 'ca',
      problems: { tls_ca_pem: 'That is not a certificate.' },
    })
    expect(chosen.value).toBe('ca')
    expect(find('tls-ca-pem').text()).toContain('That is not a certificate.')
    await find('tls-ca-pem').find('textarea').setValue('-----BEGIN CERTIFICATE-----')
    expect(authority.value).toBe('-----BEGIN CERTIFICATE-----')
    expect(find('tls-ca-pem').find('textarea').attributes('id')).toBe('api-tls_ca_pem')
  })

  it('switches between the ways', async () => {
    const { find, chosen } = await open()
    await find('tls-pinned').find('input').setValue(true)
    expect(chosen.value).toBe('pinned')
    expect(find('tls-fingerprint').exists()).toBe(true)
    await find('tls-ca').find('input').setValue(true)
    expect(chosen.value).toBe('ca')
    expect(find('tls-fingerprint').exists()).toBe(false)
  })

  it('takes a fingerprint that is typed, and says what is wrong with it', async () => {
    const { find, fingerprint } = await open({
      mode: 'pinned',
      problems: { tls_fingerprint: 'That is not a SHA-256 fingerprint.' },
    })
    expect(find('tls-fingerprint').text()).toContain('That is not a SHA-256 fingerprint.')
    await find('tls-fingerprint').find('input').setValue('aa:bb')
    expect(fingerprint.value).toBe('aa:bb')
  })

  it('shows what is wrong with the choice itself', async () => {
    const { find } = await open({ problems: { tls_mode: 'Choose how to check the certificate.' } })
    expect(find('tls-mode').text()).toContain('Choose how to check the certificate.')
  })

  it('has nothing to look up until there is an address', async () => {
    const { wrapper, find } = await open({ mode: 'pinned', url: '  ' })
    expect(find('tls-look-up').attributes('disabled')).toBeDefined()
    expect(wrapper.text()).toContain('Enter the address first.')
  })

  it('offers the lookup whichever way is chosen', async () => {
    for (const mode of ['system', 'ca', 'pinned'] as const) {
      const { find } = await open({ mode })
      expect(find('tls-look-up').exists()).toBe(true)
      expect(find('tls-look-up').attributes('disabled')).toBeUndefined()
    }
  })

  describe('looking up the certificate', () => {
    it('shows what the device presented, with the SHA-256 to compare', async () => {
      const lookUp = vi.spyOn(integrationsApi, 'lookUpCertificate').mockResolvedValue(certificate)
      const { wrapper, find, click } = await open({ url: ' https://192.168.1.1 ' })

      await click('tls-look-up')

      expect(lookUp).toHaveBeenCalledWith(
        'opnsense',
        'https://192.168.1.1',
        { mode: 'system', authority: '', fingerprint: '' },
        TOKEN,
      )
      expect(find('tls-subject').text()).toBe('CN=fw.home.arpa')
      expect(find('tls-found-fingerprint').text()).toBe('AA:BB:CC:DD')
      expect(find('tls-found').text()).toContain('fw.home.arpa, 192.168.1.1')
      expect(find('tls-found').text()).toContain('The certificate at https://192.168.1.1')
      expect(find('tls-compare').text()).toContain(
        'Check the fingerprint against the one in the device',
      )
      expect(wrapper.text()).not.toContain('Expired')
    })

    it('says whether the way of checking chosen would accept it, and why not', async () => {
      vi.spyOn(integrationsApi, 'lookUpCertificate').mockResolvedValue(certificate)
      const { find, click } = await open()
      await click('tls-look-up')
      expect(find('tls-verdict').text()).toBe(certificate.verdict)
      expect(find('tls-verdict').classes()).not.toContain('review__verdict--good')
    })

    it('has nothing left to ask when the way chosen already accepts it', async () => {
      vi.spyOn(integrationsApi, 'lookUpCertificate').mockResolvedValue(
        certificateReview({ accepted: true, verdict: 'This computer already trusts it.' }),
      )
      const { find, click } = await open()
      await click('tls-look-up')
      expect(find('tls-verdict').text()).toBe('This computer already trusts it.')
      expect(find('tls-verdict').classes()).toContain('review__verdict--good')
      expect(find('tls-trust').exists()).toBe(false)
      expect(find('tls-compare').exists()).toBe(false)
    })

    it('sends how it is set to be checked, to be judged by', async () => {
      const lookUp = vi.spyOn(integrationsApi, 'lookUpCertificate').mockResolvedValue(certificate)
      const { find, click } = await open({ mode: 'ca' })
      await find('tls-ca-pem').find('textarea').setValue('-----BEGIN CERTIFICATE-----')
      await click('tls-look-up')
      expect(lookUp).toHaveBeenCalledWith(
        'opnsense',
        'https://192.168.1.1',
        { mode: 'ca', authority: '-----BEGIN CERTIFICATE-----', fingerprint: '' },
        TOKEN,
      )
    })

    it('trusts it when told to, and then says it is the one trusted', async () => {
      vi.spyOn(integrationsApi, 'lookUpCertificate').mockResolvedValue(certificate)
      const { find, click, fingerprint, chosen, trusted } = await open()
      await click('tls-look-up')
      expect(find('tls-trusted').exists()).toBe(false)

      await click('tls-trust')

      expect(chosen.value).toBe('pinned')
      expect(fingerprint.value).toBe('AA:BB:CC:DD')
      expect(trusted).toHaveBeenCalledWith(false)
      expect(find('tls-trust').exists()).toBe(false)
      expect(find('tls-trusted').text()).toBe('This certificate is the one trusted.')
      // The fingerprint field is there to see it in.
      expect(find('tls-fingerprint').find('input').element.value).toBe('AA:BB:CC:DD')
    })

    it('trusts it and tests, for a connection that is saved', async () => {
      vi.spyOn(integrationsApi, 'lookUpCertificate').mockResolvedValue(certificate)
      const { find, click, fingerprint, trusted, wrapper } = await open({ canTest: true })
      await click('tls-look-up')
      expect(wrapper.text()).toContain('Trust and test saves your changes')

      await click('tls-trust-test')

      expect(fingerprint.value).toBe('AA:BB:CC:DD')
      expect(trusted).toHaveBeenCalledWith(true)
      expect(find('tls-trusted').exists()).toBe(true)
    })

    it('only offers to test where there is a connection to test', async () => {
      vi.spyOn(integrationsApi, 'lookUpCertificate').mockResolvedValue(certificate)
      const { find, click, wrapper } = await open({ canTest: false })
      await click('tls-look-up')
      expect(find('tls-trust-test').exists()).toBe(false)
      expect(wrapper.text()).not.toContain('Trust and test saves')
    })

    it('knows a pinned certificate whichever way its fingerprint is written', async () => {
      vi.spyOn(integrationsApi, 'lookUpCertificate').mockResolvedValue(certificate)
      const { find, click } = await open({ mode: 'pinned' })
      await find('tls-fingerprint').find('input').setValue('aabbccdd')
      await click('tls-look-up')
      expect(find('tls-trusted').exists()).toBe(true)
      expect(find('tls-trust').exists()).toBe(false)
    })

    it('offers to trust the new certificate when a pinned one has changed', async () => {
      vi.spyOn(integrationsApi, 'lookUpCertificate').mockResolvedValue(
        certificateReview({
          verdict: 'The certificate has changed: it isn’t the one you trusted.',
        }),
      )
      const { find, click, fingerprint } = await open({ mode: 'pinned' })
      await find('tls-fingerprint').find('input').setValue('11:22:33:44')
      await click('tls-look-up')
      expect(find('tls-verdict').text()).toContain('The certificate has changed')
      expect(find('tls-trusted').exists()).toBe(false)

      await click('tls-trust')

      expect(fingerprint.value).toBe('AA:BB:CC:DD')
      expect(find('tls-trusted').exists()).toBe(true)
    })

    it('stops judging the certificate once the way of checking is chosen differently', async () => {
      vi.spyOn(integrationsApi, 'lookUpCertificate').mockResolvedValue(certificate)
      const { find, click } = await open()
      await click('tls-look-up')
      expect(find('tls-verdict').exists()).toBe(true)

      await find('tls-ca').find('input').setValue(true)
      expect(find('tls-verdict').exists()).toBe(false)
      expect(find('tls-found').exists()).toBe(true)
      expect(find('tls-trust').exists()).toBe(true)

      // And the same for an authority pasted or a fingerprint typed after the lookup.
      await find('tls-system').find('input').setValue(true)
      expect(find('tls-verdict').exists()).toBe(true)
      await find('tls-ca').find('input').setValue(true)
      await click('tls-look-up')
      expect(find('tls-verdict').exists()).toBe(true)
      await find('tls-ca-pem').find('textarea').setValue('changed')
      expect(find('tls-verdict').exists()).toBe(false)
      await find('tls-pinned').find('input').setValue(true)
      await click('tls-look-up')
      expect(find('tls-verdict').exists()).toBe(true)
      await find('tls-fingerprint').find('input').setValue('11:22')
      expect(find('tls-verdict').exists()).toBe(false)
    })

    it('says when the certificate has expired', async () => {
      vi.spyOn(integrationsApi, 'lookUpCertificate').mockResolvedValue(
        certificateReview({ not_after: '2020-01-01T00:00:00Z' }),
      )
      const { find, click } = await open()
      await click('tls-look-up')
      expect(find('tls-found').text()).toContain('Expired')
    })

    it('leaves out the names when the certificate has none', async () => {
      vi.spyOn(integrationsApi, 'lookUpCertificate').mockResolvedValue(
        certificateReview({ names: [] }),
      )
      const { find, click } = await open()
      await click('tls-look-up')
      expect(find('tls-found').text()).not.toContain('Names')
    })

    it('says why the address could not be looked at, in the API’s words', async () => {
      vi.spyOn(integrationsApi, 'lookUpCertificate').mockRejectedValue(
        new ApiError(422, "AresGate couldn't use that.", 'invalid', [
          { path: ['url'], message: "Couldn't make a secure connection to 192.168.1.1:443." },
        ]),
      )
      const { find, click } = await open()
      await click('tls-look-up')
      expect(find('tls-look-up-error').text()).toBe(
        "Couldn't make a secure connection to 192.168.1.1:443.",
      )
      expect(find('tls-found').exists()).toBe(false)
    })

    it('says why for any other failure too', async () => {
      vi.spyOn(integrationsApi, 'lookUpCertificate').mockRejectedValue(
        new ApiError(0, "Can't reach AresGate.", 'offline'),
      )
      const { find, click } = await open()
      await click('tls-look-up')
      expect(find('tls-look-up-error').text()).toBe("Can't reach AresGate.")
    })

    it('forgets what it found when the address changes', async () => {
      vi.spyOn(integrationsApi, 'lookUpCertificate').mockResolvedValue(certificate)
      const { find, click, address } = await open()
      await click('tls-look-up')
      expect(find('tls-found').exists()).toBe(true)

      address.value = 'https://192.168.1.2'
      await flushPromises()

      expect(find('tls-found').exists()).toBe(false)
    })

    it('clears an earlier failure when it tries again', async () => {
      const lookUp = vi
        .spyOn(integrationsApi, 'lookUpCertificate')
        .mockRejectedValueOnce(new ApiError(0, 'Offline.', 'offline'))
        .mockResolvedValue(certificate)
      const { find, click } = await open()
      await click('tls-look-up')
      expect(find('tls-look-up-error').exists()).toBe(true)
      await click('tls-look-up')
      expect(find('tls-look-up-error').exists()).toBe(false)
      expect(find('tls-found').exists()).toBe(true)
      expect(lookUp).toHaveBeenCalledTimes(2)
    })
  })

  describe('reviewing it from elsewhere on the page', () => {
    it('looks it up and takes the keyboard to it', async () => {
      vi.spyOn(integrationsApi, 'lookUpCertificate').mockResolvedValue(certificate)
      const { find, settings } = await open()
      const scroll = vi.spyOn(Element.prototype, 'scrollIntoView')
      const spy = vi.spyOn(HTMLElement.prototype, 'focus')

      await settings.value?.review()
      await flushPromises()

      expect(find('tls-found').exists()).toBe(true)
      expect(scroll).toHaveBeenCalled()
      expect(
        spy.mock.contexts.some((element) => (element as HTMLElement).dataset.test === 'tls-found'),
      ).toBe(true)
    })
  })
})
