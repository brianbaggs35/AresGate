import { ApiError } from '@/api/client'
import * as threatsApi from '@/api/threats'
import KindSuggestion from '@/components/KindSuggestion.vue'
import { flushPromises, mountWithPlugins } from '@/test/mount'
import { familyDetail, suggestion } from '@/test/threats'

async function open(offer = suggestion(), label?: string) {
  const call = vi.spyOn(threatsApi, 'callFamily').mockResolvedValue(familyDetail())
  const dismiss = vi.spyOn(threatsApi, 'dismissSuggestion').mockResolvedValue(familyDetail())
  const mounted = await mountWithPlugins(KindSuggestion, {
    signedIn: 'admin',
    props: { id: 7, suggestion: offer, label },
  })
  const find = (selector: string) => mounted.wrapper.find(`[data-test="${selector}"]`)
  return { ...mounted, call, dismiss, find }
}

describe('KindSuggestion', () => {
  it('offers to set a kind aside for good, says why and what it would move', async () => {
    const { wrapper, find } = await open()

    expect(wrapper.text()).toContain('Always treat this kind as background?')
    expect(find('suggestion-reason').text()).toContain('You have closed 12 of the 12 incidents')
    expect(find('suggestion-moves').text()).toBe(
      'That would set aside 4 incidents that are going on now. Nothing changes unless you say so.',
    )
    expect(find('suggestion-take').text()).toBe('Always background')
    expect(find('suggestion-kind').exists()).toBe(false)
  })

  it('offers to keep a kind from being set aside, and says what would come back', async () => {
    const { wrapper, find } = await open(
      suggestion({ call: 'watch', moves: 1, loud: 3, benign: 0 }),
    )

    expect(wrapper.text()).toContain('Never set this kind aside?')
    expect(find('suggestion-moves').text()).toContain(
      'That would bring 1 incident that is set aside back into view.',
    )
    expect(find('suggestion-take').text()).toBe('Never set aside')
  })

  it('names the kind, with a link to its page, where it is not the page that is open', async () => {
    const { find } = await open(suggestion(), 'ET SCAN Potential SSH Scan')

    expect(find('suggestion-kind').text()).toBe('ET SCAN Potential SSH Scan')
    expect(find('suggestion-kind').find('a').attributes('href')).toBe('/threats/kinds/7')
  })

  it('takes the offer only when you say so, as your word on the kind', async () => {
    const { wrapper, find, call } = await open()
    expect(call).not.toHaveBeenCalled()

    await find('suggestion-take').trigger('click')
    await flushPromises()

    expect(call).toHaveBeenCalledWith(7, 'background', 'a-security-token')
    expect(wrapper.emitted('changed')).toHaveLength(1)
  })

  it('says not now, which is kept', async () => {
    const { wrapper, find, dismiss, call } = await open()

    await find('suggestion-dismiss').trigger('click')
    await flushPromises()

    expect(dismiss).toHaveBeenCalledWith(7, 'a-security-token')
    expect(call).not.toHaveBeenCalled()
    expect(wrapper.emitted('changed')).toHaveLength(1)
  })

  it('says why it could not be taken or put off', async () => {
    const { find, call, dismiss } = await open()
    call.mockRejectedValue(new ApiError(0, "Can't reach AresGate.", 'offline'))
    dismiss.mockRejectedValue(new ApiError(0, 'Try again.', 'offline'))

    await find('suggestion-take').trigger('click')
    await flushPromises()
    expect(find('suggestion-failure').text()).toBe("Can't reach AresGate.")

    await find('suggestion-dismiss').trigger('click')
    await flushPromises()
    expect(find('suggestion-failure').text()).toBe('Try again.')
  })
})
