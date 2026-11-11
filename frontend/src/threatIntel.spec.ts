import { CLEAN_LOOKUP, MALICIOUS_LOOKUP, SAFE_RULING } from '@/test/threatIntel'
import { JUDGEMENT, JUDGEMENTS, KIND, RULING, withRuling } from '@/threatIntel'

describe('threatIntel', () => {
  it('names every kind of subject', () => {
    expect(KIND).toEqual({ ip: 'IP address', domain: 'Domain', url: 'Web address' })
  })

  it('lists the judgements with what was flagged first, each with a look of its own', () => {
    expect(JUDGEMENTS).toEqual(['malicious', 'suspicious', 'clean', 'unknown'])
    expect(JUDGEMENTS.map((name) => JUDGEMENT[name].short)).toEqual([
      'Malicious',
      'Suspicious',
      'Clean',
      'No report',
    ])
    expect(new Set(JUDGEMENTS.map((name) => JUDGEMENT[name].icon)).size).toBe(4)
  })

  it('says what each ruling means and shows each in a look of its own', () => {
    expect(Object.keys(RULING)).toEqual(['safe', 'suspicious'])
    expect(RULING.safe.label).toBe('You ruled it safe')
    expect(RULING.suspicious.short).toBe('Suspicious')
    expect(RULING.safe.icon).not.toBe(RULING.suspicious.icon)
  })

  it('puts a ruling on an answer so that it comes to the ruling and keeps what VirusTotal said', () => {
    const ruled = withRuling(MALICIOUS_LOOKUP, SAFE_RULING)

    expect(ruled.judgement).toBe('clean')
    expect(ruled.reported_judgement).toBe('malicious')
    expect(ruled.ruling).toEqual(SAFE_RULING)
    expect(ruled.malicious).toBe(MALICIOUS_LOOKUP.malicious)
  })

  it('takes a ruling off an answer so that it comes to what VirusTotal said again', () => {
    const ruled = withRuling(MALICIOUS_LOOKUP, SAFE_RULING)

    const back = withRuling(ruled, null)

    expect(back.judgement).toBe('malicious')
    expect(back.ruling).toBeNull()
    expect(withRuling(CLEAN_LOOKUP, null)).toEqual(CLEAN_LOOKUP)
  })
})
