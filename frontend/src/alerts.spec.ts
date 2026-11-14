import {
  DELIVERY_REASONS,
  DELIVERY_STATES,
  KINDS,
  addressLabel,
  deliveryTitle,
  deliveryTotals,
  lastResult,
  maskedAddress,
} from '@/alerts'
import { destination, emailDestination, failing, working } from '@/test/alerts'

describe('maskedAddress', () => {
  it('shows where the webhook is and the end of its number, and none of the token', () => {
    expect(maskedAddress(destination())).toBe('discord.com/api/webhooks/…6789/••••••••')
  })

  it('shows where an email destination goes and the mail server it goes through', () => {
    expect(maskedAddress(emailDestination())).toBe('me@example.org through smtp.example.com')
  })

  it('says an email destination waits for the mail server while there is none', () => {
    expect(maskedAddress(emailDestination({ host: '' }))).toBe(
      'me@example.org, once the mail server is set up',
    )
  })

  it('copes with an email destination that somehow has no address', () => {
    expect(maskedAddress(emailDestination({ host: '', recipient: null }))).toBe(
      ', once the mail server is set up',
    )
    expect(maskedAddress(emailDestination({ recipient: null }))).toBe(' through smtp.example.com')
  })
})

describe('addressLabel', () => {
  it('says what the address is, for a screen reader', () => {
    expect(addressLabel(destination())).toBe('Webhook address, with the secret part hidden: ')
    expect(addressLabel(emailDestination())).toContain('Email address')
  })
})

describe('lastResult', () => {
  const now = Date.now()

  it('says a destination that was never tried has not been', () => {
    expect(lastResult(destination(), now)).toBe('Not tried yet. Send a test message to check it.')
  })

  it('says when a message last got through', () => {
    expect(lastResult(working(), now)).toBe('A message last got through 10 minutes ago.')
  })

  it('says a failure and when a message last got through before it', () => {
    expect(lastResult(failing(), now)).toBe(
      'The last try failed. A message last got through 1 hour ago.',
    )
  })

  it('says a failure when no message has ever got through', () => {
    expect(lastResult(failing({ last_success_at: null }), now)).toBe(
      'The last try failed. No message has got through yet.',
    )
  })

  it('says when the address is gone', () => {
    expect(lastResult(destination({ status: 'not_connected' }), now)).toBe(
      'Its webhook address is gone.',
    )
  })

  it('says when the mail server is gone', () => {
    expect(lastResult(emailDestination({ status: 'not_connected' }), now)).toBe(
      "The mail server isn't set up.",
    )
  })

  it('falls back to the last try for a working one that has no success date', () => {
    const at = new Date(now - 3 * 60_000).toISOString()

    expect(
      lastResult(
        destination({ status: 'connected', last_attempt_at: at, last_success_at: null }),
        now,
      ),
    ).toBe('A message last got through 3 minutes ago.')
  })
})

describe('the kinds', () => {
  it('has a name and a picture for Discord', () => {
    expect(KINDS.discord.label).toBe('Discord')
    expect(KINDS.discord.icon).toBeDefined()
  })

  it('has a name and a picture for email', () => {
    expect(KINDS.email.label).toBe('Email')
    expect(KINDS.email.icon).toBeDefined()
  })
})

describe('deliveryTotals', () => {
  it('says how many were sent, how many wait and how many did not get through', () => {
    expect(
      deliveryTotals({ sent: 5, queued: 1, held: 2, retrying: 1, limited: 1, failed: 3 }),
    ).toBe('5 sent, 5 waiting, 3 not sent')
  })

  it('counts what was told in a summary or left out only in saying there is something', () => {
    expect(deliveryTotals({ summarized: 2 })).toBe('0 sent, 0 waiting, 0 not sent')
    expect(deliveryTotals({ dropped: 1 })).toBe('0 sent, 0 waiting, 0 not sent')
  })

  it('says nothing yet when there is nothing', () => {
    expect(deliveryTotals({})).toBe('Nothing yet.')
  })
})

describe('deliveryTitle', () => {
  it('is the incident title for a message about an incident', () => {
    expect(deliveryTitle({ kind: 'incident', title: 'A scan', covers: 0, reason: 'new' })).toBe(
      'A scan',
    )
  })

  it('says how many incidents a summary told of, and why they were summarised', () => {
    const base = { kind: 'summary', title: '', covers: 4 } as const
    expect(deliveryTitle({ ...base, reason: 'limit' })).toBe('4 incidents held back by the limit')
    expect(deliveryTitle({ ...base, covers: 1, reason: 'quiet' })).toBe(
      '1 incident came in during quiet hours',
    )
  })

  it('says a change to a message sent before is the incident standing down', () => {
    expect(deliveryTitle({ kind: 'update', title: 'A scan', covers: 0, reason: 'retract' })).toBe(
      'Stood down: A scan',
    )
  })

  it('says a message about a collector is that it went quiet, or is back', () => {
    const base = { kind: 'watchdog', title: 'OPNsense · Connection check', covers: 0 } as const
    expect(deliveryTitle({ ...base, reason: 'silent' })).toBe(
      'OPNsense · Connection check has gone quiet',
    )
    expect(deliveryTitle({ ...base, reason: 'back' })).toBe(
      'OPNsense · Connection check is reporting again',
    )
  })
})

describe('the words of the log', () => {
  it('names every state and every reason', () => {
    expect(Object.keys(DELIVERY_STATES)).toHaveLength(8)
    expect(Object.keys(DELIVERY_REASONS)).toEqual([
      'new',
      'worse',
      'reopened',
      'limit',
      'quiet',
      'retract',
      'silent',
      'back',
    ])
    expect(DELIVERY_STATES.sent.waiting).toBe(false)
    expect(DELIVERY_STATES.held.waiting).toBe(true)
  })
})
