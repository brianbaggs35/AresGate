import type { Locator, Page } from '@playwright/test'

export type TlsChoice = 'system' | 'ca' | 'pinned'

/** One integration's page: connecting and managing it, and the log of its requests. */
export class IntegrationPage {
  readonly title: Locator
  readonly status: Locator
  readonly provides: Locator
  readonly lastSuccess: Locator
  readonly docs: Locator
  readonly back: Locator
  /** The setup guide, which opens while nothing is connected. */
  readonly guide: Locator
  readonly guideToggle: Locator
  readonly notice: Locator
  /** Shown instead of the page when it can't be loaded. */
  readonly loadError: Locator
  readonly retry: Locator

  /** What a try at saving or testing says ... */
  readonly report: Locator
  readonly checks: Locator
  readonly failure: Locator
  /** ... and the summary of what needs fixing. */
  readonly problems: Locator

  readonly save: Locator
  readonly test: Locator
  readonly unsaved: Locator
  readonly disconnect: Locator
  readonly confirmation: Locator
  readonly confirmDisconnect: Locator
  readonly cancelDisconnect: Locator

  /** The API log. */
  readonly log: Locator
  readonly logCalls: Locator
  readonly logEmpty: Locator
  readonly logError: Locator
  readonly logRefresh: Locator
  readonly logOlder: Locator
  readonly logClear: Locator

  constructor(private readonly page: Page) {
    this.title = page.getByTestId('page-heading')
    this.status = page.getByTestId('status')
    this.provides = page.getByTestId('page-description')
    this.lastSuccess = page.getByTestId('integration-last-success')
    this.docs = page.getByTestId('docs')
    this.back = page.getByTestId('back')
    this.guide = page.getByTestId('guide')
    this.guideToggle = this.guide.locator('.v-expansion-panel-title')
    this.notice = page.getByTestId('notice')
    this.loadError = page.getByTestId('integration-error')
    this.retry = page.getByTestId('retry')

    this.report = page.getByTestId('report')
    this.checks = page.getByTestId('check')
    this.failure = page.getByTestId('failure')
    this.problems = page.getByTestId('problems')

    this.save = page.getByTestId('save')
    this.test = page.getByTestId('test')
    this.unsaved = page.getByTestId('unsaved')
    this.disconnect = page.getByTestId('disconnect')
    this.confirmation = page.getByTestId('confirm-dialog')
    this.confirmDisconnect = page.getByTestId('confirm-accept')
    this.cancelDisconnect = page.getByTestId('confirm-cancel')

    this.log = page.getByTestId('api-log')
    this.logCalls = page.getByTestId('log-call')
    this.logEmpty = page.getByTestId('log-empty')
    this.logError = page.getByTestId('log-error')
    this.logRefresh = page.getByTestId('log-refresh')
    this.logOlder = page.getByTestId('log-older')
    this.logClear = page.getByTestId('log-clear')
  }

  async goto(key: string): Promise<void> {
    await this.page.goto(`/integrations/${key}`)
  }

  /** The card of one of the integration's connections, such as `api` or `zenarmor`. */
  connection(key: string): Locator {
    return this.page.getByTestId(`connection-${key}`)
  }

  connectionStatus(key: string): Locator {
    return this.connection(key).getByTestId('connection-status')
  }

  /** The switch that adds a connection not everyone has. */
  useConnection(key: string): Locator {
    return this.connection(key).getByTestId('connection-enabled').getByRole('checkbox')
  }

  address(connection: string): Locator {
    return this.connection(connection).getByTestId('connection-url').locator('input')
  }

  /** Where a message about the address, or about a field, is shown. */
  fieldMessages(connection: string, field: string): Locator {
    return this.connection(connection).getByTestId(field).locator('.v-messages')
  }

  addressMessages(connection: string): Locator {
    return this.connection(connection).getByTestId('connection-url').locator('.v-messages')
  }

  plainHttpWarning(connection: string): Locator {
    return this.connection(connection).getByTestId('connection-plain-http')
  }

  /** A text, number or secret field's input. */
  field(connection: string, key: string): Locator {
    return this.connection(connection).getByTestId(`field-${key}`).locator('input')
  }

  lastError(connection: string): Locator {
    return this.connection(connection).getByTestId('connection-last-error')
  }

  /** The certificate: how it is checked ... */
  tlsMode(connection: string, choice: TlsChoice): Locator {
    return this.connection(connection)
      .getByTestId(`tls-${choice === 'system' ? 'system' : choice}`)
      .getByRole('radio')
  }

  authority(connection: string): Locator {
    return this.connection(connection).getByTestId('tls-ca-pem').locator('textarea')
  }

  fingerprint(connection: string): Locator {
    return this.connection(connection).getByTestId('tls-fingerprint').locator('input')
  }

  /** ... and looking it up to pin it. */
  lookUp(connection: string): Locator {
    return this.connection(connection).getByTestId('tls-look-up')
  }

  lookUpError(connection: string): Locator {
    return this.connection(connection).getByTestId('tls-look-up-error')
  }

  found(connection: string): Locator {
    return this.connection(connection).getByTestId('tls-found')
  }

  foundFingerprint(connection: string): Locator {
    return this.connection(connection).getByTestId('tls-found-fingerprint')
  }

  trust(connection: string): Locator {
    return this.connection(connection).getByTestId('tls-trust')
  }

  trusted(connection: string): Locator {
    return this.connection(connection).getByTestId('tls-trusted')
  }

  /** The services on a system, with what testing found of each. */
  modules(connection: string): Locator {
    return this.connection(connection).getByTestId('module')
  }

  module(connection: string, name: string): Locator {
    return this.modules(connection).filter({ hasText: name })
  }

  /** The switch that says whether a service is read. */
  moduleSwitch(connection: string, name: string): Locator {
    return this.module(connection, name).getByRole('checkbox')
  }

  /** The log's filters ... */
  filter(name: 'connection' | 'result' | 'method' | 'period'): Locator {
    return this.log.getByTestId(`filter-${name}`)
  }

  /** ... which are chosen from a list that opens on the page. */
  async chooseFilter(
    name: 'connection' | 'result' | 'method' | 'period',
    option: string,
  ): Promise<void> {
    await this.filter(name).click()
    await this.page.getByRole('option', { name: option, exact: true }).click()
  }
}
