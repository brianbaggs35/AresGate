import type { Lookup } from '@/api/threatIntel'
import {
  CLEAN_LOOKUP,
  GREYNOISE_LOOKUP,
  MALICIOUS_LOOKUP,
  OTX_LOOKUP,
  SAFE_RULING,
} from '@/test/threatIntel'
import {
  JUDGEMENT,
  JUDGEMENTS,
  KIND,
  PROVIDERS,
  RULING,
  judgementLabel,
  providerOf,
  summaryOf,
  tallyOf,
  withRuling,
} from '@/threatIntel'

/** An answer as one service gave it, with the counts and judgement of the test. */
function answer(base: Lookup, judgement: Lookup['reported_judgement'], counts = {}): Lookup {
  return { ...base, judgement, reported_judgement: judgement, ...counts }
}

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

  it('lists the services in the order of their tabs, each with what it answers about', () => {
    expect(PROVIDERS.map((one) => one.key)).toEqual(['virustotal', 'otx', 'greynoise'])
    expect(PROVIDERS.map((one) => one.name)).toEqual(['VirusTotal', 'AlienVault OTX', 'GreyNoise'])
    expect(providerOf('otx').about).toBe('an IP address or a domain')
    expect(providerOf('greynoise').about).toBe('an IPv4 address')
  })

  it('says what a clean answer is in the words of the service that gave it', () => {
    expect(judgementLabel('virustotal', 'clean')).toBe('No engine flagged it')
    expect(judgementLabel('otx', 'clean')).toBe('Listed as safe')
    expect(judgementLabel('greynoise', 'clean')).toBe('Benign or a common business service')
    expect(judgementLabel('otx', 'malicious')).toBe('Reported as malicious')
  })

  it('says what VirusTotal made of an answer from its engines', () => {
    expect(summaryOf(MALICIOUS_LOOKUP)).toBe('3 of 84 engines flagged it as malicious.')
    expect(summaryOf(answer(MALICIOUS_LOOKUP, 'suspicious'))).toBe(
      '1 of 84 engines flagged it as suspicious.',
    )
    expect(summaryOf(CLEAN_LOOKUP)).toBe('None of the 82 engines flagged it.')
    expect(summaryOf(answer(CLEAN_LOOKUP, 'unknown'))).toBe('VirusTotal has no report on it yet.')
  })

  it('says what AlienVault OTX made of an answer from its pulses', () => {
    expect(summaryOf(OTX_LOOKUP)).toBe(
      '3 pulses name it, 2 of them also naming malware, an adversary or an attack technique.',
    )
    expect(summaryOf(answer(OTX_LOOKUP, 'suspicious', { malicious: 0, suspicious: 1 }))).toBe(
      '1 pulse names it, none of them naming malware, an adversary or an attack technique.',
    )
    expect(summaryOf(answer(OTX_LOOKUP, 'clean'))).toBe('AlienVault OTX lists it as safe.')
    expect(summaryOf(answer(OTX_LOOKUP, 'unknown'))).toBe('No pulse on AlienVault OTX names it.')
  })

  it('says what GreyNoise made of an answer from its classification', () => {
    expect(summaryOf(answer(GREYNOISE_LOOKUP, 'malicious'))).toBe(
      'GreyNoise classifies it as malicious.',
    )
    expect(summaryOf(GREYNOISE_LOOKUP)).toBe(
      "GreyNoise has seen it scanning the internet, and doesn't classify it.",
    )
    expect(summaryOf(answer(GREYNOISE_LOOKUP, 'clean'))).toBe(
      'GreyNoise classifies it as benign, or lists it as a common business service.',
    )
    expect(summaryOf(answer(GREYNOISE_LOOKUP, 'unknown'))).toBe('GreyNoise has no report on it.')
  })

  it('tallies an answer for a row of a list, in what its service counts', () => {
    expect(tallyOf(MALICIOUS_LOOKUP)).toBe('4 of 84 flagged')
    expect(tallyOf(answer(CLEAN_LOOKUP, 'unknown'))).toBe('No report')
    expect(tallyOf(OTX_LOOKUP)).toBe('3 pulses')
    expect(tallyOf(answer(OTX_LOOKUP, 'suspicious', { malicious: 0, suspicious: 1 }))).toBe(
      '1 pulse',
    )
    expect(tallyOf(answer(OTX_LOOKUP, 'clean'))).toBe('Listed as safe')
    expect(tallyOf(GREYNOISE_LOOKUP)).toBe('Suspicious')
    expect(tallyOf(answer(GREYNOISE_LOOKUP, 'clean'))).toBe('Clean')
  })
})
