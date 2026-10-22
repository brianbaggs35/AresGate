import { expect, type Locator, type Page } from '@playwright/test'

export type ThemeChoice = 'light' | 'dark' | 'system'

/** What's around every page: the logo, which links home, and the theme switcher. */
export class AppShell {
  readonly logo: Locator
  readonly themeToggle: Locator
  private readonly app: Locator

  constructor(private readonly page: Page) {
    this.logo = page.getByRole('link', { name: 'AresGate' })
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
}
