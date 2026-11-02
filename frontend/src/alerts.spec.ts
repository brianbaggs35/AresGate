import { KINDS, lastResult, maskedAddress } from '@/alerts'
import { destination, failing, working } from '@/test/alerts'

describe('maskedAddress', () => {
  it('shows where the webhook is and the end of its number, and none of the token', () => {
    expect(maskedAddress(destination())).toBe('discord.com/api/webhooks/…6789/••••••••')
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
})
