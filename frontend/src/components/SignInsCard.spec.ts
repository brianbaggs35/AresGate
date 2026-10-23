import * as accountApi from '@/api/account'
import { ApiError } from '@/api/client'
import SignInsCard from '@/components/SignInsCard.vue'
import { useSessionStore } from '@/stores/session'
import { flushPromises, mountWithPlugins } from '@/test/mount'

const TOKEN = 'a-security-token'
const FIREFOX = 'Mozilla/5.0 (X11; Linux x86_64; rv:130.0) Gecko/20100101 Firefox/130.0'
const SAFARI_PHONE =
  'Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1'

const here: accountApi.SignIn = {
  id: 'here',
  current: true,
  address: '192.168.1.20',
  user_agent: FIREFOX,
  started_at: '2026-03-04T15:30:00Z',
  last_seen_at: new Date().toISOString(),
  expires_at: '2026-03-11T15:30:00Z',
}
const phone: accountApi.SignIn = {
  id: 'phone',
  current: false,
  address: '192.168.1.31',
  user_agent: SAFARI_PHONE,
  started_at: '2026-03-05T08:00:00Z',
  last_seen_at: new Date(Date.now() - 2 * 3600 * 1000).toISOString(),
  expires_at: '2026-03-12T08:00:00Z',
}
const old: accountApi.SignIn = {
  id: 'old',
  current: false,
  address: null,
  user_agent: null,
  started_at: '2026-02-01T08:00:00Z',
  last_seen_at: '2026-02-02T08:00:00Z',
  expires_at: '2026-02-08T08:00:00Z',
}
const offline = () => new ApiError(0, "Can't reach AresGate.", 'offline')

async function open(list: accountApi.SignIn[] | Error = [here, phone]) {
  const fetchList = vi.spyOn(accountApi, 'fetchSignIns')
  if (list instanceof Error) fetchList.mockRejectedValue(list)
  else fetchList.mockResolvedValue(list)
  const mounted = await mountWithPlugins(SignInsCard, { signedIn: 'admin', withApp: true })
  await flushPromises()
  const find = (selector: string) => mounted.wrapper.find(`[data-test="${selector}"]`)
  const click = async (selector: string) => {
    await find(selector).trigger('click')
    await flushPromises()
  }
  const inDialog = (selector: string) => document.querySelector<HTMLButtonElement>(selector)
  const accept = async () => {
    inDialog('[data-test="confirm-accept"]')!.click()
    await flushPromises()
  }
  return { ...mounted, fetchList, find, click, inDialog, accept }
}

