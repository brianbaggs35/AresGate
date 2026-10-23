import { Plug } from '@lucide/vue'

import type { Problem } from '@/api/client'
import {
  MODULE_STATE,
  STATUS,
  WHOLE,
  activeFields,
  connectionLabels,
  draftFrom,
  fieldId,
  integrationIcon,
  isPlainHttp,
  settingsFrom,
  sameFingerprint,
  sortProblems,
  usesTls,
} from '@/integrations'
import { module, ntopngApi, opnsense } from '@/test/integrations'

describe('integrationIcon', () => {
  it('has a picture for each kind', () => {
    const icons = ['firewall', 'traffic', 'alerts', 'threats'].map(integrationIcon)
    expect(new Set(icons).size).toBe(4)
    expect(icons).not.toContain(Plug)
  })

  it('has a plug for a kind it does not know', () => {
    expect(integrationIcon('something new')).toBe(Plug)
  })
})

describe('how things look', () => {
  it('has words for every status and service state, not only colours', () => {
    expect(Object.values(STATUS).map(({ label }) => label)).toEqual([
      'Not connected',
      'Not tested yet',
      'Connected',
      'Problem',
    ])
    expect(Object.values(MODULE_STATE).map(({ label }) => label)).toEqual([
      'Running',
      'Stopped',
      'Installed',
      'Not installed',
      'No access',
      'Unknown',
    ])
  })
})

describe('draftFrom', () => {
  it('starts a new connection with the defaults', () => {
    expect(draftFrom(ntopngApi())).toEqual({
      enabled: true,
      url: '',
      tlsMode: 'system',
      tlsCaPem: '',
      tlsFingerprint: '',
      options: { auth: 'token', username: '', interface_id: '0' },
      secrets: {},
      disabledModules: [],
    })
  })

  it('starts from how a connection is saved, without any secret', () => {
    const saved = ntopngApi({
      url: 'https://192.168.1.2:3001',
      tls_mode: 'ca',
      tls_ca_pem: 'PEM',
      tls_fingerprint: null,
      options: { auth: 'basic', username: 'reader', interface_id: 3 },
      secrets_set: ['password'],
    })
    expect(draftFrom(saved)).toMatchObject({
      url: 'https://192.168.1.2:3001',
      tlsMode: 'ca',
      tlsCaPem: 'PEM',
      options: { auth: 'basic', username: 'reader', interface_id: '3' },
      secrets: {},
    })
  })

  it('remembers the services that are switched off', () => {
    const [api] = opnsense().connections
    const draft = draftFrom({
      ...api!,
      modules: [module({ key: 'a', label: 'A' }), module({ key: 'b', label: 'B', enabled: false })],
    })
    expect(draft.disabledModules).toEqual(['b'])
  })

  it('leaves an optional connection out until it has been set up', () => {
    const [api, zenarmor] = opnsense().connections
    expect(draftFrom(api!).enabled).toBe(true)
    expect(draftFrom(zenarmor!).enabled).toBe(false)
    expect(draftFrom({ ...zenarmor!, url: 'https://192.168.1.1:8090' }).enabled).toBe(true)
  })
})

describe('activeFields', () => {
  const { definition } = ntopngApi()

  it('shows the fields for the way of signing in that is chosen', () => {
    expect(activeFields(definition, { auth: 'token' }).map(({ key }) => key)).toEqual([
      'auth',
      'token',
      'interface_id',
    ])
    expect(activeFields(definition, { auth: 'basic' }).map(({ key }) => key)).toEqual([
      'auth',
      'username',
      'password',
      'interface_id',
    ])
  })
})

describe('the address', () => {
  it.each([
    ['http://192.168.1.2:3000', true],
    ['  HTTP://ntopng.home.arpa', true],
    ['https://192.168.1.2', false],
    ['', false],
    ['192.168.1.2', false],
  ])('%j is plain http: %s', (url, plain) => {
    expect(isPlainHttp(url)).toBe(plain)
    expect(usesTls(url)).toBe(!plain)
  })
})

