import { VRadioGroup, VSlider, VSwitch, VTextarea, VTextField } from 'vuetify/components'

import { ApiError } from '@/api/client'
import * as settingsApi from '@/api/threatSettings'
import { flushPromises, mountWithPlugins } from '@/test/mount'
import { threatPreview, threatSettings } from '@/test/threats'
import ThreatSettingsView from '@/views/ThreatSettingsView.vue'

const settle = () => vi.advanceTimersByTimeAsync(0)
const offline = () => new ApiError(0, "Can't reach AresGate.", 'offline')

async function open(kept: settingsApi.ThreatSettings | Error = threatSettings()) {
  const fetchIt = vi.spyOn(settingsApi, 'fetchThreatSettings')
  if (kept instanceof Error) fetchIt.mockRejectedValue(kept)
  else fetchIt.mockResolvedValue(kept)
  const ask = vi.spyOn(settingsApi, 'previewThreatSettings').mockResolvedValue(threatPreview())
  const save = vi.spyOn(settingsApi, 'saveThreatSettings')
  const mounted = await mountWithPlugins(ThreatSettingsView, { signedIn: 'admin', withApp: true })
  await flushPromises()
  // From here the pause before the page asks is ours to wait out.
  vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] })
  const find = (selector: string) => mounted.wrapper.find(`[data-test="${selector}"]`)
  const sliders = () => mounted.wrapper.findAllComponents(VSlider)
  const move = async (to: number) => {
    sliders()[0]?.vm.$emit('update:modelValue', to)
    await settle()
  }
  const wait = async () => {
    await vi.advanceTimersByTimeAsync(400)
    await settle()
  }
  return { ...mounted, fetchIt, ask, save, find, sliders, move, wait }
}

