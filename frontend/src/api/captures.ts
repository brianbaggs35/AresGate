import { apiPost } from '@/api/client'

/** The most a capture may be asked for, in seconds: what the server allows. */
export const MIN_CAPTURE_SECONDS = 1
export const MAX_CAPTURE_SECONDS = 30

/** One packet ntopng saw going to or from the host. */
export interface CapturedPacket {
  at: string
  source: string
  destination: string
  /** TCP, UDP, ICMP, ARP and so on. */
  protocol: string
  source_port: number | null
  destination_port: number | null
  /** Its size on the wire, in bytes. */
  length: number
  /** The flags of a TCP segment (SYN, ACK PSH), or what an ARP message says. */
  flags: string
  /** The first bytes of what it carried, with what isn't printable shown as dots. */
  preview: string
}

/** What a few seconds of a host's packets said. */
export interface Capture {
  host: string
  seconds: number
  packets: CapturedPacket[]
  /** How many packets there were, of which `packets` lists the first. */
  total: number
  /** Packets that are not IP or ARP, which are counted and not shown. */
  skipped: number
  bytes: number
  /** ntopng sent more than is read, so the end of the capture is missing. */
  cut: boolean
  protocols: { protocol: string; packets: number }[]
  max_packets: number
}

/** Has ntopng listen to the host for a few seconds. Nothing of it is kept. */
export function takeCapture(host: string, seconds: number, csrfToken: string): Promise<Capture> {
  return apiPost<Capture>('/captures', { host, seconds }, csrfToken)
}
