import { expect, type Locator, type Page } from '@playwright/test'

export type ThemeChoice = 'light' | 'dark' | 'system'

/** The places in the menu, by the names of their routes. */
export type Place = 'home' | 'incidents' | 'logs' | 'integrations' | 'status' | 'settings'

/** The places that do not fit in a phone's bottom bar, which has a More button for them. */
const BEHIND_MORE: readonly Place[] = ['status', 'settings']

/**
 * What's around every page: the logo, which links home, the menu (at the side on a computer or
 * tablet, at the bottom on a phone), the page's title and the theme switcher.
 */
export class AppShell {
  readonly logo: Locator
  readonly menu: Locator
  /** The places in the menu. */
  readonly dashboardLink: Locator
  readonly incidentsLink: Locator
  readonly logsLink: Locator
  readonly integrationsLink: Locator
  readonly statusLink: Locator
  readonly settingsLink: Locator
  /** A phone's button for the places that do not fit in the bar, and the sheet it opens. */
  readonly moreButton: Locator
  readonly moreSheet: Locator
  /** The account's button in the bar, which opens the menu with Sign out in it. */
  readonly userMenu: Locator
  readonly signOut: Locator
  /** Why signing out from the menu failed, in a message at the bottom. */
  readonly signOutError: Locator
  /** Shown instead of the page when the API can't be reached to ask who is signed in. */
  readonly startupError: Locator
  readonly startupRetry: Locator
  /** Switches the side menu between labelled and just icons. Not on a phone. */
  readonly menuWidthToggle: Locator
  /** What a place's tooltip says in the icons-only menu, once it is showing. */
  readonly menuTooltip: Locator
  readonly pageTitle: Locator
  readonly skipLink: Locator
  readonly main: Locator
  readonly themeToggle: Locator
  /** The bar's button for the command palette, which a phone has as just an icon. */
  readonly searchButton: Locator
  readonly palette: Locator
  readonly paletteSearch: Locator
  /** The links and buttons the palette lists. */
  readonly paletteRows: Locator
  /** How many it found, which is read out and not shown. */
  readonly paletteCount: Locator
  readonly paletteEmpty: Locator
  private readonly app: Locator

  constructor(private readonly page: Page) {
    this.logo = page.getByRole('link', { name: 'AresGate' })
    this.menu = page.getByRole('navigation', { name: 'Main' })
    this.dashboardLink = page.getByTestId('nav-home')
    this.incidentsLink = page.getByTestId('nav-incidents')
    this.logsLink = page.getByTestId('nav-logs')
    this.integrationsLink = page.getByTestId('nav-integrations')
    this.statusLink = page.getByTestId('nav-status')
    this.settingsLink = page.getByTestId('nav-settings')
    this.moreButton = page.getByTestId('nav-more')
    this.moreSheet = page.getByTestId('more-sheet')
    this.userMenu = page.getByTestId('user-menu')
    this.signOut = page.getByTestId('sign-out')
    this.signOutError = page.getByTestId('sign-out-error')
    this.startupError = page.getByTestId('startup-error')
    this.startupRetry = page.getByTestId('retry')
    this.menuWidthToggle = page.getByTestId('menu-width')
    // Screen readers skip it, as the place's own name says the same, so a role can't find it.
    // Every place has one, and only the one being pointed at is showing.
    this.menuTooltip = page
      .getByTestId('menu-tooltip')
      .locator('.v-overlay__content')
      .filter({ visible: true })
    this.pageTitle = page.getByTestId('page-title')
    this.skipLink = page.getByTestId('skip-link')
    this.main = page.getByRole('main')
    this.themeToggle = page.getByTestId('theme-toggle')
    this.searchButton = page.getByTestId('palette-open')
    this.palette = page.getByTestId('palette')
    this.paletteSearch = page.getByRole('textbox', { name: 'Search for a page or an action' })
    this.paletteRows = this.palette.locator('.palette__row')
    this.paletteCount = page.getByTestId('palette-count')
    this.paletteEmpty = page.getByTestId('palette-empty')
    this.app = page.locator('.v-application')
  }

  /**
   * Opens the command palette with the keys, and waits until the field has the keyboard and the
   * dialog has finished opening: Vuetify asks the field for the keyboard a second time as it
   * does, which would take it back from a key pressed in between.
   */
  async openPaletteWithKeys(): Promise<void> {
    await this.page.keyboard.press('Control+K')
    await expect(this.paletteSearch).toBeFocused()
    await this.page.waitForFunction(() =>
      document
        .getAnimations()
        .every(
          (animation) =>
            animation.playState !== 'running' ||
            animation.effect?.getComputedTiming().iterations === Infinity,
        ),
    )
  }

  /** Takes a command from the palette by typing what it is called and pressing Enter. */
  async chooseCommand(search: string): Promise<void> {
    await this.paletteSearch.fill(search)
    await this.page.keyboard.press('Enter')
  }

  /** Goes to a place in the menu. On a phone, the ones behind More are reached through it. */
  async goTo(place: Place): Promise<void> {
    if (await this.isBehindMore(place)) await this.moreButton.click()
    await this.page.getByTestId(`nav-${place}`).click()
  }

  /** Waits until the menu marks a place as the one that is open: on a phone, More stands for the
   * places behind it. */
  async expectCurrent(place: Place): Promise<void> {
    if (await this.isBehindMore(place)) {
      await expect(this.moreButton).toHaveAttribute('aria-current', 'true')
    } else {
      await expect(this.page.getByTestId(`nav-${place}`)).toHaveAttribute('aria-current', 'page')
    }
  }

  private async isBehindMore(place: Place): Promise<boolean> {
    await expect(this.menu).toBeVisible()
    return BEHIND_MORE.includes(place) && (await this.moreButton.count()) > 0
  }

  /** Signs out from the account's menu in the bar. */
  async signOutFromMenu(): Promise<void> {
    await this.userMenu.click()
    await this.signOut.click()
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
