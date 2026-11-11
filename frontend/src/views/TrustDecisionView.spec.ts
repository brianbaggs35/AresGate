import { ApiError } from '@/api/client'
import * as trustApi from '@/api/trust'
import type { TrustDetail } from '@/api/trust'
import ConfirmDialog from '@/components/ConfirmDialog.vue'
import { flushPromises, mountWithPlugins } from '@/test/mount'
import { appliedIncident, trustDetail } from '@/test/trust'
import TrustDecisionView from '@/views/TrustDecisionView.vue'

const offline = () => new ApiError(0, "Can't reach AresGate.", 'offline')

async function open(answer: TrustDetail | Error = trustDetail({ id: 4 })) {
  const fetchIt = vi.spyOn(trustApi, 'fetchTrusted')
  if (answer instanceof Error) fetchIt.mockRejectedValue(answer)
  else fetchIt.mockResolvedValue(answer)
  const change = vi.spyOn(trustApi, 'changeTrust').mockResolvedValue(trustDetail({ id: 4 }))
  const revoke = vi.spyOn(trustApi, 'revokeTrust').mockResolvedValue(undefined)
  const mounted = await mountWithPlugins(TrustDecisionView, {
    route: '/trust/4',
    signedIn: 'admin',
    withApp: true,
  })
  await flushPromises()
  const find = (selector: string) => mounted.wrapper.find(`[data-test="${selector}"]`)
  const text = (selector: string) => find(selector).text()
  const inDialog = (selector: string) =>
    document.querySelector<HTMLButtonElement>(`[data-test="${selector}"]`)
  const confirming = () => mounted.wrapper.findComponent(ConfirmDialog).props('modelValue')
  return { ...mounted, fetchIt, change, revoke, find, text, inDialog, confirming }
}

