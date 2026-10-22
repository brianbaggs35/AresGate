import { nextTick } from 'vue'

import { ApiError } from '@/api/client'
import * as passkeysApi from '@/api/passkeys'
import PasskeysCard from '@/components/PasskeysCard.vue'
import { describeBrowser } from '@/format'
import { useSessionStore } from '@/stores/session'
import { flushPromises, mountWithPlugins } from '@/test/mount'
import * as webauthn from '@/webauthn'

const TOKEN = 'a-security-token'
const PASSWORD = 'a long enough phrase'
const laptop: passkeysApi.Passkey = {
  id: 'id-laptop',
  name: 'Work laptop',
  created_at: '2026-03-04T15:30:00Z',
  last_used_at: '2026-03-10T09:00:00Z',
}
const phone: passkeysApi.Passkey = {
  id: 'id-phone',
  name: 'Phone',
  created_at: '2026-03-05T08:00:00Z',
  last_used_at: null,
}
const challenge = {
  challenge_id: 'a-challenge',
  options: { challenge: 'AAAA' } as PublicKeyCredentialCreationOptionsJSON,
}
const made = {
  id: 'AAAA',
  rawId: 'AAAA',
  type: 'public-key',
  response: {
    clientDataJSON: 'BBBB',
    attestationObject: 'CCCC',
    authenticatorData: 'DDDD',
    publicKeyAlgorithm: -7,
    transports: ['internal'],
  },
  clientExtensionResults: {},
} satisfies RegistrationResponseJSON
const offline = () => new ApiError(0, "Can't reach AresGate.", 'offline')
const wrong = () => new ApiError(403, "The password isn't right.", 'forbidden')

async function open(
  list: passkeysApi.Passkey[] | Error = [],
  { supported = true }: { supported?: boolean } = {},
) {
  vi.spyOn(webauthn, 'passkeysSupported').mockReturnValue(supported)
  const fetchList = vi.spyOn(passkeysApi, 'fetchPasskeys')
  if (list instanceof Error) fetchList.mockRejectedValue(list)
  else fetchList.mockResolvedValue(list)
  const mounted = await mountWithPlugins(PasskeysCard, { signedIn: 'admin' })
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
  return { ...mounted, fetchList, find, click, type, submit, value }
}

type Opened = Awaited<ReturnType<typeof open>>

/** Gets as far as the form for a new passkey. */
async function startAdding(opened: Opened) {
  await opened.click('add-passkey')
}

/** The three steps of adding one, answered as a device and the API would. */
function answerAdding() {
  return {
    start: vi.spyOn(passkeysApi, 'startAddingPasskey').mockResolvedValue(challenge),
    create: vi.spyOn(webauthn, 'createPasskey').mockResolvedValue(made),
    add: vi.spyOn(passkeysApi, 'addPasskey').mockResolvedValue(phone),
  }
}

