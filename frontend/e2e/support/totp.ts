import { createHmac } from 'node:crypto'

const BASE32 = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ234567'
const PERIOD_SECONDS = 30

function decodeBase32(text: string): Buffer {
  let bits = ''
  for (const letter of text.replaceAll('=', ''))
    bits += BASE32.indexOf(letter).toString(2).padStart(5, '0')
  const bytes = bits.match(/.{8}/g) ?? []
  return Buffer.from(bytes.map((byte) => Number.parseInt(byte, 2)))
}

/**
 * The six digits an authenticator app shows for a key, worked out here and not by AresGate, so
 * the tests don't rely on the code they are testing. A code works once, and AresGate accepts the
 * next period's as well, so `periodsAhead: 1` gives a code that is not the one an app was just
 * turned on with, without waiting 30 seconds for it.
 */
export function authenticatorCode(secret: string, periodsAhead = 0): string {
  const counter = Math.floor(Date.now() / 1000 / PERIOD_SECONDS) + periodsAhead
  const message = Buffer.alloc(8)
  message.writeBigUInt64BE(BigInt(counter))
  const digest = createHmac('sha1', decodeBase32(secret)).update(message).digest()
  const offset = digest.readUInt8(digest.length - 1) & 0x0f
  const number = digest.readUInt32BE(offset) & 0x7fffffff
  return String(number % 1_000_000).padStart(6, '0')
}
