import type {
  Call,
  CertificateReview,
  Connection,
  ConnectionDefinition,
  Field,
  Guide,
  GuidePart,
  GuideStep,
  Integration,
  IntegrationSummary,
  Module,
} from '@/api/integrations'

/** Integrations as the API describes them, for tests of pages that show them. */

export const field = (
  overrides: Partial<Field> & Pick<Field, 'key' | 'label' | 'kind'>,
): Field => ({
  help: '',
  caution: '',
  placeholder: '',
  default: null,
  choices: [],
  minimum: 0,
  maximum: 65535,
  only_if: null,
  action: '',
  multiple: false,
  ...overrides,
})

export const module = (overrides: Partial<Module> & Pick<Module, 'key' | 'label'>): Module => ({
  summary: `What ${overrides.label} gives.`,
  state: null,
  enabled: true,
  ...overrides,
})

export function connection(
  definition: Partial<ConnectionDefinition> & Pick<ConnectionDefinition, 'key' | 'label'>,
  overrides: Partial<Connection> = {},
): Connection {
  return {
    definition: {
      summary: `What ${definition.label} is.`,
      url_example: 'https://192.168.1.1',
      allow_http: false,
      fields: [],
      optional: false,
      certificate_note: '',
      address: '',
      internet: false,
      ...definition,
    },
    url: null,
    tls_mode: 'system',
    tls_ca_pem: null,
    tls_fingerprint: null,
    options: {},
    modules: [],
    secrets_set: [],
    status: 'not_connected',
    last_attempt_at: null,
    last_success_at: null,
    last_error: null,
    certificate_problem: false,
    ...overrides,
  }
}

/** What a lookup of the certificate at an address finds: a device's own, that nothing else
 * vouches for, which the computer's trusted certificates don't accept. */
export function certificateReview(overrides: Partial<CertificateReview> = {}): CertificateReview {
  return {
    fingerprint: 'AA:BB:CC:DD',
    subject: 'CN=fw.home.arpa',
    issuer: 'CN=fw.home.arpa',
    not_before: '2026-01-01T00:00:00Z',
    not_after: '2099-01-01T00:00:00Z',
    names: ['fw.home.arpa', '192.168.1.1'],
    self_signed: true,
    issuers: [],
    accepted: false,
    verdict: "The certificate isn't trusted: it vouches for itself and nobody else does.",
    ...overrides,
  }
}

export function summary(overrides: Partial<IntegrationSummary> = {}): IntegrationSummary {
  return {
    key: 'ntopng',
    name: 'ntopng',
    provides: 'Who talks to whom on the network.',
    icon: 'traffic',
    category: '',
    status: 'not_connected',
    last_success_at: null,
    services: [],
    ...overrides,
  }
}

/** One step of a guide, with nothing beyond its title and what to do. */
export function step(overrides: Partial<GuideStep> = {}): GuideStep {
  return {
    title: 'Create a token',
    detail: 'Create a token in ntopng.',
    menu: [],
    fills: [],
    command: '',
    result: '',
    watch: '',
    inferred: '',
    ...overrides,
  }
}

export function part(overrides: Partial<GuidePart> = {}): GuidePart {
  return {
    title: 'Make a token',
    connection: 'api',
    intro: 'AresGate needs a token.',
    steps: [step()],
    optional: false,
    ...overrides,
  }
}

export function guide(overrides: Partial<Guide> = {}): Guide {
  return {
    parts: [part()],
    sources: [{ title: 'ntopng: authentication', url: 'https://www.ntop.org/guides/ntopng/' }],
    ...overrides,
  }
}

export function integration(overrides: Partial<Integration> = {}): Integration {
  return {
    ...summary(),
    docs_url: 'https://www.ntop.org/guides/ntopng/',
    guide: guide(),
    last_error: null,
    connections: [ntopngApi()],
    ...overrides,
  }
}