describe('settingsFrom', () => {
  const { definition } = ntopngApi()
  const draft = () => draftFrom(ntopngApi())

  it('sends the options that apply and the secrets that were typed', () => {
    const filled = draft()
    filled.url = '  http://192.168.1.2:3000 '
    filled.options.username = 'ignored while a token is used'
    filled.secrets = { token: 'a-token', password: 'ignored too' }
    expect(settingsFrom(definition, filled)).toEqual({
      url: 'http://192.168.1.2:3000',
      tls_mode: 'system',
      tls_ca_pem: null,
      tls_fingerprint: null,
      options: { auth: 'token', interface_id: '0' },
      disabled_modules: [],
      secrets: { token: 'a-token' },
    })
  })

  it('keeps a secret that was left blank, by not sending it', () => {
    const filled = draft()
    filled.secrets = { token: '   ' }
    expect(settingsFrom(definition, filled).secrets).toEqual({})
    filled.secrets = {}
    expect(settingsFrom(definition, filled).secrets).toEqual({})
  })

  it('sends only the certificate setting that is chosen', () => {
    const filled = draft()
    filled.tlsCaPem = 'PEM'
    filled.tlsFingerprint = ' AA:BB '
    expect(settingsFrom(definition, { ...filled, tlsMode: 'system' })).toMatchObject({
      tls_mode: 'system',
      tls_ca_pem: null,
      tls_fingerprint: null,
    })
    expect(settingsFrom(definition, { ...filled, tlsMode: 'ca' })).toMatchObject({
      tls_mode: 'ca',
      tls_ca_pem: 'PEM',
      tls_fingerprint: null,
    })
    expect(settingsFrom(definition, { ...filled, tlsMode: 'pinned' })).toMatchObject({
      tls_mode: 'pinned',
      tls_ca_pem: null,
      tls_fingerprint: 'AA:BB',
    })
  })

  it('sends the services to leave alone', () => {
    const filled = draft()
    filled.disabledModules = ['suricata']
    expect(settingsFrom(definition, filled).disabled_modules).toEqual(['suricata'])
  })

  it('sends an option that is missing as empty, which the API fills in', () => {
    const filled = draft()
    delete filled.options.interface_id
    expect(settingsFrom(definition, filled).options.interface_id).toBe('')
  })
})

describe('sortProblems', () => {
  const about = (message: string, ...path: string[]): Problem => ({ path, message })

  it('files each problem under its connection and field', () => {
    const sorted = sortProblems([
      about('Not private.', 'connections', 'api', 'url'),
      about('Enter a value.', 'connections', 'api', 'token'),
      about('Fill in this connection.', 'connections', 'zenarmor'),
      about('Not that one.', 'connections', 'api', 'url'),
      about('Too many.', 'connections'),
      about('Wrong shape.', 'extra'),
    ])
    expect(sorted).toEqual({
      fields: {
        api: { url: 'Not private.', token: 'Enter a value.' },
        zenarmor: { [WHOLE]: 'Fill in this connection.' },
      },
      other: ['Too many.', 'Wrong shape.'],
    })
  })

  it('has nothing to report when nothing is wrong', () => {
    expect(sortProblems([])).toEqual({ fields: {}, other: [] })
  })
})

describe('fieldId', () => {
  it('names a field after its connection, so two connections can both have an API key', () => {
    expect(fieldId('zenarmor', 'api_key')).toBe('zenarmor-api_key')
  })
})

describe('sameFingerprint', () => {
  it('compares the digits, however they are written', () => {
    expect(sameFingerprint('AA:BB:0C', 'aabb0c')).toBe(true)
    expect(sameFingerprint('aa bb 0c', 'AA:BB:0C')).toBe(true)
    expect(sameFingerprint('AA:BB:0C', 'AA:BB:0D')).toBe(false)
  })

  it('does not take two empty ones for the same', () => {
    expect(sameFingerprint('', '')).toBe(false)
    expect(sameFingerprint(':', ' ')).toBe(false)
  })
})

describe('connectionLabels', () => {
  it('names each connection by its key', () => {
    expect(connectionLabels(opnsense())).toEqual({
      api: 'OPNsense API',
      zenarmor: 'Zenarmor API',
    })
  })
})
