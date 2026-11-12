import {
  Boxes,
  Cable,
  Camera,
  CircleHelp,
  Gamepad2,
  HardDrive,
  Laptop,
  Lightbulb,
  Monitor,
  Printer,
  Router,
  Server,
  Shield,
  Smartphone,
  Speaker,
  Tablet,
  Tv,
  Wifi,
  Cast,
  MonitorSmartphone,
} from '@lucide/vue'
import type { IconProps } from 'vuetify'

type Icon = NonNullable<IconProps['icon']>

/** The picture of each kind of asset, by the kind's key. A kind this version does not know gets
 * the picture of a device that nothing says what it is. */
const ICONS: Record<string, Icon> = {
  router: Router,
  firewall: Shield,
  modem: Cable,
  switch: Boxes,
  access_point: Wifi,
  server: Server,
  nas: HardDrive,
  computer: Monitor,
  laptop: Laptop,
  phone: Smartphone,
  tablet: Tablet,
  tv: Tv,
  media_player: Cast,
  speaker: Speaker,
  game_console: Gamepad2,
  camera: Camera,
  printer: Printer,
  smart_home: Lightbulb,
  other: CircleHelp,
}

export function kindIcon(kind: string | null | undefined): Icon {
  return (kind ? ICONS[kind] : undefined) ?? MonitorSmartphone
}
