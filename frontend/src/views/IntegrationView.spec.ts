import { ApiError } from '@/api/client'
import * as integrationsApi from '@/api/integrations'
import type { CheckReport, Integration } from '@/api/integrations'
import { useSessionStore } from '@/stores/session'
import { call, integration, module, ntopngApi, opnsense } from '@/test/integrations'
import { flushPromises, mountWithPlugins } from '@/test/mount'
import ConnectionCard from '@/components/ConnectionCard.vue'
import { draftFrom } from '@/integrations'
import IntegrationView from '@/views/IntegrationView.vue'

const TOKEN = 'a-security-token'
const CONNECTED_AT = '2026-03-04T15:30:45Z'

/** ntopng once it has been connected and has worked. */
const working = (): Integration =>
  integration({
    status: 'connected',
    last_success_at: CONNECTED_AT,
    connections: [
      ntopngApi({
        url: 'http://192.168.1.2:3000',
        secrets_set: ['token'],
        status: 'connected',
        last_attempt_at: CONNECTED_AT,
        last_success_at: CONNECTED_AT,
      }),
    ],
  })

const passed = (after: Integration = working()): CheckReport => ({
  ok: true,
  checks: [{ connection: 'api', ok: true, message: 'ntopng answered. Interface 0 is eth0.' }],
  integration: after,
})

async function open(
  loaded: Integration | Error = integration(),
  { key = 'ntopng' }: { key?: string } = {},
) {
  const fetch = vi.spyOn(integrationsApi, 'fetchIntegration')
  if (loaded instanceof Error) fetch.mockRejectedValue(loaded)
  else fetch.mockResolvedValue(loaded)
  const save = vi.spyOn(integrationsApi, 'saveIntegration')
  const test = vi.spyOn(integrationsApi, 'testIntegration')
  const disconnect = vi.spyOn(integrationsApi, 'disconnectIntegration')
  const calls = vi
    .spyOn(integrationsApi, 'fetchCalls')
    .mockResolvedValue({ calls: [call()], next_before: null })
  const mounted = await mountWithPlugins(IntegrationView, {
    signedIn: 'admin',
    route: `/integrations/${key}`,
  })
  await flushPromises()
  const find = (selector: string) => mounted.wrapper.find(`[data-test="${selector}"]`)
  const type = async (selector: string, value: string) => {
    await find(selector).find('input').setValue(value)
  }
  const click = async (selector: string) => {
    await find(selector).trigger('click')
    await flushPromises()
  }
  const submit = async () => {
    await mounted.wrapper.find('form').trigger('submit')
    await flushPromises()
  }
  return { ...mounted, fetch, save, test, disconnect, calls, find, type, click, submit }
}

