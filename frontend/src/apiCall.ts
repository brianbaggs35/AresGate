import type { CallDetail, CallPair } from '@/api/integrations'

/** Headers curl works out for itself, which a copied command is better without. */
const SELF_MADE = new Set(['host', 'content-length', 'connection'])

/** What stands in a copied command for a value that is a credential, which is never kept. */
const placeholder = (name: string) => `<${name.toUpperCase().replaceAll(/[^A-Z0-9]+/g, '_')}>`

/** A word for a shell, in single quotes, which is all that needs to be safe in them. */
const quoted = (text: string) => `'${text.replaceAll("'", "'\\''")}'`

/** `host:port`, with an address written as IPv6 in brackets. */
function hostPort(detail: CallDetail): string {
  const host = detail.host.includes(':') ? `[${detail.host}]` : detail.host
  const standard = detail.scheme === 'https' ? 443 : 80
  return detail.port === standard ? host : `${host}:${detail.port}`
}

/** The address a request went to, without its query: `https://192.168.1.1:8443/path`. */
export function addressOf(detail: CallDetail): string {
  return `${detail.scheme}://${hostPort(detail)}${detail.path}`
}

/** The query as it was sent, with the value of a credential shown as hidden. */
export function queryOf(pairs: readonly CallPair[]): string {
  return pairs.map(({ name, value }) => `${name}=${value === null ? '***' : value}`).join('&')
}

/** The address with its query, as it can be read: a value that is a credential is `***`. */
export function fullAddressOf(detail: CallDetail): string {
  const query = queryOf(detail.query)
  return query ? `${addressOf(detail)}?${query}` : addressOf(detail)
}

/**
 * The request as a curl command that can be pasted into a terminal. A credential is never kept, so
 * its place is taken by `<NAME>` for the person to fill in. The body of a request is not kept
 * either, so a request that sent one needs it added.
 */
export function curlOf(method: string, detail: CallDetail): string {
  const query = detail.query
    .map(
      ({ name, value }) =>
        `${encodeURIComponent(name)}=${value === null ? encodeURIComponent(placeholder(name)) : encodeURIComponent(value)}`,
    )
    .join('&')
  const address = quoted(query ? `${addressOf(detail)}?${query}` : addressOf(detail))
  const headers = detail.request_headers
    .filter(({ name }) => !SELF_MADE.has(name.toLowerCase()))
    .map(({ name, value }) => `-H ${quoted(`${name}: ${value ?? placeholder(name)}`)}`)
  return ['curl', '-X', method, ...headers, address].join(' ')
}

/** How long each part of a request took, as far as it is known, in the order they happen. */
export function timings(
  detail: CallDetail,
  totalMs: number,
): readonly { label: string; ms: number }[] {
  const first = detail.first_byte_ms
  return first == null
    ? [{ label: 'Whole request', ms: totalMs }]
    : [
        { label: 'Until the answer began', ms: first },
        { label: 'Whole request', ms: totalMs },
      ]
}
