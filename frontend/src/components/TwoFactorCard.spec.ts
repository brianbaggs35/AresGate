import { ApiError } from '@/api/client'
import * as twoFactorApi from '@/api/two-factor'
import TwoFactorCard from '@/components/TwoFactorCard.vue'
import { useSessionStore } from '@/stores/session'
import { flushPromises, mountWithPlugins } from '@/test/mount'

const TOKEN = 'a-security-token'
const off = { enabled: false, recovery_codes_left: 0 }
const on = { enabled: true, recovery_codes_left: 10 }
const enrollment = {
  secret: 'JBSWY3DPEHPK3PXPJBSWY3DPEHPK3PXP',
  otpauth_uri: 'otpauth://totp/AresGate:admin?secret=JBSWY3DPEHPK3PXPJBSWY3DPEHPK3PXP',
}
const codes = Array.from({ length: 10 }, (_, number) => `K7QD-3MWX-${9000 + number}`)
const offline = () => new ApiError(0, "Can't reach AresGate.", 'offline')
const wrong = () => new ApiError(403, "That isn't right.", 'forbidden')

async function open(status: twoFactorApi.TwoFactorStatus | Error = off) {
  const fetchStatus = vi.spyOn(twoFactorApi, 'fetchTwoFactorStatus')
  if (status instanceof Error) fetchStatus.mockRejectedValue(status)
  else fetchStatus.mockResolvedValue(status)
  const mounted = await mountWithPlugins(TwoFactorCard, { signedIn: 'admin' })
  await flushPromises()
  const find = (selector: string) => mounted.wrapper.find(`[data-test="${selector}"]`)
  const click = async (selector: string) => {
    await find(selector).trigger('click')
    await flushPromises()
  }
  const type = async (selector: string, value: string) => {
    await find(selector).find('input').setValue(value)
  }
  const submit = async () => {
    await mounted.wrapper.find('form').trigger('submit')
    await flushPromises()
  }
  const value = (selector: string) => find(selector).find<HTMLInputElement>('input').element.value
  return { ...mounted, fetchStatus, find, click, type, submit, value }
}

type Opened = Awaited<ReturnType<typeof open>>

/** Starts adding an app, so the card shows its key. */
async function startAdding(opened: Opened) {
  const start = vi.spyOn(twoFactorApi, 'startTwoFactor').mockResolvedValue(enrollment)
  await opened.click('add-app')
  return start
}

/** Gets as far as the recovery codes after turning it on. */
async function reachCodes(opened: Opened) {
  await startAdding(opened)
  const confirm = vi.spyOn(twoFactorApi, 'confirmTwoFactor').mockResolvedValue(codes)
  opened.fetchStatus.mockResolvedValue(on)
  await opened.type('confirm-code', '123456')
  await opened.submit()
  return confirm
}