describe('ThreatSettingsView', () => {
  afterEach(() => {
    vi.useRealTimers()
  })

  it('shows a placeholder while it asks', async () => {
    vi.spyOn(settingsApi, 'fetchThreatSettings').mockReturnValue(new Promise(() => {}))
    const { wrapper } = await mountWithPlugins(ThreatSettingsView, { signedIn: 'admin' })

    expect(wrapper.find('[data-test="threat-settings-loading"]').exists()).toBe(true)
  })

  it('shows how they are kept', async () => {
    const { sliders, wrapper } = await open(
      threatSettings({ threat_from: 70, clear_from: 90, exposure: 'some', exposed_ports: [22] }),
    )

    expect(sliders()[0]?.props('modelValue')).toBe(70)
    expect(sliders()[1]?.props('modelValue')).toBe(90)
    expect(wrapper.findComponent(VRadioGroup).props('modelValue')).toBe('some')
    expect(wrapper.find('[data-test="effect-idle"]').text()).toBe(
      'Change something above to see what it would do.',
    )
  })

  it('asks what a change would do once, a moment after the last one', async () => {
    const { ask, move, wait, find } = await open()

    await move(70)
    await move(75)
    await vi.advanceTimersByTimeAsync(399)
    expect(ask).not.toHaveBeenCalled()
    await wait()

    expect(ask).toHaveBeenCalledTimes(1)
    expect(ask).toHaveBeenCalledWith(
      expect.objectContaining({ threat_from: 75 }),
      'a-security-token',
    )
    expect(find('effect-sentence').text()).toBe(
      'Saving would change the lanes by +1 threat, −1 suspect.',
    )
  })

  it('withdraws the question and its answer when the change is undone', async () => {
    const { ask, move, wait, find } = await open()
    await move(70)
    await wait()
    expect(find('effect-table').exists()).toBe(true)

    await move(65)
    await settle()

    expect(find('effect-table').exists()).toBe(false)
    expect(ask).toHaveBeenCalledTimes(1)
  })

  it('says it when the question cannot be answered', async () => {
    const { ask, move, wait, find } = await open()
    ask.mockRejectedValue(offline())

    await move(70)
    await wait()

    expect(find('effect-failure').text()).toBe("Can't reach AresGate.")
    expect(find('effect-table').exists()).toBe(false)
  })

  it('drops the answer to an older question', async () => {
    const { ask, move, wait, find } = await open()
    let late: (found: settingsApi.ThreatPreview) => void = () => {}
    ask.mockReturnValueOnce(new Promise((resolve) => (late = resolve)))
    await move(70)
    await wait()
    ask.mockResolvedValueOnce(
      threatPreview({ after: { threats: 9, suspects: 5, background: 50, cleared: 40, muted: 4 } }),
    )
    await move(80)
    await wait()
    late(threatPreview())
    await settle()

    expect(find('effect-threats').find('[data-test="effect-after"]').text()).toBe('9')
  })

  it('drops the failure of an older question too', async () => {
    const { ask, move, wait, find } = await open()
    let fail: (reason: Error) => void = () => {}
    ask.mockReturnValueOnce(new Promise((_, reject) => (fail = reject)))
    await move(70)
    await wait()
    await move(80)
    await wait()
    fail(offline())
    await settle()

    expect(find('effect-failure').exists()).toBe(false)
    expect(find('effect-table').exists()).toBe(true)
  })

  it('keeps all of it, and says so', async () => {
    const { save, move, wait, find, wrapper } = await open()
    save.mockResolvedValue(threatSettings({ threat_from: 70, updated_at: '2026-11-05T00:00:00Z' }))
    await move(70)
    await wait()

    await find('effect-save').trigger('click')
    await settle()

    expect(save).toHaveBeenCalledWith(
      {
        threat_from: 70,
        ai_may_clear: true,
        clear_from: 80,
        ai_confirms: true,
        exposure: 'unknown',
        exposed_ports: [],
        notes: '',
      },
      'a-security-token',
    )
    expect(find('effect-saved').exists()).toBe(true)
    expect(find('effect-table').exists()).toBe(false)
    expect(wrapper.findAllComponents(VSlider)[0]?.props('modelValue')).toBe(70)
  })

  it('says why it could not be kept, and keeps the draft', async () => {
    const { save, move, wait, find, sliders } = await open()
    save.mockRejectedValue(offline())
    await move(70)
    await wait()

    await find('effect-save').trigger('click')
    await settle()

    expect(find('effect-failure').text()).toBe("Can't reach AresGate.")
    expect(sliders()[0]?.props('modelValue')).toBe(70)
  })

  it('goes back to what is kept when the changes are discarded', async () => {
    const { move, wait, find, sliders } = await open()
    await move(70)
    await wait()

    await find('effect-discard').trigger('click')
    await settle()

    expect(sliders()[0]?.props('modelValue')).toBe(65)
    expect(find('effect-table').exists()).toBe(false)
  })

  it('takes a change to how sure the AI has to be, and to the ports that are open', async () => {
    const { wrapper, ask, wait, sliders } = await open()

    sliders()[1]?.vm.$emit('update:modelValue', 90)
    await settle()
    await wait()
    wrapper.findComponent(VRadioGroup).vm.$emit('update:modelValue', 'some')
    await settle()
    wrapper.findComponent(VTextField).vm.$emit('update:modelValue', '443, 22')
    await settle()
    await wait()

    expect(ask).toHaveBeenLastCalledWith(
      expect.objectContaining({ clear_from: 90, exposure: 'some', exposed_ports: [22, 443] }),
      'a-security-token',
    )
  })

  it('takes a change to any of the settings', async () => {
    const { wrapper, ask, wait } = await open()

    wrapper.findAllComponents(VSwitch)[0]?.vm.$emit('update:modelValue', false)
    await settle()
    await wait()
    wrapper.findAllComponents(VSwitch)[1]?.vm.$emit('update:modelValue', false)
    wrapper.findComponent(VRadioGroup).vm.$emit('update:modelValue', 'none')
    wrapper.findComponent(VTextarea).vm.$emit('update:modelValue', 'A web server')
    await settle()
    await wait()

    expect(ask).toHaveBeenLastCalledWith(
      expect.objectContaining({
        ai_may_clear: false,
        ai_confirms: false,
        exposure: 'none',
        notes: 'A web server',
      }),
      'a-security-token',
    )
  })

  it('says why it could not load, and tries again on request', async () => {
    const { find, fetchIt } = await open(offline())
    // Nothing here waits on the pause, and flushing promises needs the real clock.
    vi.useRealTimers()

    expect(find('threat-settings-error').text()).toContain("Can't reach AresGate.")

    fetchIt.mockResolvedValue(threatSettings())
    await find('retry').trigger('click')
    await flushPromises()

    expect(find('threat-settings-error').exists()).toBe(false)
    expect(find('threat-level-card').exists()).toBe(true)
  })

  it('stops asking when it is left', async () => {
    const { move, wrapper, ask } = await open()
    await move(70)

    wrapper.unmount()
    await vi.advanceTimersByTimeAsync(1000)

    expect(ask).not.toHaveBeenCalled()
  })
})
