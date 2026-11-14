import type { Locator, Page } from '@playwright/test'

/** The groups the incidents are put in. */
export type ResponseGroupKey =
  'needs_response' | 'banned' | 'blocked' | 'ban_ended' | 'closed' | 'no_address'

/** The Incident Response page: what was done about the incidents of the last few days. */
export class IncidentResponsePage {
  readonly heading: Locator
  /** The sentence at the top, and what it says underneath. */
  readonly hero: Locator
  readonly heroTitle: Locator
  readonly heroDetail: Locator
  /** The chips that count each group that has something in it. */
  readonly counts: Locator
  /** Every incident listed, whichever group it is in. */
  readonly rows: Locator
  /** What is said when CrowdSec or OPNsense isn't connected, with the way to connect it. */
  readonly coverage: Locator
  readonly connect: Locator
  readonly scope: Locator
  readonly capped: Locator
  readonly refresh: Locator
  readonly error: Locator
  readonly retry: Locator
  readonly stale: Locator
  readonly noneWaiting: Locator

  constructor(private readonly page: Page) {
    this.heading = page.getByTestId('page-heading')
    this.hero = page.getByTestId('response-hero')
    this.heroTitle = page.getByTestId('response-hero-title')
    this.heroDetail = page.getByTestId('response-hero-detail')
    this.counts = page.locator('[data-test^="count-"]')
    this.rows = page.getByTestId('response-row')
    this.coverage = page.getByTestId('response-coverage')
    this.connect = page.getByTestId('response-connect')
    this.scope = page.getByTestId('response-scope')
    this.capped = page.getByTestId('response-capped')
    this.refresh = page.getByTestId('refresh')
    this.error = page.getByTestId('response-error')
    this.retry = page.getByTestId('retry')
    this.stale = page.getByTestId('response-stale')
    this.noneWaiting = page.getByTestId('response-none-waiting')
  }

  async goto(): Promise<void> {
    await this.page.goto('/incident-response')
  }

  /** One of the groups the incidents are put in. */
  group(key: ResponseGroupKey): Locator {
    return this.page.getByTestId(`group-${key}`)
  }

  /** The incidents in a group. */
  rowsIn(key: ResponseGroupKey): Locator {
    return this.group(key).getByTestId('response-row')
  }

  /** The row of the incident with this in its title. */
  row(text: string): Locator {
    return this.rows.filter({ hasText: text })
  }

  /** A chip that counts a group. */
  count(key: ResponseGroupKey): Locator {
    return this.page.getByTestId(`count-${key}`)
  }

  /** The button that lists the rest of a group. */
  more(key: ResponseGroupKey): Locator {
    return this.page.getByTestId(`more-${key}`)
  }

  /** Chooses how far back to look. */
  range(key: '24h' | '7d' | '30d'): Locator {
    return this.page.getByTestId(`range-${key}`)
  }
}
