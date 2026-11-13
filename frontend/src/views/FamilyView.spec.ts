import { ApiError } from '@/api/client'
import * as threatsApi from '@/api/threats'
import { flushPromises, mountWithPlugins } from '@/test/mount'
import { familyDetail, suggestion } from '@/test/threats'
import FamilyView from '@/views/FamilyView.vue'

const offline = () => new ApiError(0, "Can't reach AresGate.", 'offline')

async function open(found: threatsApi.FamilyDetail | Error = familyDetail()) {
  const fetchIt = vi.spyOn(threatsApi, 'fetchFamily')
  if (found instanceof Error) fetchIt.mockRejectedValue(found)
  else fetchIt.mockResolvedValue(found)
  const call = vi.spyOn(threatsApi, 'callFamily')
  const judge = vi.spyOn(threatsApi, 'judgeFamily')
  const mounted = await mountWithPlugins(FamilyView, {
    signedIn: 'admin',
    withApp: true,
    route: '/threats/kinds/7',
  })
  await flushPromises()
  const find = (selector: string) => mounted.wrapper.find(`[data-test="${selector}"]`)
  return { ...mounted, fetchIt, call, judge, find }
}

describe('FamilyView', () => {
  it('asks for the kind that is in the address of the page', async () => {
    const { fetchIt } = await open()

    expect(fetchIt).toHaveBeenCalledWith(7)
  })

  it('asks for the kind again once your review of its judgement is answered', async () => {
    const { fetchIt, wrapper } = await open()
    fetchIt.mockClear()

    wrapper.findComponent({ name: 'ReviewStrip' }).vm.$emit('answered')
    await flushPromises()

    expect(fetchIt).toHaveBeenCalledWith(7)
  })

  it('shows a skeleton until the answer arrives', async () => {
    vi.spyOn(threatsApi, 'fetchFamily').mockReturnValue(new Promise(() => {}))
    const { wrapper } = await mountWithPlugins(FamilyView, {
      signedIn: 'admin',
      route: '/threats/kinds/7',
    })

    expect(wrapper.find('[data-test="kind-loading"]').exists()).toBe(true)
  })

  it('names the kind, where it is from, and leads back to the kinds', async () => {
    const { wrapper, find } = await open()

    expect(wrapper.find('h1').text()).toBe('ET SCAN Potential SSH Scan from <address>')
    expect(wrapper.text()).toContain('From the internet, seen by OPNsense.')
    expect(find('back').attributes('href')).toBe('/threats/kinds')
  })

  it('says what is thought of it and why it is where it is', async () => {
    const { find } = await open()

    expect(find('judgement-class').text()).toBe('AI: Probe, 92% sure')
    expect(find('why').text()).toContain('92% sure this kind is a probe')
  })

  it('says nothing of a change when the kind is as it was judged', async () => {
    const { find } = await open()

    expect(find('changed').exists()).toBe(false)
  })

  it('says how a kind has changed since it was judged, and that the AI will look again', async () => {
    const { find, wrapper } = await open(
      familyDetail({
        changed_at: new Date(Date.now() - 10 * 60_000).toISOString(),
        changes: ['It now reaches destination ports it did not before: 3389.'],
      }),
    )

    expect(find('changed').text()).toContain('It has changed since it was judged')
    expect(wrapper.findAll('[data-test="change"]').map((item) => item.text())).toEqual([
      'It now reaches destination ports it did not before: 3389.',
    ])
    expect(find('changed').text()).toContain('First noticed 10 minutes ago')
    expect(find('changed').text()).toContain('The AI will be asked about it again')
  })

  it('says that your word stands on a kind you called that has changed', async () => {
    const { find } = await open(
      familyDetail({
        owner_call: 'background',
        changed_at: new Date().toISOString(),
        changes: ['It comes from many more addresses: 4 when it was judged, 40 now.'],
      }),
    )

    expect(find('changed').text()).toContain('Your word on it stands')
  })

  it('offers what you keep deciding, and asks again once you have taken or put it off', async () => {
    const { find, fetchIt } = await open(familyDetail({ suggestion: suggestion() }))
    vi.spyOn(threatsApi, 'dismissSuggestion').mockResolvedValue(familyDetail())
    expect(find('suggestion-reason').text()).toContain('You have closed 12')
    fetchIt.mockClear()

    await find('suggestion-dismiss').trigger('click')
    await flushPromises()

    expect(fetchIt).toHaveBeenCalledWith(7)
  })

  it('offers nothing when there is nothing to offer', async () => {
    const { find } = await open()

    expect(find('suggestion').exists()).toBe(false)
  })

  it('leaves out the reasons when there are none', async () => {
    const { find } = await open(familyDetail({ why: [] }))

    expect(find('why-card').exists()).toBe(false)
  })

  it('lists its incidents, and leads to them in Incidents', async () => {
    const { find, wrapper } = await open()

    expect(find('sample').text()).toContain(
      '41 incidents are going on, 3,200 alerts in all from 41 addresses.',
    )
    expect(wrapper.findAll('[data-test="incident-card"]')).toHaveLength(1)
    expect(find('sample-all').attributes('href')).toBe('/incidents?family=7')
  })

  it('says one incident and one address in the singular', async () => {
    const { find } = await open(familyDetail({ incidents: 1, alerts: 1, actors: 1 }))

    expect(find('sample').text()).toContain(
      '1 incident is going on, 1 alert in all from 1 address.',
    )
  })

  it('says when none of its incidents are going on', async () => {
    const { find, wrapper } = await open(familyDetail({ sample: [], incidents: 0 }))

    expect(find('sample-empty').exists()).toBe(true)
    expect(wrapper.findAll('[data-test="incident-card"]')).toHaveLength(0)
  })

  it('asks again when an incident in the list is given a verdict', async () => {
    const { wrapper, fetchIt } = await open()

    await wrapper.findComponent({ name: 'IncidentCard' }).vm.$emit('judged', {})
    await flushPromises()

    expect(fetchIt).toHaveBeenCalledTimes(2)
  })

  it('drops the failure of a refresh that something newer has taken the place of', async () => {
    const { wrapper, find, fetchIt, call } = await open()
    let fail: (reason: Error) => void = () => {}
    fetchIt.mockReturnValueOnce(new Promise((_, reject) => (fail = reject)))
    call.mockResolvedValue(familyDetail({ owner_call: 'watch' }))

    wrapper.findComponent({ name: 'IncidentCard' }).vm.$emit('judged', {})
    await find('call-watch').trigger('click')
    await flushPromises()
    fail(offline())
    await flushPromises()

    expect(find('kind-stale').exists()).toBe(false)
    expect(find('judgement-owner').text()).toContain('You watch it.')
  })

  describe('your word on it', () => {
    it('keeps it and shows the kind as the server says it now is', async () => {
      const { find, call } = await open()
      call.mockResolvedValue(familyDetail({ owner_call: 'background' }))

      await find('call-background').trigger('click')
      await flushPromises()

      expect(call).toHaveBeenCalledWith(7, 'background', 'a-security-token')
      expect(find('judgement-owner').text()).toContain('You set it aside.')
    })

    it('takes it back', async () => {
      const { find, call } = await open(familyDetail({ owner_call: 'watch' }))
      call.mockResolvedValue(familyDetail())

      await find('call-clear').trigger('click')
      await flushPromises()

      expect(call).toHaveBeenCalledWith(7, null, 'a-security-token')
      expect(find('judgement-owner').exists()).toBe(false)
    })

    it('says why it could not be kept', async () => {
      const { find, call } = await open()
      call.mockRejectedValue(offline())

      await find('call-watch').trigger('click')
      await flushPromises()

      expect(find('judgement-failure').text()).toBe("Can't reach AresGate.")
    })
  })

  describe('asking the AI', () => {
    it('shows what it made of the kind', async () => {
      const { find, judge } = await open(familyDetail({ classification: null, confidence: null }))
      judge.mockResolvedValue({ ok: true, reason: null, family: familyDetail() })

      await find('judge').trigger('click')
      await flushPromises()

      expect(judge).toHaveBeenCalledWith(7, 'a-security-token')
      expect(find('judgement-class').text()).toBe('AI: Probe, 92% sure')
      expect(find('judgement-failure').exists()).toBe(false)
    })

    it('says why it could not be asked', async () => {
      const { find, judge } = await open()
      judge.mockResolvedValue({ ok: false, reason: 'AI is turned off.', family: familyDetail() })

      await find('judge').trigger('click')
      await flushPromises()

      expect(find('judgement-failure').text()).toBe('AI is turned off.')
    })

    it('says why the request failed', async () => {
      const { find, judge } = await open()
      judge.mockRejectedValue(offline())

      await find('judge').trigger('click')
      await flushPromises()

      expect(find('judgement-failure').text()).toBe("Can't reach AresGate.")
    })
  })

  describe('when it cannot be loaded', () => {
    it('says so, and tries again', async () => {
      const { find, fetchIt } = await open(offline())

      expect(find('kind-error').text()).toContain("Can't reach AresGate.")

      fetchIt.mockResolvedValue(familyDetail())
      await find('retry').trigger('click')
      await flushPromises()

      expect(find('kind-error').exists()).toBe(false)
      expect(find('judgement-card').exists()).toBe(true)
    })

    it('says a kind that is not there may have been removed, and does not offer to try again', async () => {
      const { find } = await open(new ApiError(404, 'No such kind.', 'not_found'))

      expect(find('kind-error').text()).toContain('No such kind. It may have been removed.')
      expect(find('retry').exists()).toBe(false)
    })

    it('keeps what it has while a refresh fails, and says so', async () => {
      vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval'] })
      try {
        const { find, fetchIt } = await open()
        fetchIt.mockRejectedValue(offline())

        vi.advanceTimersByTime(30_000)
        await flushPromises()

        expect(find('kind-stale').text()).toContain("Can't reach AresGate.")
        expect(find('judgement-card').exists()).toBe(true)

        fetchIt.mockResolvedValue(familyDetail())
        vi.advanceTimersByTime(30_000)
        await flushPromises()
        expect(find('kind-stale').exists()).toBe(false)
      } finally {
        vi.useRealTimers()
      }
    })

    it('does not let a refresh that was already on its way undo what was just said', async () => {
      vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval'] })
      try {
        const { find, fetchIt, call } = await open()
        let settle: (value: threatsApi.FamilyDetail) => void = () => {}
        call.mockReturnValue(new Promise((resolve) => (settle = resolve)))
        await find('call-background').trigger('click')
        fetchIt.mockResolvedValue(familyDetail())

        vi.advanceTimersByTime(30_000)
        await flushPromises()
        settle(familyDetail({ owner_call: 'background' }))
        await flushPromises()

        expect(find('judgement-owner').exists()).toBe(true)
      } finally {
        vi.useRealTimers()
      }
    })
  })
})
