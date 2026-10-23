import { defineComponent, ref } from 'vue'

import { ApiError } from '@/api/client'
import * as integrationsApi from '@/api/integrations'
import type { Certificate, TlsMode } from '@/api/integrations'
import TlsSettings from '@/components/TlsSettings.vue'
import { flushPromises, mountWithPlugins } from '@/test/mount'

const TOKEN = 'a-security-token'
const certificate: Certificate = {
  fingerprint: 'AA:BB:CC:DD',
  subject: 'CN=fw.home.arpa',
  issuer: 'CN=fw.home.arpa',
  not_before: '2026-01-01T00:00:00Z',
  not_after: '2099-01-01T00:00:00Z',
  names: ['fw.home.arpa', '192.168.1.1'],
}

async function open({
  mode = 'system',
  url = 'https://192.168.1.1',
  problems = {},
}: { mode?: TlsMode; url?: string; problems?: Record<string, string> } = {}) {
  const chosen = ref(mode)
  const authority = ref('')
  const fingerprint = ref('')
  const address = ref(url)
  const host = defineComponent({
    components: { TlsSettings },
    setup: () => ({ chosen, authority, fingerprint, address, problems }),
    template: `<TlsSettings v-model:mode="chosen" v-model:authority="authority"
      v-model:fingerprint="fingerprint" integration="opnsense" :url="address" id-prefix="api"
      :problems="problems" />`,
  })
  const mounted = await mountWithPlugins(host, { signedIn: 'admin' })
  const find = (selector: string) => mounted.wrapper.find(`[data-test="${selector}"]`)
  const click = async (selector: string) => {
    await find(selector).trigger('click')
    await flushPromises()
  }
  return { ...mounted, chosen, authority, fingerprint, address, find, click }
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

  describe('looking up the certificate', () => {
    it('shows what the device presented, with the SHA-256 to compare', async () => {
      const lookUp = vi.spyOn(integrationsApi, 'lookUpCertificate').mockResolvedValue(certificate)
      const { wrapper, find, click } = await open({ mode: 'pinned', url: ' https://192.168.1.1 ' })

      await click('tls-look-up')

      expect(lookUp).toHaveBeenCalledWith('opnsense', 'https://192.168.1.1', TOKEN)
      expect(find('tls-subject').text()).toBe('CN=fw.home.arpa')
      expect(find('tls-found-fingerprint').text()).toBe('AA:BB:CC:DD')
      expect(find('tls-found').text()).toContain('fw.home.arpa, 192.168.1.1')
      expect(find('tls-found').text()).toContain(
        'Check the fingerprint against the one in the device',
      )
      expect(wrapper.text()).not.toContain('Expired')
    })

    it('trusts it when told to, and then says it is the one trusted', async () => {
      vi.spyOn(integrationsApi, 'lookUpCertificate').mockResolvedValue(certificate)
      const { find, click, fingerprint, chosen } = await open({ mode: 'pinned' })
      await click('tls-look-up')
      expect(find('tls-trusted').exists()).toBe(false)

      await click('tls-trust')

      expect(chosen.value).toBe('pinned')
      expect(fingerprint.value).toBe('AA:BB:CC:DD')
      expect(find('tls-trust').exists()).toBe(false)
      expect(find('tls-trusted').text()).toBe('This certificate is the one trusted.')
    })

    it('knows a pinned certificate whichever way its fingerprint is written', async () => {
      vi.spyOn(integrationsApi, 'lookUpCertificate').mockResolvedValue(certificate)
      const { find, click } = await open({ mode: 'pinned' })
      await find('tls-fingerprint').find('input').setValue('aabbccdd')
      await click('tls-look-up')
      expect(find('tls-trusted').exists()).toBe(true)
    })

    it('says when the certificate has expired', async () => {
      vi.spyOn(integrationsApi, 'lookUpCertificate').mockResolvedValue({
        ...certificate,
        not_after: '2020-01-01T00:00:00Z',
      })
      const { find, click } = await open({ mode: 'pinned' })
      await click('tls-look-up')
      expect(find('tls-found').text()).toContain('Expired')
    })

    it('leaves out the names when the certificate has none', async () => {
      vi.spyOn(integrationsApi, 'lookUpCertificate').mockResolvedValue({
        ...certificate,
        names: [],
      })
      const { find, click } = await open({ mode: 'pinned' })
      await click('tls-look-up')
      expect(find('tls-found').text()).not.toContain('Names')
    })

    it('says why the address could not be looked at, in the API’s words', async () => {
      vi.spyOn(integrationsApi, 'lookUpCertificate').mockRejectedValue(
        new ApiError(422, "AresGate couldn't use that.", 'invalid', [
          { path: ['url'], message: "Couldn't make a secure connection to 192.168.1.1:443." },
        ]),
      )
      const { find, click } = await open({ mode: 'pinned' })
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
      const { find, click } = await open({ mode: 'pinned' })
      await click('tls-look-up')
      expect(find('tls-look-up-error').text()).toBe("Can't reach AresGate.")
    })

    it('forgets what it found when the address changes', async () => {
      vi.spyOn(integrationsApi, 'lookUpCertificate').mockResolvedValue(certificate)
      const { find, click, address } = await open({ mode: 'pinned' })
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
      const { find, click } = await open({ mode: 'pinned' })
      await click('tls-look-up')
      expect(find('tls-look-up-error').exists()).toBe(true)
      await click('tls-look-up')
      expect(find('tls-look-up-error').exists()).toBe(false)
      expect(find('tls-found').exists()).toBe(true)
      expect(lookUp).toHaveBeenCalledTimes(2)
    })
  })
})