/** ntopng's one connection, which chooses between a token and a user name and password. */
export function ntopngApi(overrides: Partial<Connection> = {}): Connection {
  return connection(
    {
      key: 'api',
      label: 'REST API',
      url_example: 'http://192.168.1.2:3000',
      allow_http: true,
      fields: [
        field({
          key: 'auth',
          label: 'Sign in with',
          kind: 'choice',
          default: 'token',
          choices: [
            { value: 'token', label: 'Authentication token' },
            { value: 'basic', label: 'Username and password' },
          ],
        }),
        field({
          key: 'token',
          label: 'Token',
          kind: 'secret',
          only_if: { field: 'auth', value: 'token' },
        }),
        field({
          key: 'username',
          label: 'Username',
          kind: 'text',
          only_if: { field: 'auth', value: 'basic' },
        }),
        field({
          key: 'password',
          label: 'Password',
          kind: 'secret',
          only_if: { field: 'auth', value: 'basic' },
        }),
        field({
          key: 'interface_id',
          label: 'Interfaces',
          kind: 'lookup',
          default: '',
          help: 'The interfaces ntopng watches that AresGate reads (their ifid). Leave it empty to read every one except the loopback.',
          maximum: 999,
          action: 'Fetch interfaces',
          multiple: true,
        }),
      ],
    },
    overrides,
  )
}

/** An OPNsense with its services, and Zenarmor as the connection it may not have. */
export function opnsense(overrides: Partial<Integration> = {}): Integration {
  const services = [
    module({ key: 'firewall', label: 'Firewall and system' }),
    module({ key: 'suricata', label: 'Suricata' }),
    module({ key: 'crowdsec', label: 'CrowdSec' }),
  ]
  return integration({
    key: 'opnsense',
    name: 'OPNsense',
    provides: 'The firewall, and the services that run on it.',
    icon: 'firewall',
    docs_url: 'https://docs.opnsense.org/development/api.html',
    guide: guide({
      parts: [
        part({
          title: 'Make a key for AresGate',
          connection: 'api',
          steps: [step({ title: 'Create the API key', menu: ['System', 'Access', 'Users'] })],
        }),
        part({ title: 'Zenarmor', connection: 'zenarmor', optional: true }),
      ],
    }),
    connections: [
      connection(
        {
          key: 'api',
          label: 'OPNsense API',
          fields: [
            field({ key: 'api_key', label: 'API key', kind: 'secret' }),
            field({ key: 'api_secret', label: 'API secret', kind: 'secret' }),
          ],
        },
        { modules: services },
      ),
      connection({
        key: 'zenarmor',
        label: 'Zenarmor API',
        optional: true,
        url_example: 'https://192.168.1.1:8090',
        fields: [
          field({ key: 'user', label: 'API user', kind: 'text' }),
          field({ key: 'api_key', label: 'API key', kind: 'secret' }),
        ],
      }),
    ],
    ...overrides,
  })
}

/** VirusTotal, which has one address that cannot be changed, and an access level that costs money
 * above the free one. */
export function virustotal(overrides: Partial<Integration> = {}): Integration {
  return integration({
    key: 'virustotal',
    name: 'VirusTotal',
    provides: 'How many security vendors flag each internet address, and who owns it.',
    icon: 'threats',
    category: 'Threat intelligence',
    docs_url: 'https://docs.virustotal.com/reference/overview',
    connections: [
      connection({
        key: 'api',
        label: 'VirusTotal API',
        url_example: 'https://www.virustotal.com',
        address: 'https://www.virustotal.com',
        internet: true,
        fields: [
          field({ key: 'api_key', label: 'API key', kind: 'secret' }),
          field({
            key: 'tier',
            label: 'Access level',
            kind: 'choice',
            default: 'free',
            choices: [
              { value: 'free', label: 'Free public API' },
              { value: 'premium', label: 'Premium API' },
            ],
            caution:
              'Free and premium differ. The free public API must not be used in business workflows, commercial products or services.',
          }),
        ],
      }),
    ],
    ...overrides,
  })
}

export function call(overrides: Partial<Call> = {}): Call {
  return {
    id: 1,
    occurred_at: '2026-03-04T15:30:45Z',
    connection: 'api',
    method: 'GET',
    path: '/lua/rest/v2/get/ntopng/interfaces.lua',
    status_code: 200,
    duration_ms: 42,
    error: null,
    ...overrides,
  }
}