describe('SignInsCard', () => {
  describe('looking at it', () => {
    it('shows a placeholder while it asks', async () => {
      vi.spyOn(accountApi, 'fetchSignIns').mockReturnValue(new Promise(() => {}))
      const { wrapper } = await mountWithPlugins(SignInsCard, { signedIn: 'admin' })
      expect(wrapper.find('.v-skeleton-loader').exists()).toBe(true)
      expect(wrapper.find('[data-test="sign-in-list"]').exists()).toBe(false)
    })

    it('lists each browser by what it is, with when it signed in and was last active', async () => {
      const { wrapper } = await open([here, phone, old])
      const names = wrapper.findAll('[data-test="sign-in-name"]').map((name) => name.text())
      expect(names).toEqual(['Firefox on Linux', 'Safari on iOS', 'Unknown device'])
      const details = wrapper.findAll('[data-test="sign-in-details"]').map((item) => item.text())
      expect(details[0]).toMatch(/^Signed in .*2026.* · Last active .* · 192\.168\.1\.20$/)
      expect(details[1]).toMatch(/· 192\.168\.1\.31$/)
      // A sign-in from before the address was kept has none to show.
      expect(details[2]).toMatch(/^Signed in .*2026.* · Last active .*$/)
      expect(details[2]).not.toContain('·  ·')
      expect(details[2]?.split('·')).toHaveLength(2)
    })

    it('marks the browser being used, and offers to sign out only the others', async () => {
      const { wrapper } = await open()
      const items = wrapper.findAll('[data-test="sign-in"]')
      expect(items[0]?.find('[data-test="sign-in-current"]').text()).toBe('This browser')
      expect(items[0]?.find('[data-test="end-sign-in"]').exists()).toBe(false)
      expect(items[1]?.find('[data-test="sign-in-current"]').exists()).toBe(false)
      expect(items[1]?.find('[data-test="end-sign-in"]').attributes('aria-label')).toBe(
        'Sign out Safari on iOS',
      )
    })

    it('shows a phone as a phone, and anything else as a computer', async () => {
      const { wrapper } = await open()
      const icons = wrapper
        .findAll('[data-test="sign-in"]')
        .map((item) => item.find('svg').classes().join(' '))
      expect(icons[0]).toContain('lucide-monitor')
      expect(icons[1]).toContain('lucide-smartphone')
    })

    it('offers to sign out everywhere else only when there is somewhere else', async () => {
      const alone = await open([here])
      expect(alone.find('end-others').exists()).toBe(false)
      alone.wrapper.unmount()

      const shared = await open([here, phone])
      expect(shared.find('end-others').text()).toBe('Sign out everywhere else')
    })

    it('says why it can’t tell, and asks again when told to', async () => {
      const { find, click, fetchList } = await open(offline())
      expect(find('sign-ins-error').text()).toContain("Can't reach AresGate.")
      expect(find('sign-in-list').exists()).toBe(false)

      fetchList.mockResolvedValue([here])
      await click('sign-ins-retry')
      expect(find('sign-ins-error').exists()).toBe(false)
      expect(find('sign-in-name').text()).toBe('Firefox on Linux')
    })

    it('notes that the sign-in ended when the API says nobody is signed in', async () => {
      await open(new ApiError(401, "You're not signed in.", 'unauthenticated'))
      expect(useSessionStore()).toMatchObject({ signedIn: false, expired: true })
    })
  })

  describe('signing one out', () => {
    it('asks first, naming the browser, and does nothing if that is cancelled', async () => {
      const end = vi.spyOn(accountApi, 'endSignIn')
      const { click, inDialog } = await open()

      await click('end-sign-in')

      expect(inDialog('[data-test="confirm-title"]')?.textContent).toBe('Sign out Safari on iOS?')
      inDialog('[data-test="confirm-cancel"]')!.click()
      await flushPromises()
      expect(end).not.toHaveBeenCalled()
    })

    it('signs it out, says so, and lists again', async () => {
      const end = vi.spyOn(accountApi, 'endSignIn').mockResolvedValue()
      const { click, accept, find, fetchList, wrapper } = await open()
      fetchList.mockResolvedValue([here])

      await click('end-sign-in')
      await accept()

      expect(end).toHaveBeenCalledWith('phone', TOKEN)
      expect(find('sign-ins-notice').text()).toBe('Safari on iOS was signed out.')
      expect(wrapper.findAll('[data-test="sign-in"]')).toHaveLength(1)
      expect(fetchList).toHaveBeenCalledTimes(2)
    })

    it('says why it couldn’t, and lists again anyway', async () => {
      vi.spyOn(accountApi, 'endSignIn').mockRejectedValue(
        new ApiError(404, 'That sign-in has already ended.', 'not_found'),
      )
      const { click, accept, find, fetchList } = await open()
      fetchList.mockResolvedValue([here])

      await click('end-sign-in')
      await accept()

      expect(find('sign-ins-failure').text()).toBe('That sign-in has already ended.')
      expect(find('sign-ins-notice').exists()).toBe(false)
      expect(fetchList).toHaveBeenCalledTimes(2)
    })
  })

  describe('signing the others out', () => {
    it('asks first, and does nothing if that is cancelled', async () => {
      const end = vi.spyOn(accountApi, 'endOtherSignIns')
      const { click, inDialog } = await open()

      await click('end-others')

      expect(inDialog('[data-test="confirm-title"]')?.textContent).toBe('Sign out everywhere else?')
      inDialog('[data-test="confirm-cancel"]')!.click()
      await flushPromises()
      expect(end).not.toHaveBeenCalled()
    })

    it('signs them out, says how many, and lists again', async () => {
      const end = vi.spyOn(accountApi, 'endOtherSignIns').mockResolvedValue({ ended: 2 })
      const { click, accept, find, fetchList, wrapper } = await open([here, phone, old])
      fetchList.mockResolvedValue([here])

      await click('end-others')
      await accept()

      expect(end).toHaveBeenCalledWith(TOKEN)
      expect(find('sign-ins-notice').text()).toBe('2 other sign-ins were ended.')
      expect(wrapper.findAll('[data-test="sign-in"]')).toHaveLength(1)
      expect(find('end-others').exists()).toBe(false)
    })

    it('says so when it was one', async () => {
      vi.spyOn(accountApi, 'endOtherSignIns').mockResolvedValue({ ended: 1 })
      const { click, accept, find } = await open()

      await click('end-others')
      await accept()

      expect(find('sign-ins-notice').text()).toBe('1 other sign-in was ended.')
    })

    it('says why it couldn’t', async () => {
      vi.spyOn(accountApi, 'endOtherSignIns').mockRejectedValue(offline())
      const { click, accept, find } = await open()

      await click('end-others')
      await accept()

      expect(find('sign-ins-failure').text()).toBe("Can't reach AresGate.")
    })

    it('forgets an earlier notice when it is asked again', async () => {
      vi.spyOn(accountApi, 'endOtherSignIns').mockResolvedValueOnce({ ended: 1 })
      const { click, accept, find, fetchList } = await open()

      await click('end-others')
      await accept()
      expect(find('sign-ins-notice').exists()).toBe(true)

      fetchList.mockResolvedValue([here, phone])
      vi.spyOn(accountApi, 'endOtherSignIns').mockRejectedValue(offline())
      await click('end-others')
      await accept()

      expect(find('sign-ins-notice').exists()).toBe(false)
      expect(find('sign-ins-failure').exists()).toBe(true)
    })
  })
})