describe('IntegrationView', () => {
  describe('the page', () => {
    it('asks for the integration the address names', async () => {
      const { fetch } = await open(integration({ key: 'wazuh' }), { key: 'wazuh' })
      expect(fetch).toHaveBeenCalledWith('wazuh')
    })

    it('says what it is, how it is and what it provides', async () => {
      const { find, wrapper } = await open(working())
      expect(wrapper.find('h1').text()).toBe('ntopng')
      expect(find('page-description').text()).toBe('Who talks to whom on the network.')
      expect(find('status').text()).toBe('Connected')
      expect(find('integration-last-success').text()).toMatch(/^Last successful call .+ ago$/)
      expect(find('integration-last-success').find('time').attributes('datetime')).toBe(
        CONNECTED_AT,
      )
    })

    it('says nothing of a call that was never made', async () => {
      const { find } = await open()
      expect(find('integration-last-success').exists()).toBe(false)
      expect(find('status').text()).toBe('Not connected')
    })

    it('links to the official documentation, in a new tab that cannot reach back', async () => {
      const { find } = await open()
      const docs = find('docs')
      expect(docs.attributes('href')).toBe('https://www.ntop.org/guides/ntopng/')
      expect(docs.attributes('target')).toBe('_blank')
      expect(docs.attributes('rel')).toBe('noopener noreferrer')
      expect(docs.attributes('aria-label')).toBe('ntopng documentation (opens in a new tab)')
    })

    it('goes back to all of them', async () => {
      const { find } = await open()
      expect(find('back').attributes('href')).toBe('/integrations')
    })

    it('titles the browser’s tab with its name', async () => {
      await open()
      expect(document.title).toBe('ntopng · Integrations · AresGate')
    })

    it('opens the guide while nothing is connected, and closes it after', async () => {
      const fresh = await open()
      expect(fresh.wrapper.find('.v-expansion-panel--active').exists()).toBe(true)
      expect(fresh.wrapper.text()).toContain('Create a token in ntopng.')
      const set = await open(working())
      expect(set.wrapper.find('.v-expansion-panel--active').exists()).toBe(false)
    })

    it('opens and closes the guide when its title is chosen', async () => {
      const { wrapper } = await open(working())
      const open_ = () => wrapper.find('.v-expansion-panel--active').exists()
      expect(open_()).toBe(false)
      await wrapper.find('.v-expansion-panel-title').trigger('click')
      expect(open_()).toBe(true)
      await wrapper.find('.v-expansion-panel-title').trigger('click')
      expect(open_()).toBe(false)
    })

    it('takes in a form that a connection hands back', async () => {
      const { wrapper, find } = await open(working())
      const replacement = draftFrom(working().connections[0]!)
      replacement.url = 'http://192.168.1.77:3000'
      wrapper.findComponent(ConnectionCard).vm.$emit('update:modelValue', replacement)
      await flushPromises()
      expect(find('connection-url').find<HTMLInputElement>('input').element.value).toBe(
        'http://192.168.1.77:3000',
      )
      expect(find('unsaved').exists()).toBe(true)
    })

    it('has a form for each connection, and the log of its requests', async () => {
      const { find, calls } = await open(opnsense())
      expect(find('connection-api').exists()).toBe(true)
      expect(find('connection-zenarmor').exists()).toBe(true)
      expect(find('api-log').exists()).toBe(true)
      expect(calls).toHaveBeenCalledWith('opnsense', { limit: 25 })
    })
  })

  describe('when it cannot be shown', () => {
    it('shows placeholders while it loads', async () => {
      vi.spyOn(integrationsApi, 'fetchIntegration').mockReturnValue(new Promise(() => {}))
      const { wrapper } = await mountWithPlugins(IntegrationView, {
        signedIn: 'admin',
        route: '/integrations/ntopng',
      })
      expect(wrapper.find('[data-test="integration-loading"]').exists()).toBe(true)
      expect(wrapper.find('form').exists()).toBe(false)
    })

    it('says why it could not load, and tries again', async () => {
      const { fetch, find, click } = await open(new ApiError(0, "Can't reach AresGate.", 'offline'))
      expect(find('load-error-message').text()).toBe("Can't reach AresGate.")
      expect(find('page-heading').text()).toBe("Couldn't load this integration")
      expect(find('back').attributes('href')).toBe('/integrations')

      fetch.mockResolvedValue(integration())
      await click('retry')

      expect(find('integration-error').exists()).toBe(false)
      expect(find('page-heading').text()).toBe('ntopng')
    })

    it('says so when there is no such integration, without offering to try again', async () => {
      const { find } = await open(new ApiError(404, 'There is no such integration.', 'not_found'), {
        key: 'nothing',
      })
      expect(find('page-heading').text()).toBe('There is no such integration')
      expect(find('retry').exists()).toBe(false)
    })

    it('notes that the sign-in is over when the API says so', async () => {
      const { pinia } = await open(new ApiError(401, 'Sign in first.', 'unauthenticated'))
      expect(useSessionStore(pinia).expired).toBe(true)
    })

    it('loads the other one when the address changes to another integration', async () => {
      const { router, fetch, find } = await open()
      fetch.mockResolvedValue(integration({ key: 'wazuh', name: 'Wazuh' }))
      await router.push('/integrations/wazuh')
      await flushPromises()
      expect(fetch).toHaveBeenLastCalledWith('wazuh')
      expect(find('page-heading').text()).toBe('Wazuh')
    })
  })

  describe('connecting', () => {
    async function fillIn(opened: Awaited<ReturnType<typeof open>>) {
      await opened.type('connection-url', ' http://192.168.1.2:3000 ')
      await opened.type('field-token', 'a-token')
    }

    it('saves what was filled in, then tests it, and shows that it passed', async () => {
      const opened = await open()
      opened.save.mockResolvedValue(working())
      opened.test.mockResolvedValue(passed())
      await fillIn(opened)
      expect(opened.find('save').text()).toBe('Connect')

      await opened.submit()

      expect(opened.save).toHaveBeenCalledWith(
        'ntopng',
        {
          api: {
            url: 'http://192.168.1.2:3000',
            tls_mode: 'system',
            tls_ca_pem: null,
            tls_fingerprint: null,
            options: { auth: 'token', interface_id: '0' },
            disabled_modules: [],
            secrets: { token: 'a-token' },
          },
        },
        TOKEN,
      )
      expect(opened.test).toHaveBeenCalledWith('ntopng', TOKEN)
      expect(opened.find('report').text()).toContain('The test passed')
      expect(opened.find('report').text()).toContain('ntopng answered. Interface 0 is eth0.')
      expect(opened.find('status').text()).toBe('Connected')
      expect(opened.find('save').text()).toBe('Save and test')
      expect(opened.find('test').exists()).toBe(true)
      expect(opened.find('disconnect').exists()).toBe(true)
    })

    it('forgets the secret that was typed once it is saved', async () => {
      const opened = await open()
      opened.save.mockResolvedValue(working())
      opened.test.mockResolvedValue(passed())
      await fillIn(opened)
      await opened.submit()
      const token = opened.find('field-token').find<HTMLInputElement>('input')
      expect(token.element.value).toBe('')
      expect(token.attributes('placeholder')).toBe('Saved')
    })

    it('reloads the log after the test, which made requests', async () => {
      const opened = await open()
      opened.save.mockResolvedValue(working())
      opened.test.mockResolvedValue(passed())
      await fillIn(opened)
      await opened.submit()
      expect(opened.calls).toHaveBeenCalledTimes(2)
    })

    it('says why the test failed, and keeps what was saved', async () => {
      const opened = await open()
      const after = working()
      after.status = 'problem'
      opened.save.mockResolvedValue(after)
      opened.test.mockResolvedValue({
        ok: false,
        checks: [{ connection: 'api', ok: false, message: 'ntopng redirected to its login page.' }],
        integration: after,
      })
      await fillIn(opened)
      await opened.submit()
      expect(opened.find('report').text()).toContain('The test failed')
      expect(opened.find('report').text()).toContain('ntopng redirected to its login page.')
      expect(opened.find('status').text()).toBe('Problem')
    })

    it('says so when it was saved but the test could not be run', async () => {
      const opened = await open()
      opened.save.mockResolvedValue(working())
      opened.test.mockRejectedValue(new ApiError(0, "Can't reach AresGate.", 'offline'))
      await fillIn(opened)
      await opened.submit()
      expect(opened.find('failure').text()).toBe(
        "Saved, but the test couldn't run. Can't reach AresGate.",
      )
      expect(opened.find('report').exists()).toBe(false)
      expect(opened.find('save').text()).toBe('Save and test')
    })

    it('shows the field by field problems the API found, and moves to the first', async () => {
      const opened = await open()
      opened.save.mockRejectedValue(
        new ApiError(422, "AresGate couldn't use that.", 'invalid', [
          { path: ['connections', 'api', 'token'], message: 'Enter a value.' },
          {
            path: ['connections', 'api', 'url'],
            message: 'That address is not on a private network.',
          },
        ]),
      )
      await opened.type('connection-url', 'https://8.8.8.8')

      await opened.submit()

      expect(opened.find('problems').isVisible()).toBe(true)
      expect(opened.find('connection-url').text()).toContain(
        'That address is not on a private network.',
      )
      expect(opened.find('field-token').text()).toContain('Enter a value.')
      expect(opened.test).not.toHaveBeenCalled()
      expect(document.activeElement?.id).toBe('api-url')
    })

    it('moves to the summary when the problem has no field to go to', async () => {
      const opened = await open()
      opened.save.mockRejectedValue(
        new ApiError(422, "AresGate couldn't use that.", 'invalid', [
          { path: ['connections', 'api', 'auth'], message: 'Choose one of the options.' },
          { path: ['extra'], message: 'Something else is wrong.' },
        ]),
      )
      await opened.submit()
      expect(opened.find('problems').text()).toContain('Something else is wrong.')
      expect(document.activeElement).toBe(opened.find('problems').element)
    })

    it('hides the problems again once the next try gets further', async () => {
      const opened = await open()
      opened.save.mockRejectedValueOnce(
        new ApiError(422, 'No.', 'invalid', [
          { path: ['connections', 'api', 'url'], message: 'Enter a value.' },
        ]),
      )
      await opened.submit()
      expect(opened.find('problems').isVisible()).toBe(true)

      opened.save.mockResolvedValue(working())
      opened.test.mockResolvedValue(passed())
      await opened.submit()

      expect(opened.find('problems').isVisible()).toBe(false)
      expect(opened.find('connection-url').text()).not.toContain('Enter a value.')
    })

    it('says why a save failed when that is not about a field', async () => {
      const opened = await open()
      opened.save.mockRejectedValue(new ApiError(500, 'AresGate ran into a problem.', 'error'))
      await opened.submit()
      expect(opened.find('failure').text()).toBe('AresGate ran into a problem.')
      expect(opened.find('problems').isVisible()).toBe(false)
      expect(opened.find('save').attributes('disabled')).toBeUndefined()
    })

    it('notes that the sign-in is over when a save finds out', async () => {
      const opened = await open()
      opened.save.mockRejectedValue(new ApiError(401, 'Sign in first.', 'unauthenticated'))
      await opened.submit()
      expect(useSessionStore(opened.pinia).expired).toBe(true)
    })

    it('does not start a second save while one is going', async () => {
      const opened = await open()
      let finish: (value: Integration) => void = () => {}
      opened.save.mockReturnValue(
        new Promise<Integration>((resolve) => {
          finish = resolve
        }),
      )
      await opened.submit()
      await opened.submit()
      expect(opened.save).toHaveBeenCalledOnce()
      expect(opened.find('save').classes()).toContain('v-btn--loading')

      opened.test.mockResolvedValue(passed())
      finish(working())
      await flushPromises()
      expect(opened.find('save').classes()).not.toContain('v-btn--loading')
    })
  })

  describe('changing what is connected', () => {
    it('sends no secret that was not typed, so the kept ones stay', async () => {
      const opened = await open(working())
      opened.save.mockResolvedValue(working())
      opened.test.mockResolvedValue(passed())
      await opened.type('connection-url', 'http://192.168.1.3:3000')

      await opened.submit()

      const sent = opened.save.mock.calls[0]?.[1]
      expect(sent?.api?.secrets).toEqual({})
      expect(sent?.api?.url).toBe('http://192.168.1.3:3000')
    })

    it('sends a new secret when one is typed', async () => {
      const opened = await open(working())
      opened.save.mockResolvedValue(working())
      opened.test.mockResolvedValue(passed())
      await opened.type('field-token', 'a-new-token')
      await opened.submit()
      expect(opened.save.mock.calls[0]?.[1]?.api?.secrets).toEqual({ token: 'a-new-token' })
    })

    it('sends only the fields of the way of signing in that is chosen', async () => {
      const opened = await open(working())
      opened.save.mockResolvedValue(working())
      opened.test.mockResolvedValue(passed())
      await opened.find('field-auth').findAll('input')[1]?.setValue(true)
      await opened.type('field-username', 'reader')
      await opened.type('field-password', 'a-password')
      await opened.submit()
      const sent = opened.save.mock.calls[0]?.[1]?.api
      expect(sent?.options).toEqual({ auth: 'basic', username: 'reader', interface_id: '0' })
      expect(sent?.secrets).toEqual({ password: 'a-password' })
    })
  })

  describe('testing', () => {
    it('is not offered until something is connected', async () => {
      const { find } = await open()
      expect(find('test').exists()).toBe(false)
      expect(find('disconnect').exists()).toBe(false)
      expect(find('unsaved').exists()).toBe(false)
    })

    it('tests what is saved, and shows how it went', async () => {
      const opened = await open(working())
      opened.test.mockResolvedValue(passed())
      await opened.click('test')
      expect(opened.test).toHaveBeenCalledWith('ntopng', TOKEN)
      expect(opened.save).not.toHaveBeenCalled()
      expect(opened.find('report').text()).toContain('The test passed')
      expect(opened.calls).toHaveBeenCalledTimes(2)
    })

    it('says why it could not be run', async () => {
      const opened = await open(working())
      opened.test.mockRejectedValue(new ApiError(409, 'Connect it first.', 'conflict'))
      await opened.click('test')
      expect(opened.find('failure').text()).toBe('Connect it first.')
      expect(opened.find('report').exists()).toBe(false)
    })

    it('waits for changes to be saved, and says so', async () => {
      const opened = await open(working())
      expect(opened.find('test').attributes('disabled')).toBeUndefined()
      await opened.type('connection-url', 'http://192.168.1.9:3000')
      expect(opened.find('test').attributes('disabled')).toBeDefined()
      expect(opened.find('unsaved').text()).toContain("aren't saved")
      await opened.type('connection-url', 'http://192.168.1.2:3000')
      expect(opened.find('test').attributes('disabled')).toBeUndefined()
      expect(opened.find('unsaved').exists()).toBe(false)
    })

    it('takes in what testing found without losing what is being typed', async () => {
      const opened = await open(opnsense())
      opened.save.mockResolvedValue(opnsense())
      const found = opnsense({ status: 'connected' })
      found.connections[0]!.modules = [
        module({ key: 'firewall', label: 'Firewall and system', state: 'running' }),
        module({ key: 'suricata', label: 'Suricata', state: 'running' }),
        module({ key: 'crowdsec', label: 'CrowdSec', state: 'not_installed' }),
      ]
      found.connections[0]!.url = 'https://192.168.1.1'
      found.connections[0]!.status = 'connected'
      opened.test.mockResolvedValue({ ok: true, checks: [], integration: found })
      await opened.type('connection-url', 'https://192.168.1.1')
      await opened.submit()
      const states = opened.wrapper
        .findAll('[data-test="module-state"]')
        .map((state) => state.text())
      expect(states).toEqual(['Running', 'Running', 'Not installed'])
    })
  })

  describe('a connection that not everyone has', () => {
    const switchOn = async (opened: Awaited<ReturnType<typeof open>>) => {
      await opened
        .find('connection-zenarmor')
        .find('[data-test="connection-enabled"] input')
        .setValue(true)
      await opened
        .find('connection-zenarmor')
        .find('[data-test="connection-url"] input')
        .setValue('https://192.168.1.1:8090')
    }

    it('is left out of what is saved unless it is switched on', async () => {
      const opened = await open(opnsense())
      opened.save.mockResolvedValue(opnsense())
      opened.test.mockResolvedValue(passed())
      await opened.submit()
      expect(Object.keys(opened.save.mock.calls[0]?.[1] ?? {})).toEqual(['api'])
    })

    it('is saved along with the other when it is switched on', async () => {
      const opened = await open(opnsense())
      opened.save.mockResolvedValue(opnsense())
      opened.test.mockResolvedValue(passed())
      await switchOn(opened)
      await opened.submit()
      expect(Object.keys(opened.save.mock.calls[0]?.[1] ?? {})).toEqual(['api', 'zenarmor'])
    })

    it('names the connection of each check when there are several', async () => {
      const opened = await open(opnsense())
      opened.save.mockResolvedValue(opnsense())
      opened.test.mockResolvedValue({
        ok: false,
        checks: [
          { connection: 'api', ok: true, message: 'OPNsense answered.' },
          { connection: 'zenarmor', ok: false, message: 'Zenarmor answered 403.' },
        ],
        integration: opnsense(),
      })
      await opened.submit()
      const checks = opened.wrapper.findAll('[data-test="check"]').map((check) => check.text())
      expect(checks).toEqual([
        'OPNsense API: OPNsense answered.',
        'Zenarmor API: Zenarmor answered 403.',
      ])
    })

    it('puts a problem with a whole connection on its card', async () => {
      const opened = await open(opnsense())
      opened.save.mockRejectedValue(
        new ApiError(422, 'No.', 'invalid', [
          { path: ['connections', 'zenarmor'], message: 'Fill in this connection.' },
        ]),
      )
      await switchOn(opened)
      await opened.submit()
      expect(opened.find('connection-zenarmor').text()).toContain('Fill in this connection.')
    })
  })

  describe('disconnecting', () => {
    const inDialog = (selector: string) =>
      document.querySelector<HTMLElement>(`[data-test="${selector}"]`)
    /** Vuetify keeps a dialog's content once it has been shown, and only hides it. */
    const isOpen = () =>
      document.querySelector('.v-overlay--active [data-test="confirm-dialog"]') !== null
    const choose = async (selector: string) => {
      inDialog(selector)!.click()
      await flushPromises()
    }

    it('asks first', async () => {
      const opened = await open(working())
      expect(isOpen()).toBe(false)

      await opened.click('disconnect')

      expect(inDialog('confirm-title')?.textContent).toBe('Disconnect ntopng?')
      expect(inDialog('confirm-message')?.textContent).toContain('Nothing changes on ntopng itself')
      expect(inDialog('confirm-accept')?.className).toContain('bg-error')
      expect(opened.disconnect).not.toHaveBeenCalled()
    })

    it('gives the keyboard back when it is cancelled', async () => {
      const opened = await open(working())
      ;(opened.find('disconnect').element as HTMLElement).focus()
      await opened.click('disconnect')

      await choose('confirm-cancel')

      await vi.waitFor(() => {
        expect(isOpen()).toBe(false)
        expect(document.activeElement).toBe(opened.find('disconnect').element)
      })
    })

    it('forgets the connection, and shows it as it is now', async () => {
      const opened = await open(working())
      opened.disconnect.mockResolvedValue(undefined)
      await opened.click('disconnect')
      opened.fetch.mockResolvedValue(integration())

      await choose('confirm-accept')

      expect(opened.disconnect).toHaveBeenCalledWith('ntopng', TOKEN)
      await vi.waitFor(() => {
        expect(isOpen()).toBe(false)
      })
      expect(opened.find('notice').text()).toBe(
        'ntopng is disconnected. AresGate forgot its addresses and keys.',
      )
      expect(opened.find('status').text()).toBe('Not connected')
      expect(opened.find('save').text()).toBe('Connect')
      expect(opened.find('disconnect').exists()).toBe(false)
      expect(opened.wrapper.find('.v-expansion-panel--active').exists()).toBe(true)
    })

    it('says why it could not, on the page', async () => {
      const opened = await open(working())
      opened.disconnect.mockRejectedValue(new ApiError(404, "It isn't connected.", 'not_found'))
      await opened.click('disconnect')

      await choose('confirm-accept')

      await vi.waitFor(() => {
        expect(isOpen()).toBe(false)
      })
      expect(opened.find('failure').text()).toBe("It isn't connected.")
      expect(opened.find('notice').exists()).toBe(false)
    })

    it('does not let anything else be done while it is going', async () => {
      const opened = await open(working())
      let finish: () => void = () => {}
      opened.disconnect.mockReturnValue(
        new Promise<undefined>((resolve) => {
          finish = () => {
            resolve(undefined)
          }
        }),
      )
      await opened.click('disconnect')
      await choose('confirm-accept')
      expect(opened.find('test').attributes('disabled')).toBeDefined()
      expect(opened.find('save').attributes('disabled')).toBeDefined()
      expect(inDialog('confirm-cancel')?.hasAttribute('disabled')).toBe(true)
      opened.fetch.mockResolvedValue(integration())
      finish()
      await flushPromises()
    })
  })
})
