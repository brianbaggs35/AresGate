import * as responseApi from '@/api/incidentResponse'
import { ApiError } from '@/api/client'
import { flushPromises, mountWithPlugins } from '@/test/mount'
import { item, overview } from '@/test/incidentResponse'
import IncidentResponseView from '@/views/IncidentResponseView.vue'

const offline = () => new ApiError(0, "Can't reach AresGate.", 'offline')

async function open(answer: responseApi.ResponseOverview | Error = overview()) {
  const fetchIt = vi.spyOn(responseApi, 'fetchIncidentResponse')
  if (answer instanceof Error) fetchIt.mockRejectedValue(answer)
  else fetchIt.mockResolvedValue(answer)
  const mounted = await mountWithPlugins(IncidentResponseView, {
    signedIn: 'admin',
    withApp: true,
    route: '/incident-response',
  })
  await flushPromises()
  const find = (selector: string) => mounted.wrapper.find(`[data-test="${selector}"]`)
  return { ...mounted, fetchIt, find, text: (selector: string) => find(selector).text() }
}

const many = (count: number) =>
  Array.from({ length: count }, (_, number) =>
    item({ id: number + 1, title: `Incident ${number + 1}` }),
  )

describe('IncidentResponseView', () => {
  it('shows a placeholder while it asks, under its title', async () => {
    vi.spyOn(responseApi, 'fetchIncidentResponse').mockReturnValue(new Promise(() => {}))
    const { wrapper } = await mountWithPlugins(IncidentResponseView, { signedIn: 'admin' })

    expect(wrapper.find('[data-test="page-heading"]').text()).toBe('Incident response')
    expect(wrapper.find('[data-test="response-loading"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="range"]').exists()).toBe(false)
  })

  it('asks for the last seven days, and offers the range and Refresh once it has an answer', async () => {
    const { fetchIt, find } = await open()

    expect(fetchIt).toHaveBeenCalledWith('7d')
    expect(find('range').exists()).toBe(true)
    expect(find('refresh').exists()).toBe(true)
  })

  it('says when it could not be had, and asks again', async () => {
    const { find, fetchIt, text } = await open(offline())
    expect(text('response-error')).toContain("Can't reach AresGate.")
    fetchIt.mockResolvedValue(overview())

    await find('retry').trigger('click')
    await flushPromises()

    expect(find('response-error').exists()).toBe(false)
    expect(find('response-hero').exists()).toBe(true)
  })

  it('keeps what it had when asking again fails', async () => {
    const { find, fetchIt, text } = await open(overview({ needs_response: [item()] }))
    fetchIt.mockRejectedValue(offline())

    await find('refresh').trigger('click')
    await flushPromises()

    expect(text('response-stale')).toContain('What is shown is from before.')
    expect(find('response-hero').exists()).toBe(true)
  })

  describe('the answer at the top', () => {
    it('says how many need a response, urgently', async () => {
      const { find, text } = await open(overview({ needs_response: [item(), item({ id: 2 })] }))

      expect(text('response-hero-title')).toBe('2 incidents still need a response')
      expect(find('response-hero').attributes('data-tone')).toBe('urgent')
    })

    it('counts each group that has anything in it', async () => {
      const { find, text } = await open(
        overview({
          needs_response: [item()],
          banned: [item({ id: 2, state: 'banned' }), item({ id: 3, state: 'banned' })],
        }),
      )

      expect(text('count-needs_response')).toBe('Needs a response: 1')
      expect(text('count-banned')).toBe('Banned: 2')
      expect(find('count-blocked').exists()).toBe(false)
    })

    it('says so when everything has been answered', async () => {
      const { find, text } = await open(
        overview({ banned: [item({ state: 'banned', why: null })] }),
      )

      expect(text('response-hero-title')).toBe('Everything that matters has been answered')
      expect(find('response-hero').attributes('data-tone')).toBe('calm')
      expect(text('response-none-waiting')).toBe('Nothing is waiting for a response.')
    })

    it('says so when nothing serious went on, with no groups', async () => {
      const { find, text } = await open()

      expect(text('response-hero-title')).toBe('No serious incidents in the last 7 days')
      expect(find('response-hero').attributes('data-tone')).toBe('idle')
      expect(find('group-needs_response').exists()).toBe(false)
      expect(find('response-row').exists()).toBe(false)
    })
  })

  describe('the groups', () => {
    it('lists each in the group that says what was done, those that wait first', async () => {
      const { wrapper, find } = await open(
        overview({
          needs_response: [item({ id: 1, title: 'Waiting' })],
          banned: [item({ id: 2, title: 'Banned one', state: 'banned', why: null })],
          blocked: [item({ id: 3, title: 'Blocked one', state: 'blocked', why: null, blocked: 2 })],
        }),
      )

      const titles = wrapper
        .findAll('[data-test^="group-"]')
        .map((card) => card.attributes('data-test'))
      expect(titles).toEqual(['group-needs_response', 'group-banned', 'group-blocked'])
      expect(find('group-needs_response').text()).toContain('Waiting')
      expect(find('group-banned').text()).toContain('Banned one')
      expect(find('group-blocked').text()).toContain('The firewall turned it away 2 times.')
    })

    it('puts the first ten in a group, and the rest behind a button', async () => {
      const { wrapper, find, text } = await open(overview({ needs_response: many(14) }))

      expect(wrapper.findAll('[data-test="response-row"]')).toHaveLength(10)
      expect(text('more-needs_response')).toBe('Show 4 more')

      await find('more-needs_response').trigger('click')

      expect(wrapper.findAll('[data-test="response-row"]')).toHaveLength(14)
      expect(find('more-needs_response').exists()).toBe(false)
    })

    it('has no button for a group that fits', async () => {
      const { find } = await open(overview({ needs_response: many(10) }))

      expect(find('more-needs_response').exists()).toBe(false)
    })
  })

  describe('what it cannot see', () => {
    it('says nothing when both programs are connected', async () => {
      const { find } = await open(overview({ needs_response: [item()] }))

      expect(find('response-coverage').exists()).toBe(false)
    })

    it('says what is hidden when one is not, and leads to Integrations', async () => {
      const { find, text } = await open(
        overview({ needs_response: [item()] }, { crowdsec_connected: false }),
      )

      expect(text('response-coverage')).toContain("CrowdSec isn't connected")
      expect(find('response-connect').attributes('href')).toBe('/integrations')
    })
  })

  describe('the range', () => {
    it('asks again for another, and starts the groups short again', async () => {
      const { find, fetchIt, wrapper } = await open(overview({ needs_response: many(14) }))
      await find('more-needs_response').trigger('click')
      fetchIt.mockResolvedValue(overview({ needs_response: many(12) }, { days: 30 }))

      await find('range-30d').trigger('click')
      await flushPromises()

      expect(fetchIt).toHaveBeenLastCalledWith('30d')
      expect(wrapper.findAll('[data-test="response-row"]')).toHaveLength(10)
      expect(find('response-scope').text()).toContain('the last 30 days')
    })

    it('drops the answer to an earlier ask that comes after a later one', async () => {
      const { find, fetchIt, wrapper } = await open()
      let finishSlow: (value: responseApi.ResponseOverview) => void = () => {}
      fetchIt.mockReturnValueOnce(
        new Promise((resolve) => {
          finishSlow = resolve
        }),
      )
      fetchIt.mockResolvedValueOnce(overview({ banned: [item({ title: 'Newer' })] }))

      await find('range-24h').trigger('click')
      await find('range-30d').trigger('click')
      await flushPromises()
      finishSlow(overview({ banned: [item({ title: 'Older' })] }))
      await flushPromises()

      expect(wrapper.text()).toContain('Newer')
      expect(wrapper.text()).not.toContain('Older')
    })

    it('drops the failure of an earlier ask too', async () => {
      const { find, fetchIt, wrapper } = await open()
      let failSlow: (reason: Error) => void = () => {}
      fetchIt.mockReturnValueOnce(
        new Promise((_resolve, reject) => {
          failSlow = reject
        }),
      )
      fetchIt.mockResolvedValueOnce(overview())

      await find('range-24h').trigger('click')
      await find('range-30d').trigger('click')
      await flushPromises()
      failSlow(offline())
      await flushPromises()

      expect(wrapper.find('[data-test="response-stale"]').exists()).toBe(false)
    })
  })

  describe('the notes at the bottom', () => {
    it('says which incidents count', async () => {
      const { text } = await open()

      expect(text('response-scope')).toContain('medium severity or higher')
      expect(text('response-scope')).toContain('the last 7 days')
    })

    it('says how many there were when there are more than it holds', async () => {
      const { text } = await open(overview({ needs_response: many(3) }, { total: 450 }))

      expect(text('response-capped')).toBe('Showing the 3 most serious of 450 incidents.')
    })

    it('says nothing of it when it holds them all', async () => {
      const { find } = await open(overview({ needs_response: many(3) }))

      expect(find('response-capped').exists()).toBe(false)
    })
  })
})