describe('TwoFactorCard', () => {
  describe('looking at it', () => {
    it('shows a placeholder while it asks', async () => {
      vi.spyOn(twoFactorApi, 'fetchTwoFactorStatus').mockReturnValue(new Promise(() => {}))
      const { wrapper } = await mountWithPlugins(TwoFactorCard, { signedIn: 'admin' })
      expect(wrapper.find('.v-skeleton-loader').exists()).toBe(true)
      expect(wrapper.find('[data-test="add-app"]').exists()).toBe(false)
    })

    it('says it is off, and offers to add an app', async () => {
      const { find } = await open(off)
      expect(find('two-factor-off').text()).toContain('Off.')
      expect(find('add-app').text()).toBe('Add an authenticator app')
      expect(find('two-factor-state').exists()).toBe(false)
    })

    it('says it is on, and how many recovery codes are left', async () => {
      const { find } = await open(on)
      expect(find('two-factor-state').text()).toBe('On')
      expect(find('recovery-codes-left').text()).toBe('10 recovery codes left')
      expect(find('recovery-codes-low').exists()).toBe(false)
      expect(find('add-app').exists()).toBe(false)
    })

    it('says one recovery code, and suggests new ones when it is running low', async () => {
      const { find } = await open({ enabled: true, recovery_codes_left: 1 })
      expect(find('recovery-codes-left').text()).toBe('1 recovery code left')
      expect(find('recovery-codes-low').text()).toContain('running low')
      expect(find('recovery-codes-low').find('.v-alert').classes()).toContain('text-warning')
    })

    it('says plainly when none are left', async () => {
      const { find } = await open({ enabled: true, recovery_codes_left: 0 })
      expect(find('recovery-codes-left').text()).toBe('0 recovery codes left')
      expect(find('recovery-codes-low').text()).toContain('no recovery codes left')
      expect(find('recovery-codes-low').find('.v-alert').classes()).toContain('text-error')
    })

    it('says why it can’t tell, and asks again when told to', async () => {
      const { find, click, fetchStatus } = await open(offline())
      expect(find('two-factor-load-error').text()).toContain("Can't reach AresGate.")
      expect(find('add-app').exists()).toBe(false)

      fetchStatus.mockResolvedValue(on)
      await click('two-factor-retry')
      expect(find('two-factor-load-error').exists()).toBe(false)
      expect(find('two-factor-state').exists()).toBe(true)
    })

    it('notes that the sign-in ended when the API says nobody is signed in', async () => {
      await open(new ApiError(401, "You're not signed in.", 'unauthenticated'))
      expect(useSessionStore()).toMatchObject({ signedIn: false, expired: true })
    })
  })

  describe('adding an authenticator app', () => {
    it('shows a QR code, a link for this device and the key to type in', async () => {
      const opened = await open(off)
      const start = await startAdding(opened)
      const { wrapper, find } = opened
      expect(start).toHaveBeenCalledWith(TOKEN)
      expect(wrapper.find('svg[role="img"]').attributes('aria-label')).toBe(
        'QR code for your authenticator app',
      )
      expect(find('two-factor-key').text()).toBe('JBSW Y3DP EHPK 3PXP JBSW Y3DP EHPK 3PXP')
      expect(find('open-in-app').attributes('href')).toBe(enrollment.otpauth_uri)
      expect(wrapper.find('h3').text()).toBe('Add your authenticator app')
    })

    it('puts the keyboard in the code field, and asks for the code from the app', async () => {
      const opened = await open(off)
      await startAdding(opened)
      expect(document.activeElement).toBe(opened.find('confirm-code').find('input').element)
      expect(opened.find('confirm-code').find('input').attributes('inputmode')).toBe('numeric')
    })

    it('says why it couldn’t start', async () => {
      const { find, click } = await open(off)
      vi.spyOn(twoFactorApi, 'startTwoFactor').mockRejectedValue(
        new ApiError(409, 'An authenticator app is already set up.', 'conflict'),
      )
      await click('add-app')
      expect(find('two-factor-error').text()).toBe('An authenticator app is already set up.')
      expect(find('two-factor-key').exists()).toBe(false)
    })

    it('can be given up on, which leaves it off', async () => {
      const opened = await open(off)
      await startAdding(opened)
      await opened.click('cancel')
      expect(opened.find('two-factor-key').exists()).toBe(false)
      expect(opened.find('add-app').exists()).toBe(true)
      expect(document.activeElement?.textContent).toBe('Two-step verification')
    })

    it('asks for the code before it asks the API', async () => {
      const opened = await open(off)
      await startAdding(opened)
      const confirm = vi.spyOn(twoFactorApi, 'confirmTwoFactor')
      await opened.submit()
      expect(opened.wrapper.text()).toContain('Enter the code from the app.')
      expect(confirm).not.toHaveBeenCalled()
    })

    it('says when the code is wrong, clears it, and stays to try again', async () => {
      const opened = await open(off)
      await startAdding(opened)
      vi.spyOn(twoFactorApi, 'confirmTwoFactor').mockRejectedValue(
        new ApiError(422, "That code isn't right.", 'invalid'),
      )
      await opened.type('confirm-code', '000000')
      await opened.submit()
      expect(opened.find('two-factor-error').text()).toBe("That code isn't right.")
      expect(opened.value('confirm-code')).toBe('')
      expect(opened.find('two-factor-key').exists()).toBe(true)
    })

    it('turns it on with the code, and shows the recovery codes', async () => {
      const opened = await open(off)
      const confirm = await reachCodes(opened)
      const { wrapper, find } = opened
      expect(confirm).toHaveBeenCalledWith('123456', TOKEN)
      expect(wrapper.find('h3').text()).toBe('Save your recovery codes')
      expect(wrapper.findAll('[data-test="recovery-code"]').map((item) => item.text())).toEqual(
        codes,
      )
      expect(find('two-factor-key').exists()).toBe(false)
      expect(document.activeElement?.textContent.trim()).toBe('Save your recovery codes')
    })

    it('only goes on once the person says the codes are saved, and then shows it is on', async () => {
      const opened = await open(off)
      await reachCodes(opened)
      const { find, click } = opened
      expect(find('codes-done').attributes('disabled')).toBeDefined()

      await find('codes-saved').find('input').setValue(true)
      expect(find('codes-done').attributes('disabled')).toBeUndefined()

      await click('codes-done')
      expect(find('recovery-code').exists()).toBe(false)
      expect(find('two-factor-state').text()).toBe('On')
      expect(find('recovery-codes-left').text()).toBe('10 recovery codes left')
      expect(document.activeElement?.textContent).toBe('Two-step verification')
    })

    it('copies the codes, one to a line', async () => {
      const writeText = vi.fn().mockResolvedValue(undefined)
      Object.defineProperty(navigator, 'clipboard', { configurable: true, value: { writeText } })
      try {
        const opened = await open(off)
        await reachCodes(opened)
        await opened.click('copy-codes')
        expect(writeText).toHaveBeenCalledWith(codes.join('\n'))
        expect(opened.find('copy-note').text()).toBe('Copied.')
      } finally {
        Reflect.deleteProperty(navigator, 'clipboard')
      }
    })

    it('says so when it can’t copy them', async () => {
      const opened = await open(off)
      await reachCodes(opened)
      await opened.click('copy-codes')
      expect(opened.find('copy-note').text()).toContain("Couldn't copy them")
    })

    it('forgets the last copy note when new codes are shown', async () => {
      const opened = await open(on)
      await opened.click('renew-codes')
      vi.spyOn(twoFactorApi, 'renewRecoveryCodes').mockResolvedValue(codes)
      await opened.type('renew-code', '123456')
      await opened.submit()
      expect(opened.find('copy-note').text()).toBe('')
    })
  })

  describe('making new recovery codes', () => {
    async function openRenewing() {
      const opened = await open({ enabled: true, recovery_codes_left: 2 })
      await opened.click('renew-codes')
      return opened
    }

    it('asks for a code, and says what it will do', async () => {
      const { wrapper, find } = await openRenewing()
      expect(wrapper.find('h3').text()).toBe('Make new recovery codes')
      expect(wrapper.text()).toContain('ends the recovery codes you have now')
      expect(document.activeElement).toBe(find('renew-code').find('input').element)
    })

    it('shows the new codes once the code is right', async () => {
      const opened = await openRenewing()
      const renew = vi.spyOn(twoFactorApi, 'renewRecoveryCodes').mockResolvedValue(codes)
      opened.fetchStatus.mockResolvedValue(on)
      await opened.type('renew-code', 'K7QD-3MWX-9HPA')
      await opened.submit()
      expect(renew).toHaveBeenCalledWith('K7QD-3MWX-9HPA', TOKEN)
      expect(opened.wrapper.findAll('[data-test="recovery-code"]')).toHaveLength(10)
      await opened.find('codes-saved').find('input').setValue(true)
      await opened.click('codes-done')
      expect(opened.find('recovery-codes-left').text()).toBe('10 recovery codes left')
    })

    it('asks for a code before it asks the API', async () => {
      const opened = await openRenewing()
      const renew = vi.spyOn(twoFactorApi, 'renewRecoveryCodes')
      await opened.submit()
      expect(opened.wrapper.text()).toContain('Enter a code.')
      expect(renew).not.toHaveBeenCalled()
    })

    it('says when the code is wrong, and the sign-in carries on', async () => {
      const opened = await openRenewing()
      vi.spyOn(twoFactorApi, 'renewRecoveryCodes').mockRejectedValue(wrong())
      await opened.type('renew-code', '000000')
      await opened.submit()
      expect(opened.find('two-factor-error').text()).toBe("That isn't right.")
      expect(opened.value('renew-code')).toBe('')
      expect(useSessionStore().signedIn).toBe(true)
    })

    it('can be given up on', async () => {
      const opened = await openRenewing()
      await opened.click('cancel')
      expect(opened.find('renew-code').exists()).toBe(false)
      expect(opened.find('two-factor-state').exists()).toBe(true)
    })
  })

  describe('turning it off', () => {
    async function openTurningOff() {
      const opened = await open(on)
      await opened.click('turn-off')
      return opened
    }

    it('asks for the password and a code, with the hints password managers need', async () => {
      const { wrapper, find } = await openTurningOff()
      expect(wrapper.find('h3').text()).toBe('Turn off two-step verification')
      expect(find('turn-off-password').find('input').attributes('autocomplete')).toBe(
        'current-password',
      )
      expect(find('turn-off-code').find('input').attributes('autocomplete')).toBe('one-time-code')
    })

    it('turns it off with both, and shows that it is off', async () => {
      const opened = await openTurningOff()
      const turnOff = vi.spyOn(twoFactorApi, 'turnOffTwoFactor').mockResolvedValue()
      opened.fetchStatus.mockResolvedValue(off)
      await opened.type('turn-off-password', 'a long enough phrase')
      await opened.type('turn-off-code', '123456')
      await opened.submit()
      expect(turnOff).toHaveBeenCalledWith('a long enough phrase', '123456', TOKEN)
      expect(opened.find('two-factor-off').exists()).toBe(true)
      expect(opened.find('two-factor-state').exists()).toBe(false)
      expect(document.activeElement?.textContent).toBe('Two-step verification')
    })

    it('asks for both before it asks the API', async () => {
      const opened = await openTurningOff()
      const turnOff = vi.spyOn(twoFactorApi, 'turnOffTwoFactor')
      await opened.submit()
      expect(opened.wrapper.text()).toContain('Enter your password.')
      expect(opened.wrapper.text()).toContain('Enter a code.')
      expect(turnOff).not.toHaveBeenCalled()
    })

    it('says when either is wrong, clears both, and stays signed in', async () => {
      const opened = await openTurningOff()
      vi.spyOn(twoFactorApi, 'turnOffTwoFactor').mockRejectedValue(
        new ApiError(403, "The password or the code isn't right.", 'forbidden'),
      )
      await opened.type('turn-off-password', 'a long enough phrase')
      await opened.type('turn-off-code', '000000')
      await opened.submit()
      expect(opened.find('two-factor-error').text()).toBe("The password or the code isn't right.")
      expect(opened.value('turn-off-password')).toBe('')
      expect(opened.value('turn-off-code')).toBe('')
      expect(useSessionStore().signedIn).toBe(true)
    })

    it('says how long to wait when too many guesses have locked it', async () => {
      const opened = await openTurningOff()
      vi.spyOn(twoFactorApi, 'turnOffTwoFactor').mockRejectedValue(
        new ApiError(429, 'Too many attempts. Try again in 1 minute.', 'rate_limited'),
      )
      await opened.type('turn-off-password', 'a long enough phrase')
      await opened.type('turn-off-code', '000000')
      await opened.submit()
      expect(opened.find('two-factor-error').text()).toBe(
        'Too many attempts. Try again in 1 minute.',
      )
    })

    it('can be given up on, which leaves it on', async () => {
      const opened = await openTurningOff()
      await opened.click('cancel')
      expect(opened.find('turn-off-password').exists()).toBe(false)
      expect(opened.find('two-factor-state').exists()).toBe(true)
    })
  })
})
