import IncidentWire from '@/components/IncidentWire.vue'
import { wire, wireCertificate, wireRequest } from '@/test/incidents'
import { mountWithPlugins } from '@/test/mount'

async function show(found = wire()) {
  const { wrapper } = await mountWithPlugins(IncidentWire, { props: { wire: found } })
  return wrapper
}

const text = (wrapper: Awaited<ReturnType<typeof show>>, selector: string) =>
  wrapper.find(`[data-test="${selector}"]`).text()

describe('IncidentWire', () => {
  it('says what stands out in plain words, and a certificate that signs itself', async () => {
    const wrapper = await show()

    expect(text(wrapper, 'wire-note')).toContain('self-signed')
    expect(text(wrapper, 'wire-certificate-name')).toBe('cloud.example.net')
    expect(wrapper.find('[data-test="wire-self-signed"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="wire-expired"]').exists()).toBe(false)
    const facts = wrapper.find('[data-test="wire-certificate"]').text()
    expect(facts).toContain('Vouched for byitself')
    expect(facts).toContain('Good until2035-01-01')
    expect(facts).toContain('Shown by203.0.113.9:443')
    expect(facts).toContain('TLS 1.2')
    expect(facts).toContain('4 alerts')
  })

  it('has no notes when none stands out', async () => {
    const wrapper = await show(wire({ notes: [] }))

    expect(wrapper.find('[data-test="wire-notes"]').exists()).toBe(false)
  })

  it('says a certificate that somebody else vouched for, and one that ran out', async () => {
    const wrapper = await show(
      wire({
        certificates: [
          wireCertificate({
            self_signed: false,
            issuer: 'CN=Some CA',
            expired: true,
            subject: null,
            sni: null,
            not_before: null,
            not_after: null,
            version: null,
            alerts: 1,
            serial: null,
            fingerprint: null,
            ja3: null,
            ja3s: 'abc',
            server: null,
          }),
        ],
      }),
    )

    const facts = wrapper.find('[data-test="wire-certificate"]').text()
    expect(text(wrapper, 'wire-certificate-name')).toBe('A server')
    expect(wrapper.find('[data-test="wire-self-signed"]').exists()).toBe(false)
    expect(wrapper.find('[data-test="wire-expired"]').exists()).toBe(true)
    expect(facts).toContain('Vouched for byCN=Some CA')
    expect(facts).toContain('Server fingerprintabc')
    expect(facts).not.toContain('Good from')
    expect(facts).toContain('1 alert')
    expect(facts).not.toContain('1 alerts')
  })

  it('names a certificate by its subject when no name was asked for', async () => {
    const wrapper = await show(wire({ certificates: [wireCertificate({ sni: null })] }))

    expect(text(wrapper, 'wire-certificate-name')).toBe('CN=cloud.example.net')
  })

  it('shows a web request with its headers, and a secret one as hidden', async () => {
    const wrapper = await show(
      wire({
        certificates: [],
        requests: [
          wireRequest({
            response_headers: [{ name: 'Server', value: 'nginx', hidden: false }],
          }),
        ],
      }),
    )

    expect(text(wrapper, 'wire-request-name')).toBe('POST api.example.net/v1/login')
    const request = wrapper.find('[data-test="wire-request"]').text()
    expect(request).toContain('200')
    expect(request).toContain('application/json')
    expect(request).toContain('Software: camera-firmware/2.1')
    expect(wrapper.findAll('[data-test="wire-header"]')).toHaveLength(3)
    expect(wrapper.findAll('[data-test="wire-hidden"]')).toHaveLength(1)
    expect(request).toContain('Hostapi.example.net')
    expect(request).not.toContain('(hidden)')
  })

  it('calls a request by its server where it has no host, and by a word where it has no method', async () => {
    const wrapper = await show(
      wire({
        certificates: [],
        requests: [
          wireRequest({
            method: null,
            host: null,
            url: null,
            status: null,
            content_type: null,
            user_agent: null,
            request_headers: [],
            alerts: 1,
          }),
        ],
      }),
    )

    expect(text(wrapper, 'wire-request-name')).toBe('Request 203.0.113.9:80')

    const nowhere = await show(
      wire({
        certificates: [],
        requests: [wireRequest({ method: 'GET', host: null, server: null, url: '/x' })],
      }),
    )
    expect(text(nowhere, 'wire-request-name')).toBe('GET /x')
    expect(wrapper.find('[data-test="wire-header"]').exists()).toBe(false)
  })

  it('shows the names looked up with what came back', async () => {
    const wrapper = await show(
      wire({
        certificates: [],
        lookups: [
          { name: 'a.example.net', type: 'A', rcode: 'NOERROR', answers: ['192.0.2.1'], alerts: 3 },
          { name: 'gone.example.net', type: null, rcode: 'NXDOMAIN', answers: [], alerts: 1 },
          { name: 'x.example.net', type: null, rcode: null, answers: [], alerts: 1 },
        ],
      }),
    )

    const lines = wrapper.findAll('[data-test="wire-lookup"]').map((each) => each.text())
    expect(lines[0]).toContain('a.example.net → 192.0.2.1')
    expect(lines[0]).toContain('3 alerts')
    expect(lines[1]).toContain('gone.example.net → NXDOMAIN')
    expect(lines[2]).toContain('x.example.net → no answer')
  })

  it('shows what the two ends of ssh run', async () => {
    const wrapper = await show(
      wire({
        certificates: [],
        banners: [
          { client: 'OpenSSH_9', server_software: null, server: '192.0.2.5:22', alerts: 2 },
          { client: null, server_software: 'dropbear', server: null, alerts: 1 },
        ],
      }),
    )

    const banners = wrapper.findAll('[data-test="wire-banner"]').map((each) => each.text())
    expect(banners[0]).toContain('192.0.2.5:22')
    expect(banners[0]).toContain('The client runsOpenSSH_9')
    expect(banners[0]).not.toContain('The server runs')
    expect(banners[1]).toContain('ssh')
    expect(banners[1]).toContain('The server runsdropbear')
  })

  it('shows the start of the packet as text and as bytes', async () => {
    const wrapper = await show(
      wire({
        certificates: [],
        payload: 'GET /admin',
        dump: [{ offset: '0000', hex: '47 45 54', text: 'GET' }],
      }),
    )

    expect(text(wrapper, 'wire-payload')).toBe('GET /admin')
    expect(wrapper.findAll('[data-test="wire-dump-row"]')).toHaveLength(1)
    expect(wrapper.find('[data-test="wire-count"]').exists()).toBe(false)
  })

  it('shows a packet that has bytes and no text, or text and no bytes', async () => {
    const bytes = await show(
      wire({ certificates: [], dump: [{ offset: '0000', hex: '00 01', text: '..' }] }),
    )
    const words = await show(wire({ certificates: [], payload: 'hello' }))

    expect(bytes.find('[data-test="wire-payload"]').exists()).toBe(false)
    expect(bytes.find('[data-test="wire-dump-row"]').exists()).toBe(true)
    expect(words.find('[data-test="wire-payload"]').exists()).toBe(true)
    expect(words.find('[data-test="wire-dump-row"]').exists()).toBe(false)
  })

  it('has a panel for what there is, counted, with the first one open', async () => {
    const wrapper = await show(wire({ requests: [wireRequest(), wireRequest({ url: '/b' })] }))

    expect(wrapper.find('[data-test="wire-panel-certificates"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="wire-panel-requests"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="wire-panel-lookups"]').exists()).toBe(false)
    expect(wrapper.find('[data-test="wire-panel-packet"]').exists()).toBe(false)
    expect(wrapper.findAll('[data-test="wire-count"]').map((each) => each.text())).toEqual([
      '1',
      '2',
    ])
    expect(wrapper.find('[data-test="wire-panel-certificates"]').classes()).toContain(
      'v-expansion-panel--active',
    )
    expect(wrapper.find('[data-test="wire-panel-requests"]').classes()).not.toContain(
      'v-expansion-panel--active',
    )
  })

  it('opens another panel when asked, and leaves the first open', async () => {
    const wrapper = await show(wire({ requests: [wireRequest()] }))

    await wrapper
      .find('[data-test="wire-panel-requests"] .v-expansion-panel-title')
      .trigger('click')

    expect(wrapper.find('[data-test="wire-panel-requests"]').classes()).toContain(
      'v-expansion-panel--active',
    )
    expect(wrapper.find('[data-test="wire-panel-certificates"]').classes()).toContain(
      'v-expansion-panel--active',
    )
  })
})