describe('PasskeysCard', () => {
  describe('looking at it', () => {
    it('shows a placeholder while it asks', async () => {
      vi.spyOn(webauthn, 'passkeysSupported').mockReturnValue(true)
      vi.spyOn(passkeysApi, 'fetchPasskeys').mockReturnValue(new Promise(() => {}))
      const { wrapper } = await mountWithPlugins(PasskeysCard, { signedIn: 'admin' })
      expect(wrapper.find('.v-skeleton-loader').exists()).toBe(true)
      expect(wrapper.find('[data-test="add-passkey"]').exists()).toBe(false)
    })

    it('says there are none, and offers to add one', async () => {
      const { find } = await open([])
      expect(find('no-passkeys').text()).toBe("You haven't added a passkey yet.")
      expect(find('passkey-list').exists()).toBe(false)
      expect(find('add-passkey').text()).toBe('Add a passkey')
    })

    it('lists each passkey by name, with when it was added and last used', async () => {
      const { wrapper, find } = await open([laptop, phone])
      const names = wrapper.findAll('[data-test="passkey-name"]').map((name) => name.text())
      expect(names).toEqual(['Work laptop', 'Phone'])
      const details = wrapper.findAll('[data-test="passkey-details"]').map((item) => item.text())
      expect(details[0]).toMatch(/^Added .*2026.* · Last used .*2026/)
      expect(details[1]).toMatch(/^Added .*2026.* · Never used$/)
      expect(find('no-passkeys').exists()).toBe(false)
    })

    it('names the passkey on each button that removes it', async () => {
      const { wrapper } = await open([laptop, phone])
      const labels = wrapper
        .findAll('[data-test="remove-passkey"]')
        .map((button) => button.attributes('aria-label'))
      expect(labels).toEqual(['Remove Work laptop', 'Remove Phone'])
    })

    it('says so when the browser has no passkeys, and still lists the ones it has', async () => {
      const { find } = await open([laptop], { supported: false })
      expect(find('passkeys-unsupported').text()).toContain("can't make a passkey")
      expect(find('add-passkey').exists()).toBe(false)
      expect(find('remove-passkey').exists()).toBe(true)
    })

    it('says why it can’t tell, and asks again when told to', async () => {
      const { find, click, fetchList } = await open(offline())
      expect(find('passkeys-load-error').text()).toContain("Can't reach AresGate.")
      expect(find('add-passkey').exists()).toBe(false)

      fetchList.mockResolvedValue([laptop])
      await click('passkeys-retry')
      expect(find('passkeys-load-error').exists()).toBe(false)
      expect(find('passkey-name').text()).toBe('Work laptop')
    })

    it('notes that the sign-in ended when the API says nobody is signed in', async () => {
      await open(new ApiError(401, "You're not signed in.", 'unauthenticated'))
      expect(useSessionStore()).toMatchObject({ signedIn: false, expired: true })
    })
  })

  describe('adding one', () => {
    it('asks for a name, which starts as the browser and system, and for the password', async () => {
      const opened = await open([])
      await startAdding(opened)
      const { wrapper, find, value } = opened
      expect(wrapper.find('h3').text()).toBe('Add a passkey')
      expect(value('new-passkey-name')).toBe(describeBrowser(navigator.userAgent))
      expect(find('new-passkey-password').find('input').attributes('autocomplete')).toBe(
        'current-password',
      )
      expect(document.activeElement).toBe(find('new-passkey-name').find('input').element)
    })

    it('asks for both before it asks the API', async () => {
      const opened = await open([])
      const { start } = answerAdding()
      await startAdding(opened)
      await opened.type('new-passkey-name', '  ')
      await opened.submit()
      expect(opened.wrapper.text()).toContain('Enter a name.')
      expect(opened.wrapper.text()).toContain('Enter your password.')
      expect(start).not.toHaveBeenCalled()
    })

    it('adds the passkey the device makes, and lists it', async () => {
      const opened = await open([laptop])
      const { start, create, add } = answerAdding()
      await startAdding(opened)
      await opened.type('new-passkey-name', 'Phone')
      await opened.type('new-passkey-password', PASSWORD)
      opened.fetchList.mockResolvedValue([laptop, phone])
      await opened.submit()

      expect(start).toHaveBeenCalledWith(PASSWORD, TOKEN)
      expect(create).toHaveBeenCalledWith(challenge.options)
      expect(add).toHaveBeenCalledWith('a-challenge', made, 'Phone', TOKEN)
      expect(opened.wrapper.findAll('[data-test="passkey-name"]')).toHaveLength(2)
      expect(opened.find('new-passkey-name').exists()).toBe(false)
      expect(opened.find('passkeys-error').exists()).toBe(false)
      expect(document.activeElement?.textContent).toBe('Passkeys')
    })

    it('forgets the password before the device asks for its unlock', async () => {
      const opened = await open([])
      const { create } = answerAdding()
      let passwordAtThatPoint: string | undefined
      create.mockImplementation(async () => {
        await nextTick()
        passwordAtThatPoint = opened.value('new-passkey-password')
        return made
      })
      await startAdding(opened)
      await opened.type('new-passkey-password', PASSWORD)
      await opened.submit()
      expect(passwordAtThatPoint).toBe('')
    })

    it('says when the password is wrong, clears it and asks the device for nothing', async () => {
      const opened = await open([])
      const { start, create, add } = answerAdding()
      start.mockRejectedValue(wrong())
      await startAdding(opened)
      await opened.type('new-passkey-password', 'not it')
      await opened.submit()
      expect(opened.find('passkeys-error').text()).toBe("The password isn't right.")
      expect(opened.value('new-passkey-password')).toBe('')
      expect(create).not.toHaveBeenCalled()
      expect(add).not.toHaveBeenCalled()
    })

    it('says when the device was cancelled, and keeps the form so the person can try again', async () => {
      const opened = await open([])
      const { create, add } = answerAdding()
      create.mockRejectedValue(new webauthn.PasskeyError('Making the passkey was cancelled.'))
      await startAdding(opened)
      await opened.type('new-passkey-password', PASSWORD)
      await opened.submit()
      expect(opened.find('passkeys-error').text()).toBe('Making the passkey was cancelled.')
      expect(opened.find('new-passkey-name').exists()).toBe(true)
      expect(add).not.toHaveBeenCalled()
    })

    it('says why the API refused the passkey', async () => {
      const opened = await open([])
      const { add } = answerAdding()
      add.mockRejectedValue(new ApiError(422, "That passkey couldn't be added.", 'invalid'))
      await startAdding(opened)
      await opened.type('new-passkey-password', PASSWORD)
      await opened.submit()
      expect(opened.find('passkeys-error').text()).toBe("That passkey couldn't be added.")
    })

    it('goes back to the list without adding anything', async () => {
      const opened = await open([laptop])
      const { start } = answerAdding()
      await startAdding(opened)
      await opened.click('cancel')
      expect(opened.find('new-passkey-name').exists()).toBe(false)
      expect(opened.find('add-passkey').exists()).toBe(true)
      expect(start).not.toHaveBeenCalled()
      expect(document.activeElement?.textContent).toBe('Passkeys')
    })
  })

  describe('removing one', () => {
    async function startRemoving(opened: Opened) {
      await opened.wrapper.findAll('[data-test="remove-passkey"]')[0]?.trigger('click')
      await flushPromises()
    }

    it('names the passkey and asks for the password', async () => {
      const opened = await open([laptop, phone])
      await startRemoving(opened)
      expect(opened.wrapper.find('h3').text()).toBe('Remove Work laptop')
      expect(document.activeElement).toBe(
        opened.find('remove-passkey-password').find('input').element,
      )
    })

    it('asks for the password before it asks the API', async () => {
      const opened = await open([laptop])
      const remove = vi.spyOn(passkeysApi, 'removePasskey')
      await startRemoving(opened)
      await opened.submit()
      expect(opened.wrapper.text()).toContain('Enter your password.')
      expect(remove).not.toHaveBeenCalled()
    })

    it('removes it, and lists what is left', async () => {
      const opened = await open([laptop, phone])
      const remove = vi.spyOn(passkeysApi, 'removePasskey').mockResolvedValue(undefined)
      await startRemoving(opened)
      await opened.type('remove-passkey-password', PASSWORD)
      opened.fetchList.mockResolvedValue([phone])
      await opened.submit()

      expect(remove).toHaveBeenCalledWith('id-laptop', PASSWORD, TOKEN)
      expect(opened.wrapper.findAll('[data-test="passkey-name"]').map((n) => n.text())).toEqual([
        'Phone',
      ])
      expect(document.activeElement?.textContent).toBe('Passkeys')
    })

    it('says when the password is wrong, and clears it', async () => {
      const opened = await open([laptop])
      vi.spyOn(passkeysApi, 'removePasskey').mockRejectedValue(wrong())
      await startRemoving(opened)
      await opened.type('remove-passkey-password', 'not it')
      await opened.submit()
      expect(opened.find('passkeys-error').text()).toBe("The password isn't right.")
      expect(opened.value('remove-passkey-password')).toBe('')
    })

    it('goes back to the list without removing anything', async () => {
      const opened = await open([laptop])
      const remove = vi.spyOn(passkeysApi, 'removePasskey')
      await startRemoving(opened)
      await opened.click('cancel')
      expect(opened.find('passkey-name').text()).toBe('Work laptop')
      expect(remove).not.toHaveBeenCalled()
    })
  })
})
