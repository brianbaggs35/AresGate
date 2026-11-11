import {
  LEVEL,
  LEVELS,
  appliedText,
  fieldsOf,
  isAddress,
  problemWith,
  requestOf,
  scopesFor,
  type TrustFields,
} from '@/trust'

import { trustRule } from '@/test/trust'

const EMPTY: TrustFields = {
  verdict: 'not_suspicious',
  address: '',
  destination: '',
  source: '',
  signature: '',
  note: '',
}

describe('trust', () => {
  it('has words, an icon and a color for each level, so that color is never alone', () => {
    expect(LEVELS).toEqual(['not_suspicious', 'low_priority'])
    expect(LEVEL.not_suspicious.label).toBe('Safe')
    expect(LEVEL.low_priority.label).toBe('Low priority')
    for (const level of LEVELS) {
      expect(LEVEL[level].icon).toBeTruthy()
      expect(LEVEL[level].meaning).not.toBe('')
    }
  })

  describe('scopesFor', () => {
    it('offers only the whole address when nothing more is known', () => {
      const scopes = scopesFor({ address: '52.1.2.3' })

      expect(scopes.map(({ key }) => key)).toEqual(['address'])
      expect(scopes[0]?.request).toEqual({ address: '52.1.2.3' })
    })

    it('offers the narrowest first: what the device sent, then the alert, then everything', () => {
      const scopes = scopesFor({
        address: '52.1.2.3',
        device: { address: '192.168.1.30', name: 'Blink camera' },
        signature: 'ET POLICY Odd call',
      })

      expect(scopes.map(({ key }) => key)).toEqual(['traffic', 'alert', 'address'])
      expect(scopes[0]?.label).toBe('Only what Blink camera sends to 52.1.2.3')
      expect(scopes[0]?.request).toEqual({ address: '192.168.1.30', destination: '52.1.2.3' })
      expect(scopes[1]?.request).toEqual({ address: '52.1.2.3', signature: 'ET POLICY Odd call' })
      expect(scopes[2]?.label).toBe('Everything about 52.1.2.3')
    })

    it('names a device that has no name by its address', () => {
      const scopes = scopesFor({ address: '52.1.2.3', device: { address: '192.168.1.30' } })

      expect(scopes[0]?.label).toBe('Only what 192.168.1.30 sends to 52.1.2.3')
    })
  })

  describe('appliedText', () => {
    it('says nothing has been kept quiet yet', () => {
      expect(appliedText({ hits: 0, incidents: 0 })).toBe('Not applied to anything yet')
    })

    it('says one alert in one incident in the singular', () => {
      expect(appliedText({ hits: 1, incidents: 1 })).toBe(
        'Kept 1 alert in 1 incident from raising an alarm',
      )
    })

    it('says many in the plural', () => {
      expect(appliedText({ hits: 12, incidents: 2 })).toBe(
        'Kept 12 alerts in 2 incidents from raising an alarm',
      )
    })
  })

  describe('the form', () => {
    it('starts empty and safe for a new decision', () => {
      expect(fieldsOf(null)).toEqual(EMPTY)
    })

    it('starts from what a decision says, with what is not set as empty text', () => {
      const rule = trustRule({ destination: '52.0.0.0/8', source: 'wazuh', note: 'camera' })

      expect(fieldsOf(rule)).toEqual({
        verdict: 'not_suspicious',
        address: '52.1.2.3',
        destination: '52.0.0.0/8',
        source: 'wazuh',
        signature: '',
        note: 'camera',
      })
    })

    it('sends what was typed trimmed, leaves out what is empty and always sends the note', () => {
      expect(
        requestOf({ ...EMPTY, verdict: 'low_priority', address: ' 52.1.2.3 ', note: '  ' }),
      ).toEqual({ verdict: 'low_priority', address: '52.1.2.3', note: '' })
      expect(
        requestOf({ ...EMPTY, source: 'wazuh', signature: ' ET SCAN ', destination: '10.0.0.0/8' }),
      ).toEqual({
        verdict: 'not_suspicious',
        note: '',
        source: 'wazuh',
        signature: 'ET SCAN',
        destination: '10.0.0.0/8',
      })
    })

    it('asks for something to be named', () => {
      expect(problemWith(EMPTY)).toBe('Say what to trust: an address, a program or an alert.')
      expect(problemWith({ ...EMPTY, address: '  ' })).not.toBeNull()
    })

    it('accepts a program or an alert on its own', () => {
      expect(problemWith({ ...EMPTY, source: 'wazuh' })).toBeNull()
      expect(problemWith({ ...EMPTY, signature: 'ET SCAN' })).toBeNull()
    })

    it('wants the address that sends where a destination is given', () => {
      expect(problemWith({ ...EMPTY, signature: 'x', destination: '52.0.0.0/8' })).toBe(
        'A destination is where an address sends to, so name that address too.',
      )
      expect(
        problemWith({ ...EMPTY, address: '192.168.1.30', destination: '52.0.0.0/8' }),
      ).toBeNull()
    })
  })

  describe('isAddress', () => {
    it.each(['52.1.2.3', '2001:db8::1', '::1'])('knows %s is one', (text) => {
      expect(isAddress(text)).toBe(true)
    })

    it.each(['example.com', 'ET SCAN', '52.1.2', '', 'fe80 ::1'])('knows %s is not', (text) => {
      expect(isAddress(text)).toBe(false)
    })
  })
})
