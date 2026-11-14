import type { Capture, CapturedPacket } from '@/api/captures'

export function packet(changes: Partial<CapturedPacket> = {}): CapturedPacket {
  return {
    at: '2026-11-14T10:00:00Z',
    source: '192.168.1.20',
    destination: '93.184.216.34',
    protocol: 'TCP',
    source_port: 50000,
    destination_port: 80,
    length: 74,
    flags: 'SYN',
    preview: '',
    ...changes,
  }
}

/** A capture of a handshake and a web request, as the server sends one. */
export function capture(changes: Partial<Capture> = {}): Capture {
  return {
    host: '192.168.1.20',
    seconds: 10,
    packets: [
      packet(),
      packet({
        at: '2026-11-14T10:00:00.1Z',
        source: '93.184.216.34',
        destination: '192.168.1.20',
        source_port: 80,
        destination_port: 50000,
        flags: 'ACK SYN',
      }),
      packet({
        at: '2026-11-14T10:00:00.25Z',
        flags: 'ACK PSH',
        length: 120,
        preview: 'GET / HTTP/1.1..',
      }),
    ],
    total: 3,
    skipped: 0,
    bytes: 4096,
    cut: false,
    protocols: [{ protocol: 'TCP', packets: 3 }],
    max_packets: 300,
    ...changes,
  }
}
