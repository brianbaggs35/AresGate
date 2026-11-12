import type { BlockedCounts, DashboardWindow } from '@/api/dashboard'
import { formatCount } from '@/format'

/** Which way a refused connection was going. */
export type Side = 'inbound' | 'outbound' | 'inside'

export interface SideInfo {
  key: Side
  label: string
  /** What it means, in a sentence that follows the count. */
  meaning: string
  /** The theme colour that draws it. */
  color: string
}

/** The three directions, in the order they are drawn: the internet knocking is the most common and
 * the least worrying, so it is first and calm; a device of yours being turned away is the one to
 * look at. */
export const SIDES: readonly SideInfo[] = [
  {
    key: 'inbound',
    label: 'From the internet',
    meaning: 'strangers knocking on doors that were shut',
    color: 'primary',
  },
  {
    key: 'outbound',
    label: 'Out from your devices',
    meaning: 'your own devices the firewall would not let connect',
    color: 'warning',
  },
  {
    key: 'inside',
    label: 'Between your networks',
    meaning: 'one network of yours reaching another',
    color: 'secondary',
  },
]

/** What share of the blocks that were sorted by direction went one way, from 0 to 1. */
export function shareOfSides(blocked: Pick<BlockedCounts, Side>, side: Side): number {
  const total = blocked.inbound + blocked.outbound + blocked.inside
  return total > 0 ? blocked[side] / total : 0
}

/** The sentence over the card: what the blocks were, and whether any are worth a look. */
export function sidesSummary(blocked: Pick<BlockedCounts, Side>): string {
  const { inbound, outbound, inside } = blocked
  const total = inbound + outbound + inside
  if (total === 0) return 'The firewall refused nothing.'
  const turned = formatCount(outbound)
  if (outbound === 0 && inside === 0) {
    return `All ${formatCount(total)} came from the internet: the firewall doing its job.`
  }
  if (outbound === 0) {
    return `${formatCount(inbound)} came from the internet, the firewall doing its job. None of your devices were turned away.`
  }
  const plural = outbound === 1 ? 'connection' : 'connections'
  return `${formatCount(inbound)} came from the internet, the firewall doing its job. ${turned} ${plural} from your own devices were refused: worth a look if one device keeps trying.`
}

/** The search of the Logs page for the blocks of one device in the window. */
export function deviceQuery(address: string, window: DashboardWindow): string {
  return `kind:firewall severity>=low from:${address} since:${window}`
}

/** The search of the Logs page for the blocks of one port in the window. */
export function portQuery(port: number, window: DashboardWindow): string {
  return `kind:firewall severity>=low port:${port} since:${window}`
}

/** A port as it is written in the list: "22 · SSH", or the number alone. */
export function portLabel(item: { port: number; service: string | null }): string {
  return item.service ? `${item.port} · ${item.service}` : String(item.port)
}

/** How many addresses a device tried to reach, in words. */
export function reachLabel(destinations: number): string {
  if (destinations === 0) return 'to no address the firewall named'
  return `to ${formatCount(destinations)} ${destinations === 1 ? 'address' : 'addresses'}`
}