describe('TrustDecisionView', () => {
  it('shows a placeholder while it asks', async () => {
    vi.spyOn(trustApi, 'fetchTrusted').mockReturnValue(new Promise(() => {}))
    const { wrapper } = await mountWithPlugins(TrustDecisionView, {
      route: '/trust/4',
      signedIn: 'admin',
    })

    expect(wrapper.find('[data-test="decision-loading"]').exists()).toBe(true)
  })

  it('asks for the decision in the address', async () => {
    const { fetchIt } = await open()

    expect(fetchIt).toHaveBeenCalledWith(4)
  })

  it('says what it is about, how much it is trusted, and what that means', async () => {
    const { text, wrapper } = await open()

    expect(wrapper.text()).toContain('Everything about 52.1.2.3')
    expect(text('decision-level')).toBe('Safe')
    expect(text('decision-info')).toContain('never raises an alarm')
    expect(text('decision-applied')).toContain('Kept 12 alerts in 2 incidents')
    expect(text('decision-applied')).toContain('for every program that reports it')
  })

  it('says it has not been applied to anything yet', async () => {
    const { text, find } = await open(trustDetail({ hits: 0, last_hit_at: null, applied_to: [] }))

    expect(text('decision-applied')).toContain('Not applied to anything yet')
    expect(find('decision-none').exists()).toBe(true)
    expect(find('decision-incidents').exists()).toBe(false)
  })

  it('lists the incidents it was applied to, each a link', async () => {
    const { wrapper } = await open(
      trustDetail({
        applied_to: [
          appliedIncident({ id: 7 }),
          appliedIncident({ id: 8, signals: 1, severity: 'low', status: 'resolved' }),
        ],
      }),
    )

    const links = wrapper.findAll('[data-test="applied-incident"]')
    expect(links).toHaveLength(2)
    expect(links[0]?.attributes('href')).toBe('/incidents/7')
    expect(links[0]?.text()).toContain('12 alerts')
    expect(links[1]?.text()).toContain('1 alert,')
  })

  it('says it is gone, without offering to try again, when it was taken back', async () => {
    const { find, text } = await open(new ApiError(404, 'There is no such decision.'))

    expect(text('decision-error')).toContain(
      'There is no such decision. It may have been taken back.',
    )
    expect(find('decision-error').find('button').exists()).toBe(false)
  })

  it('says so, and tries again, when it cannot be loaded', async () => {
    const { find, fetchIt, wrapper } = await open(offline())
    expect(find('decision-error').text()).toContain("Can't reach AresGate.")

    fetchIt.mockResolvedValue(trustDetail({ id: 4 }))
    await find('decision-error').find('button').trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('Everything about 52.1.2.3')
  })

  it('keeps showing what it has, and says it is from earlier, when a read fails', async () => {
    const { find, fetchIt, change } = await open()
    fetchIt.mockRejectedValue(offline())
    change.mockResolvedValue(trustDetail({ id: 4 }))

    await find('field-note').find('input').setValue('camera')
    await find('trust-form').trigger('submit')
    await flushPromises()
    await flushPromises()

    expect(find('decision-stale').text()).toContain('What is shown is from earlier.')
  })

  describe('changing it', () => {
    it('saves all of it, reads it again, and says what happens next', async () => {
      const { find, change, fetchIt, text } = await open()

      await find('field-note').find('input').setValue('my camera')
      await find('field-address').find('input').setValue('52.9.9.9')
      await find('trust-form').trigger('submit')
      await flushPromises()
      await flushPromises()

      expect(change).toHaveBeenCalledWith(
        4,
        { verdict: 'not_suspicious', note: 'my camera', address: '52.9.9.9' },
        'a-security-token',
      )
      expect(fetchIt).toHaveBeenCalledTimes(2)
      expect(text('decision-notice')).toBe('Saved. What it reaches is judged again.')
    })

    it('says why it could not be saved, and says nothing was saved', async () => {
      const { find, change, text } = await open()
      change.mockRejectedValue(new ApiError(409, 'Another decision says the same.'))

      await find('trust-form').trigger('submit')
      await flushPromises()
      await flushPromises()

      expect(text('trust-failure')).toBe('Another decision says the same.')
      expect(find('decision-notice').exists()).toBe(false)
    })

    it('starts the form again from what was saved when it is cancelled', async () => {
      const { find, fetchIt } = await open()

      await find('trust-cancel').trigger('click')
      await flushPromises()

      expect(fetchIt).toHaveBeenCalledTimes(2)
    })
  })

  describe('taking it back', () => {
    it('asks first', async () => {
      const { find, confirming, inDialog } = await open()

      await find('decision-revoke').trigger('click')

      expect(confirming()).toBe(true)
      expect(inDialog('confirm-message')?.textContent).toContain('Everything about 52.1.2.3')
      expect(inDialog('confirm-message')?.textContent).toContain('can raise alarms again')
    })

    it('does nothing if the question is cancelled', async () => {
      const { find, revoke, inDialog, confirming } = await open()
      await find('decision-revoke').trigger('click')

      inDialog('confirm-cancel')!.click()
      await flushPromises()

      expect(revoke).not.toHaveBeenCalled()
      expect(confirming()).toBe(false)
    })

    it('goes back to the list once it is taken back', async () => {
      const { find, revoke, inDialog, router } = await open()
      const push = vi.spyOn(router, 'push')
      await find('decision-revoke').trigger('click')

      inDialog('confirm-accept')!.click()
      await flushPromises()
      await flushPromises()

      expect(revoke).toHaveBeenCalledWith(4, 'a-security-token')
      expect(push).toHaveBeenCalledWith({ name: 'trust' })
    })

    it('says why it could not be taken back, and stays', async () => {
      const { find, revoke, inDialog, text, router, confirming } = await open()
      revoke.mockRejectedValue(offline())
      await find('decision-revoke').trigger('click')

      inDialog('confirm-accept')!.click()
      await flushPromises()
      await flushPromises()

      expect(text('trust-failure')).toContain("Can't reach AresGate.")
      expect(router.currentRoute.value.name).toBe('trust-decision')
      expect(confirming()).toBe(false)
    })
  })
})
