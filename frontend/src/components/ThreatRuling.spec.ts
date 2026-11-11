import { ApiError } from '@/api/client'
import * as threatIntel from '@/api/threatIntel'
import ThreatRuling from '@/components/ThreatRuling.vue'
import { flushPromises, mountWithPlugins } from '@/test/mount'
import { SAFE_RULING } from '@/test/threatIntel'

async function mountRuling(ruling: threatIntel.Ruled | null = null) {
  const mounted = await mountWithPlugins(ThreatRuling, {
    signedIn: 'brian',
    props: { subject: '93.184.216.34', ruling },
  })
  const { wrapper } = mounted
  const find = (selector: string) => wrapper.find(`[data-test="${selector}"]`)
  const choose = async (verdict: 'safe' | 'suspicious') => {
    await find(`ruling-choice-${verdict}`).find('input').setValue(true)
  }
  const write = async (text: string) => {
    await find('ruling-note').find('textarea').setValue(text)
  }
  return { ...mounted, find, choose, write }
}

describe('ThreatRuling', () => {
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('offers the two rulings as radio buttons, and nothing is chosen at first', async () => {
    const { wrapper, find } = await mountRuling()

    const inputs = wrapper.findAll<HTMLInputElement>('input[type="radio"]')
    expect(inputs.map((input) => input.element.value)).toEqual(['safe', 'suspicious'])
    expect(inputs.every((input) => !input.element.checked)).toBe(true)
    expect(find('ruling-choices').find('legend').text()).toBe('What do you make of it?')
    expect(find('ruling-save').attributes('disabled')).toBeDefined()
    expect(find('ruling-take-back').exists()).toBe(false)
    expect(find('ruling-lead').text()).toContain('Services can be wrong either way')
  })

  it('saves what was chosen with the reason, trimmed, and says what was ruled', async () => {
    const ruled = { ...SAFE_RULING, note: 'A friend' }
    const rule = vi.spyOn(threatIntel, 'ruleOnThreat').mockResolvedValue(ruled)
    const { wrapper, find, choose, write } = await mountRuling()
    await choose('safe')
    await write('  A friend  ')
    expect(find('ruling-save').attributes('disabled')).toBeUndefined()

    await find('ruling-save').trigger('click')
    await flushPromises()

    expect(rule).toHaveBeenCalledWith('93.184.216.34', 'safe', 'A friend', 'a-security-token')
    expect(wrapper.emitted('changed')).toEqual([[ruled]])
  })

  it('saves with no reason as none', async () => {
    const rule = vi.spyOn(threatIntel, 'ruleOnThreat').mockResolvedValue(SAFE_RULING)
    const { find, choose, write } = await mountRuling()
    await choose('suspicious')
    await write('   ')

    await find('ruling-save').trigger('click')
    await flushPromises()

    expect(rule).toHaveBeenCalledWith('93.184.216.34', 'suspicious', null, 'a-security-token')
  })

  it('starts from what was ruled, says when, and has nothing to save until it is changed', async () => {
    const { wrapper, find, choose } = await mountRuling(SAFE_RULING)

    expect(find('ruling-choice-safe').find('input').element.checked).toBe(true)
    expect(find('ruling-note').find('textarea').element.value).toBe("My friend's server")
    expect(find('ruling-lead').text()).toMatch(
      /^You ruled it safe, .+ It stands over what the services say/,
    )
    expect(find('ruling-save').text()).toBe('Change my ruling')
    expect(find('ruling-save').attributes('disabled')).toBeDefined()

    await choose('suspicious')

    expect(find('ruling-save').attributes('disabled')).toBeUndefined()
    await choose('safe')
    expect(find('ruling-save').attributes('disabled')).toBeDefined()
    await find('ruling-note').find('textarea').setValue('Another reason')
    expect(find('ruling-save').attributes('disabled')).toBeUndefined()
    expect(wrapper.emitted('changed')).toBeUndefined()
  })

  it('does not say when a ruling was made where that is not known', async () => {
    const { find } = await mountRuling({ verdict: 'suspicious', note: null })

    expect(find('ruling-lead').text()).toMatch(/^You ruled it suspicious\. It stands over/)
  })

  it('takes a ruling back, and clears what was chosen', async () => {
    const back = vi.spyOn(threatIntel, 'takeBackRuling').mockResolvedValue(undefined)
    const { wrapper, find } = await mountRuling(SAFE_RULING)

    await find('ruling-take-back').trigger('click')
    await flushPromises()

    expect(back).toHaveBeenCalledWith('93.184.216.34', 'a-security-token')
    expect(wrapper.emitted('changed')).toEqual([[null]])
    expect(find('ruling-choice-safe').find('input').element.checked).toBe(false)
    expect(find('ruling-note').find('textarea').element.value).toBe('')
  })

  it('follows the ruling it is given when that changes', async () => {
    const { wrapper, find } = await mountRuling()

    await wrapper.setProps({ ruling: SAFE_RULING })
    expect(find('ruling-choice-safe').find('input').element.checked).toBe(true)

    await wrapper.setProps({ ruling: null })
    expect(find('ruling-choice-safe').find('input').element.checked).toBe(false)
    expect(find('ruling-note').find('textarea').element.value).toBe('')
  })

  it('says why it could not be saved, and says why it could not be taken back', async () => {
    const rule = vi
      .spyOn(threatIntel, 'ruleOnThreat')
      .mockRejectedValue(new ApiError(422, "10.0.0.5 isn't a public internet address."))
    const back = vi.spyOn(threatIntel, 'takeBackRuling').mockRejectedValue(new Error('offline'))
    const { wrapper, find, choose } = await mountRuling(SAFE_RULING)
    await choose('suspicious')

    await find('ruling-save').trigger('click')
    await flushPromises()
    expect(find('ruling-problem').text()).toContain("isn't a public internet address")

    await find('ruling-take-back').trigger('click')
    await flushPromises()

    expect(rule).toHaveBeenCalledTimes(1)
    expect(back).toHaveBeenCalledTimes(1)
    expect(find('ruling-problem').exists()).toBe(true)
    expect(wrapper.emitted('changed')).toBeUndefined()
  })

  it('does nothing twice while it is sending', async () => {
    let finish: (ruling: threatIntel.Ruling) => void = () => undefined
    const rule = vi.spyOn(threatIntel, 'ruleOnThreat').mockReturnValue(
      new Promise((resolve) => {
        finish = resolve
      }),
    )
    const back = vi.spyOn(threatIntel, 'takeBackRuling').mockResolvedValue(undefined)
    const { wrapper, find, choose } = await mountRuling(SAFE_RULING)
    await choose('suspicious')
    const vm = wrapper.vm as unknown as {
      $: { setupState: { save: () => Promise<void>; takeBack: () => Promise<void> } }
    }

    const first = vm.$.setupState.save()
    await vm.$.setupState.save()
    await vm.$.setupState.takeBack()
    finish(SAFE_RULING)
    await first
    await flushPromises()

    expect(rule).toHaveBeenCalledTimes(1)
    expect(back).not.toHaveBeenCalled()
    expect(find('ruling-save').exists()).toBe(true)
  })

  it('does not save with nothing chosen', async () => {
    const rule = vi.spyOn(threatIntel, 'ruleOnThreat').mockResolvedValue(SAFE_RULING)
    const { wrapper } = await mountRuling()
    const vm = wrapper.vm as unknown as { $: { setupState: { save: () => Promise<void> } } }

    await vm.$.setupState.save()

    expect(rule).not.toHaveBeenCalled()
  })
})
