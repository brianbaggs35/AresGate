import { addressOf, curlOf, fullAddressOf, queryOf, timings } from '@/apiCall'
import { callDetail } from '@/test/integrations'

describe('apiCall', () => {
  it('writes the address a request went to, with its port only when it is not the usual one', () => {
    expect(addressOf(callDetail())).toBe(
      'https://192.168.1.1:8443/lua/rest/v2/get/ntopng/interfaces.lua',
    )
    expect(addressOf(callDetail({ port: 443, path: '/a' }))).toBe('https://192.168.1.1/a')
    expect(addressOf(callDetail({ scheme: 'http', port: 80, path: '/a' }))).toBe(
      'http://192.168.1.1/a',
    )
    expect(addressOf(callDetail({ scheme: 'http', port: 3000, host: 'fe80::1', path: '/a' }))).toBe(
      'http://[fe80::1]:3000/a',
    )
  })

  it('writes the query, with a credential hidden', () => {
    expect(queryOf(callDetail().query)).toBe('ifid=0&token=***')
    expect(fullAddressOf(callDetail({ path: '/a' }))).toBe(
      'https://192.168.1.1:8443/a?ifid=0&token=***',
    )
    expect(fullAddressOf(callDetail({ path: '/a', query: [] }))).toBe('https://192.168.1.1:8443/a')
  })

  it('makes a curl command with a stand-in where a credential was', () => {
    expect(curlOf('GET', callDetail({ path: '/a' }))).toBe(
      "curl -X GET -H 'accept: application/json' -H 'authorization: <AUTHORIZATION>' 'https://192.168.1.1:8443/a?ifid=0&token=%3CTOKEN%3E'",
    )
  })

  it('leaves out the headers curl makes itself, and quotes what a shell would take apart', () => {
    const command = curlOf(
      'POST',
      callDetail({
        path: '/it',
        query: [{ name: 'q', value: "a'b c" }],
        request_headers: [
          { name: 'Host', value: '192.168.1.1' },
          { name: 'content-length', value: '2' },
          { name: 'x-api-key', value: null },
          { name: 'x-note', value: "it's" },
        ],
      }),
    )
    expect(command).toBe(
      "curl -X POST -H 'x-api-key: <X_API_KEY>' -H 'x-note: it'\\''s' 'https://192.168.1.1:8443/it?q=a'\\''b%20c'",
    )
  })

  it('lists the timings that are known', () => {
    expect(timings(callDetail({ first_byte_ms: 30 }), 42)).toEqual([
      { label: 'Until the answer began', ms: 30 },
      { label: 'Whole request', ms: 42 },
    ])
    expect(timings(callDetail({ first_byte_ms: null }), 42)).toEqual([
      { label: 'Whole request', ms: 42 },
    ])
    const unanswered = callDetail()
    delete unanswered.first_byte_ms
    expect(timings(unanswered, 7)).toEqual([{ label: 'Whole request', ms: 7 }])
  })
})
