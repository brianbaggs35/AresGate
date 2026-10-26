import { HeartPulse, LayoutDashboard, Plug, Settings } from '@lucide/vue'
import type { IconProps } from 'vuetify'

/** A place in the menu. */
export interface NavItem {
  /** The name of the route it opens. */
  route: string
  title: string
  icon: NonNullable<IconProps['icon']>
}

/** A phone's bottom bar has room for this many destinations before it gets cramped. */
export const BOTTOM_BAR_LIMIT = 5

/** The menu, in order. A page that should be in it adds itself here. */
export const navItems: readonly NavItem[] = [
  { route: 'home', title: 'Dashboard', icon: LayoutDashboard },
  { route: 'integrations', title: 'Integrations', icon: Plug },
  { route: 'status', title: 'Status', icon: HeartPulse },
  { route: 'settings', title: 'Settings', icon: Settings },
]
