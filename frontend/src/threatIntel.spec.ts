import { JUDGEMENT, JUDGEMENTS, KIND } from '@/threatIntel'

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
})
