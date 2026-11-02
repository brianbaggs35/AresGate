import {
  CONFIDENCES,
  SEVERITIES,
  browserZone,
  describeRules,
  perHour,
  toMinutes,
  toTime,
  withCurrent,
} from '@/alertRules'
import { choices, rules } from '@/test/alerts'

describe('toTime', () => {
  it('writes minutes after midnight as a time of day', () => {
    expect(toTime(0)).toBe('00:00')
    expect(toTime(7 * 60 + 5)).toBe('07:05')
    expect(toTime(23 * 60 + 59)).toBe('23:59')
  })
})

describe('toMinutes', () => {
  it('reads a time of day as minutes after midnight', () => {
    expect(toMinutes('00:00')).toBe(0)
    expect(toMinutes('22:30')).toBe(22 * 60 + 30)
    expect(toMinutes('23:59')).toBe(1439)
  })

  it.each(['', '7:00', '24:00', '12:60', 'noon', '12:00:00'])('refuses %j', (text) => {
    expect(toMinutes(text)).toBeNull()
  })
})

describe('perHour', () => {
  it('says how many messages are allowed an hour', () => {
    expect(perHour(1)).toBe('At most 1 message an hour')
    expect(perHour(6)).toBe('At most 6 messages an hour')
  })
})

describe('withCurrent', () => {
  it('leaves the choices as they are when they hold the value', () => {
    expect(withCurrent(CONFIDENCES, 35, (value) => `${value.toString()}%`)).toEqual([
      ...CONFIDENCES,
    ])
  })

  it('adds a value set from elsewhere, in its place', () => {
    const found = withCurrent(CONFIDENCES, 50, (value) => `${value.toString()}% or more`)

    expect(found.map((item) => item.value)).toEqual([65, 50, 35, 0])
    expect(found[1]?.label).toBe('50% or more')
  })
})

describe('browserZone', () => {
  it('is the name of a time zone', () => {
    expect(browserZone()).toMatch(/^[A-Za-z_]+(\/[A-Za-z_+\-0-9]+)*$/)
  })
})

describe('describeRules', () => {
  it('says what a new destination is told about', () => {
    expect(describeRules(rules(), choices())).toBe(
      'Tells you about incidents that are medium or worse, when AresGate is at least 65% sure. From any program. At most 6 messages an hour.',
    )
  })

  it('names the programs and kinds chosen', () => {
    const chosen = rules({
      sources: ['wazuh', 'opnsense'],
      activities: ['scan', 'brute_force'],
      min_confidence: 0,
      min_severity: 4,
      max_per_hour: 1,
    })

    expect(describeRules(chosen, choices())).toBe(
      'Tells you about incidents that are critical only, however sure AresGate is. Only from Wazuh and OPNsense. Only scanning and brute force. At most 1 message an hour.',
    )
  })

  it('says one program by its name, and one it does not know by its key', () => {
    expect(describeRules(rules({ sources: ['wazuh'] }), choices())).toContain('Only from Wazuh.')
    expect(describeRules(rules({ sources: ['zenarmor'] }), choices())).toContain(
      'Only from zenarmor.',
    )
  })

  it('lists three programs with commas', () => {
    const three = rules({ sources: ['opnsense', 'ntopng', 'wazuh'] })

    expect(describeRules(three, choices())).toContain('Only from OPNsense, ntopng and Wazuh.')
  })

  it('says the quiet hours, and whether critical ones get through', () => {
    const quiet = rules({ quiet_hours: true, time_zone: 'Europe/Berlin' })

    expect(describeRules(quiet, choices())).toContain(
      'Quiet from 22:00 to 07:00 (Europe/Berlin), except critical ones.',
    )
    expect(describeRules({ ...quiet, quiet_critical: false }, choices())).toContain(
      'Quiet from 22:00 to 07:00 (Europe/Berlin).',
    )
  })

  it('does not trip on a severity it has no word for', () => {
    expect(SEVERITIES.some((item) => item.value === 9)).toBe(false)
    expect(describeRules(rules({ min_severity: 9 }), choices())).toContain('severity 9 or worse')
  })
})
