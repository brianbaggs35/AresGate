import type {
  Call,
  Connection,
  ConnectionDefinition,
  Field,
  Integration,
  IntegrationSummary,
  Module,
} from '@/api/integrations'

/** Integrations as the API describes them, for tests of pages that show them. */

export const field = (
  overrides: Partial<Field> & Pick<Field, 'key' | 'label' | 'kind'>,
): Field => ({
  help: '',
  placeholder: '',
  default: null,
  choices: [],
  minimum: 0,
  maximum: 65535,
  only_if: null,
  action: '',
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
    ...overrides,
  }
}

export function summary(overrides: Partial<IntegrationSummary> = {}): IntegrationSummary {
  return {
    key: 'ntopng',
    name: 'ntopng',
    provides: 'Who talks to whom on the network.',
    icon: 'traffic',
    status: 'not_connected',
    last_success_at: null,
    services: [],
    ...overrides,
  }
}

export function integration(overrides: Partial<Integration> = {}): Integration {
  return {
    ...summary(),
    docs_url: 'https://www.ntop.org/guides/ntopng/',
    setup: ['Create a token in ntopng.', 'Paste it here.'],
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
          label: 'Interface',
          kind: 'lookup',
          default: 0,
          help: 'The interface ntopng watches that AresGate reads.',
          maximum: 999,
          action: 'Fetch interfaces',
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
    setup: ['Create an API key under System, Access, Users.'],
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
