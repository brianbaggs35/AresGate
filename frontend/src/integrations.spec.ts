import { Plug } from '@lucide/vue'

import type { Problem } from '@/api/client'
import type { LookupEntry } from '@/api/integrations'
import {
  MODULE_STATE,
  STATUS,
  WHOLE,
  activeFields,
  categoriesOf,
  chosenValues,
  connectionLabels,
  draftFrom,
  fieldId,
  integrationIcon,
  isPlainHttp,
  joinValues,
  lookupItems,
  narrowIntegrations,
  settingsFrom,
  sameFingerprint,
  sortProblems,
  suggestedEntries,
  usesTls,
} from '@/integrations'
import { fingerbank, module, ntopngApi, opnsense, summary, virustotal } from '@/test/integrations'

describe('integrationIcon', () => {
  it('has a picture for each kind', () => {
    const icons = ['firewall', 'traffic', 'alerts', 'threats', 'devices'].map(integrationIcon)
    expect(new Set(icons).size).toBe(5)
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
      options: { auth: 'token', username: '', interface_id: '' },
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

  it('gives a service with one address that address, whether or not it was saved', () => {
    const [api] = virustotal().connections
    expect(draftFrom(api!).url).toBe('https://www.virustotal.com')
    expect(draftFrom({ ...api!, url: 'https://elsewhere.example' }).url).toBe(
      'https://www.virustotal.com',
    )
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
      options: { auth: 'token', interface_id: '' },
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

describe('lookupItems', () => {
  const entries = [
    { value: '0', label: 'eth0', detail: 'live packet capture', quiet: false, loopback: false },
    { value: '1', label: 'LAN (eth1)', detail: '', quiet: true, loopback: false },
  ]

  it('names each choice, with its ID and what else is known of it', () => {
    expect(lookupItems(entries, ['0'])).toEqual([
      { value: '0', title: 'eth0', props: { subtitle: 'ID 0 · live packet capture' } },
      { value: '1', title: 'LAN (eth1)', props: { subtitle: 'ID 1' } },
    ])
  })

  it('still offers a choice that was kept but is not on the list now, and says why', () => {
    expect(lookupItems(entries, ['7'])[0]).toEqual({
      value: '7',
      title: 'ID 7',
      props: { subtitle: 'Saved, but not in the list it gave now' },
    })
  })

  it('offers the choice that was kept before anything has been listed', () => {
    expect(lookupItems([], ['3'])).toEqual([
      { value: '3', title: 'ID 3', props: { subtitle: 'Not looked up yet' } },
    ])
  })

  it('offers nothing when nothing was chosen and nothing is listed', () => {
    expect(lookupItems([], [])).toEqual([])
  })

  it('offers each choice that was kept and has gone, ahead of the list', () => {
    expect(lookupItems(entries, ['1', '7', '9']).map(({ value }) => value)).toEqual([
      '7',
      '9',
      '0',
      '1',
    ])
  })
})

describe('chosenValues and joinValues', () => {
  it('reads the values a lookup field holds, one or several joined by commas', () => {
    expect(chosenValues('')).toEqual([])
    expect(chosenValues('3')).toEqual(['3'])
    expect(chosenValues('0, 1,,10 ')).toEqual(['0', '1', '10'])
  })

  it('keeps them once each, in order of their numbers, so a choice is always saved the same way', () => {
    expect(joinValues(['10', '2', '0', '2'])).toBe('0,2,10')
    expect(joinValues([])).toBe('')
  })
})

describe('suggestedEntries', () => {
  const entry = (value: string, changes: Partial<LookupEntry> = {}): LookupEntry => ({
    value,
    label: `if${value}`,
    detail: '',
    quiet: false,
    loopback: false,
    ...changes,
  })
  const values = (found: LookupEntry[]) => found.map(({ value }) => value)

  it('suggests every one but a loopback, quiet or not, where several can be chosen', () => {
    const listed = [entry('1'), entry('2', { quiet: true }), entry('3', { loopback: true })]
    expect(values(suggestedEntries(listed, true, 16))).toEqual(['1', '2'])
  })

  it('suggests no more than can be chosen', () => {
    const listed = [entry('1'), entry('2'), entry('3')]
    expect(values(suggestedEntries(listed, true, 2))).toEqual(['1', '2'])
  })

  it('suggests the loopback when it is all there is', () => {
    const listed = [entry('3', { loopback: true })]
    expect(values(suggestedEntries(listed, true, 16))).toEqual(['3'])
  })

  it('suggests the first that has seen traffic where one can be chosen, or else the first', () => {
    const quiet = entry('1', { quiet: true })
    expect(values(suggestedEntries([quiet, entry('2'), entry('4')], false, 16))).toEqual(['2'])
    expect(values(suggestedEntries([quiet, entry('2', { quiet: true })], false, 16))).toEqual(['1'])
    expect(values(suggestedEntries([entry('3', { loopback: true }), quiet], false, 16))).toEqual([
      '1',
    ])
  })

  it('suggests nothing when nothing is listed', () => {
    expect(suggestedEntries([], true, 16)).toEqual([])
    expect(suggestedEntries([], false, 16)).toEqual([])
  })
})

describe('categoriesOf', () => {
  it('lists each kind once, in the order it first appears, with how many belong to it', () => {
    const found = categoriesOf([
      summary({ category: 'Threat intelligence' }),
      summary({ category: 'Device intelligence' }),
      summary({ category: 'Threat intelligence' }),
    ])

    expect(found).toEqual([
      { name: 'Threat intelligence', count: 2 },
      { name: 'Device intelligence', count: 1 },
    ])
  })

  it('leaves out an integration that belongs to no kind', () => {
    expect(categoriesOf([summary({ category: '' })])).toEqual([])
    expect(categoriesOf([])).toEqual([])
  })
})

describe('narrowIntegrations', () => {
  const all = [
    summary({
      key: 'opnsense',
      name: 'OPNsense',
      provides: 'The firewall’s health',
      category: 'Network monitoring',
    }),
    summary({
      key: 'virustotal',
      name: 'VirusTotal',
      provides: 'How many vendors flag each address',
      category: 'Threat intelligence',
    }),
    summary({
      key: 'fingerbank',
      name: 'Fingerbank',
      provides: 'What each device is, from its hardware address',
      category: 'Device intelligence',
    }),
  ]
  const keys = (items: { key: string }[]) => items.map((item) => item.key)

  it('keeps them all for an empty search and no kind', () => {
    expect(keys(narrowIntegrations(all, '', ''))).toEqual(['opnsense', 'virustotal', 'fingerbank'])
    expect(keys(narrowIntegrations(all, '   ', ''))).toEqual([
      'opnsense',
      'virustotal',
      'fingerbank',
    ])
  })

  it('keeps those of a kind', () => {
    expect(keys(narrowIntegrations(all, '', 'Device intelligence'))).toEqual(['fingerbank'])
  })

  it('finds a name, what it provides or its kind, whatever the case', () => {
    expect(keys(narrowIntegrations(all, 'VIRUSTOTAL', ''))).toEqual(['virustotal'])
    expect(keys(narrowIntegrations(all, 'firewall', ''))).toEqual(['opnsense'])
    expect(keys(narrowIntegrations(all, 'device intel', ''))).toEqual(['fingerbank'])
  })

  it('needs every word, in any order', () => {
    expect(keys(narrowIntegrations(all, 'address vendors', ''))).toEqual(['virustotal'])
    expect(keys(narrowIntegrations(all, 'address nothing', ''))).toEqual([])
  })

  it('needs the search and the kind together', () => {
    expect(keys(narrowIntegrations(all, 'address', 'Device intelligence'))).toEqual(['fingerbank'])
    expect(keys(narrowIntegrations(all, 'firewall', 'Device intelligence'))).toEqual([])
  })

  it('has a Fingerbank page whose kind is a kind of its own', () => {
    expect(fingerbank().category).toBe('Device intelligence')
  })
})
