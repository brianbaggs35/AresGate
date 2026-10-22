import { expect, type Locator, type Page } from '@playwright/test'

export type ThemeChoice = 'light' | 'dark' | 'system'

/**
 * What's around every page: the logo, which links home, the menu (at the side on a computer or
 * tablet, at the bottom on a phone), the page's title and the theme switcher.
 */
export class AppShell {
  readonly logo: Locator
  readonly menu: Locator
  /** The places in the menu. */
  readonly overviewLink: Locator
  /** Switches the side menu between labelled and just icons. Not on a phone. */
  readonly menuWidthToggle: Locator
  /** What a place's tooltip says in the icons-only menu, once it is showing. */
  readonly menuTooltip: Locator
  readonly pageTitle: Locator
  readonly skipLink: Locator
  readonly main: Locator
  readonly themeToggle: Locator
  private readonly app: Locator

  constructor(private readonly page: Page) {
    this.logo = page.getByRole('link', { name: 'AresGate' })
    this.menu = page.getByRole('navigation', { name: 'Main' })
    this.overviewLink = page.getByTestId('nav-home')
    this.menuWidthToggle = page.getByTestId('menu-width')
    // Screen readers skip it, as the place's own name says the same, so a role can't find it.
    this.menuTooltip = page.getByTestId('menu-tooltip').locator('.v-overlay__content')
    this.pageTitle = page.getByTestId('page-title')
    this.skipLink = page.getByTestId('skip-link')
    this.main = page.getByRole('main')
    this.themeToggle = page.getByTestId('theme-toggle')
    this.app = page.locator('.v-application')
  }

  async chooseTheme(choice: ThemeChoice): Promise<void> {
    await this.themeToggle.click()
    await this.page.getByTestId(`theme-${choice}`).click()
  }

  /** Waits until the page is drawn in a theme, as Vuetify marks it on the app's root. */
  async expectTheme(theme: 'light' | 'dark'): Promise<void> {
    await expect(this.app).toHaveClass(new RegExp(`v-theme--${theme}\\b`))
  }

  /** Waits until the side menu has settled at its labelled or icons-only width. */
  async expectMenuWidth(width: 'full' | 'rail'): Promise<void> {
    await expect(this.menuWidthToggle).toHaveAttribute('aria-expanded', String(width === 'full'))
    await expect(this.menu).toHaveClass(
      width === 'rail' ? /v-navigation-drawer--rail/ : /^(?!.*rail)/,
    )
  }
}
