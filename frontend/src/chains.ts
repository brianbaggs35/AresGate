import { Crosshair, Link2, MonitorSmartphone, PlugZap, Unlink } from '@lucide/vue'
import type { IconProps } from 'vuetify'

import type { Chain, ChainLink, ChainRole } from '@/api/threats'

type Icon = NonNullable<IconProps['icon']>

interface LinkLook {
  label: string
  /** A theme color. */
  color: string
  icon: Icon
  /** What the tie between the steps means, in a sentence. */
  meaning: string
}

/** How a step is tied to the chain. Never only a color: each has its icon and its word. */
export const LINK: Readonly<Record<ChainLink, LinkLook>> = {
  confirmed: {
    label: 'Seen',
    color: 'error',
    icon: Link2,
    meaning: 'What was seen ties it to the attack: the device and the timing, and what it did.',
  },
  inferred: {
    label: 'Inferred',
    color: 'warning',
    icon: Unlink,
    meaning:
      'The device and the timing agree and nothing else does. It may be a coincidence, so it is kept apart from what was seen.',
  },
}

interface RoleLook {
  title: string
  icon: Icon
}

/** What each step of a chain did. */
export const ROLE: Readonly<Record<ChainRole, RoleLook>> = {
  attacker: { title: 'Got in from the internet', icon: Crosshair },
  callout: { title: 'Then the device called out', icon: PlugZap },
}

/** The icon of the device the attack went through. */
export const DEVICE_ICON = MonitorSmartphone

/** What the device is called: its name and address, or the address alone. */
export function deviceTitle(chain: Pick<Chain, 'device' | 'device_name'>): string {
  return chain.device_name ? `${chain.device_name} (${chain.device})` : chain.device
}

/** How sure a chain is, in a sentence. */
export function certainty(chain: Pick<Chain, 'confirmed'>): string {
  return chain.confirmed
    ? 'The device was seen doing what a taken-over device does.'
    : 'The device called out after the attack, which is a guess until something shows more.'
}
