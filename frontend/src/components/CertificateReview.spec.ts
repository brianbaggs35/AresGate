import { defineComponent, ref } from 'vue'

import CertificateReview from '@/components/CertificateReview.vue'
import { certificateReview } from '@/test/integrations'
import { mountWithPlugins } from '@/test/mount'

async function open(
  props: Partial<InstanceType<typeof CertificateReview>['$props']> = {},
  certificate = certificateReview(),
) {
  const trust = vi.fn()
  const panel = ref<{ focus: () => void } | null>(null)
  const host = defineComponent({
    components: { CertificateReview },
    setup: () => ({ certificate, props, trust, panel }),
    template: `<CertificateReview ref="panel" address="https://192.168.1.1" :certificate="certificate"
      :verdict="null" :trusted="false" :can-test="false" v-bind="props" @trust="trust" />`,
  })
  const mounted = await mountWithPlugins(host, { signedIn: 'admin' })
  const find = (selector: string) => mounted.wrapper.find(`[data-test="${selector}"]`)
  return { ...mounted, trust, panel, find }
}

describe('CertificateReview', () => {
  it('is named for where the certificate was found', async () => {
    const { wrapper, find } = await open()
    const heading = wrapper.find('h4')
    expect(heading.text()).toBe('The certificate at https://192.168.1.1')
    expect(find('tls-found').attributes('aria-labelledby')).toBe(heading.attributes('id'))
  })

  it('says whose it is, how long it is good for and its fingerprint', async () => {
    const { find } = await open()
    const text = find('tls-found').text()
    expect(text).toContain('CN=fw.home.arpa')
    expect(text).toContain('fw.home.arpa, 192.168.1.1')
    expect(text).toContain(' to ')
    expect(find('tls-found-fingerprint').text()).toBe('AA:BB:CC:DD')
  })

  it('says when the certificate vouches for itself, and when it does not', async () => {
    const own = await open()
    expect(own.find('tls-self-signed').text()).toBe('Self-signed')
    const issued = await open({}, certificateReview({ self_signed: false }))
    expect(issued.find('tls-self-signed').exists()).toBe(false)
  })

  it('says when it has expired, or is not valid yet, and neither otherwise', async () => {
    const expired = await open({}, certificateReview({ not_after: '2020-01-01T00:00:00Z' }))
    expect(expired.find('tls-expired').text()).toBe('Expired')
    const early = await open({}, certificateReview({ not_before: '2099-01-01T00:00:00Z' }))
    expect(early.find('tls-found').text()).toContain('Not valid yet')
    expect(early.find('tls-expired').exists()).toBe(false)
    const fine = await open()
    expect(fine.find('tls-found').text()).not.toMatch(/Expired|Not valid yet/)
  })

  it('lists the others the device sent with it', async () => {
    const { find } = await open(
      {},
      certificateReview({
        issuers: [
          {
            ...certificateReview(),
            subject: 'CN=Test Intermediate',
            issuer: 'CN=Test Root',
            fingerprint: '11:22',
            self_signed: false,
          },
          {
            ...certificateReview(),
            subject: 'CN=Test Root',
            issuer: 'CN=Test Root',
            fingerprint: '33:44',
          },
        ],
      }),
    )
    const also = find('tls-issuers').text()
    expect(also).toContain('Also sent 2 more certificates, which vouch for it')
    expect(also).toContain('CN=Test Intermediate')
    expect(also).toContain('Issued by CN=Test Root, good until')
    expect(also).toContain('Issued by CN=Test Root (itself)')
    expect(also).toContain('33:44')
  })

  it('says certificate, not certificates, for one more', async () => {
    const { find } = await open({}, certificateReview({ issuers: [certificateReview()] }))
    expect(find('tls-issuers').text()).toContain('Also sent 1 more certificate, which')
  })

  it('has no list where it was sent alone', async () => {
    const { find } = await open()
    expect(find('tls-issuers').exists()).toBe(false)
  })

  describe('what the way of checking makes of it', () => {
    it('says nothing if it was chosen differently since', async () => {
      const { find } = await open({ verdict: null })
      expect(find('tls-verdict').exists()).toBe(false)
      expect(find('tls-trust').exists()).toBe(true)
    })

    it('says why it is not accepted, and asks for a decision', async () => {
      const { find } = await open({ verdict: { accepted: false, text: 'It vouches for itself.' } })
      expect(find('tls-verdict').text()).toBe('It vouches for itself.')
      expect(find('tls-compare').exists()).toBe(true)
      expect(find('tls-trust').text()).toBe('Trust this certificate')
    })

    it('says it is accepted, and asks for nothing', async () => {
      const { find } = await open({ verdict: { accepted: true, text: 'This computer trusts it.' } })
      expect(find('tls-verdict').text()).toBe('This computer trusts it.')
      expect(find('tls-compare').exists()).toBe(false)
      expect(find('tls-trust').exists()).toBe(false)
    })

    it('says it is the one trusted, and that nothing else is accepted', async () => {
      const { find } = await open({ trusted: true, verdict: { accepted: false, text: 'Old.' } })
      expect(find('tls-trusted').text()).toBe('This certificate is the one trusted.')
      expect(find('tls-verdict').exists()).toBe(false)
      expect(find('tls-found').text()).toContain('Nothing else is accepted for this connection')
      expect(find('tls-trust').exists()).toBe(false)
    })
  })

  describe('trusting it', () => {
    it('is one button where the connection is not saved yet', async () => {
      const { find, trust } = await open()
      expect(find('tls-trust-test').exists()).toBe(false)
      await find('tls-trust').trigger('click')
      expect(trust).toHaveBeenCalledWith(false)
    })

    it('is that, or that and a test, where it is', async () => {
      const { find, trust } = await open({ canTest: true })
      await find('tls-trust').trigger('click')
      expect(trust).toHaveBeenLastCalledWith(false)
      await find('tls-trust-test').trigger('click')
      expect(trust).toHaveBeenLastCalledWith(true)
      expect(find('tls-trust-test').text()).toBe('Trust and test')
    })
  })

  it('takes the keyboard to itself and brings itself into view', async () => {
    const { find, panel } = await open()
    const scroll = vi.fn()
    const element = find('tls-found').element as HTMLElement
    element.scrollIntoView = scroll
    const focus = vi.spyOn(element, 'focus')

    panel.value?.focus()

    expect(focus).toHaveBeenCalled()
    expect(scroll).toHaveBeenCalledWith({ block: 'nearest' })
  })
})
