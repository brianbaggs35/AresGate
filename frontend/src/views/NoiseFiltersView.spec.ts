import { VSelect, VSlider, VSwitch } from 'vuetify/components'

import { ApiError } from '@/api/client'
import * as noiseApi from '@/api/noise'
import NoiseGapCard from '@/components/NoiseGapCard.vue'
import NoiseThinCard from '@/components/NoiseThinCard.vue'
import { flushPromises, mountWithPlugins } from '@/test/mount'
import { noiseFilters, preview, source } from '@/test/noise'
import NoiseFiltersView from '@/views/NoiseFiltersView.vue'

const settle = () => vi.advanceTimersByTimeAsync(0)
const offline = () => new ApiError(0, "Can't reach AresGate.", 'offline')
// The gaps and the minimum as they are until the owner changes them, which the page sends too.
const KEPT_GAPS = { scan_gap_hours: 4, brute_force_gap_hours: 6, thin_low_signals: 1 }

async function open(kept: noiseApi.NoiseFilters | Error = noiseFilters()) {
  const fetchIt = vi.spyOn(noiseApi, 'fetchNoiseFilters')
  if (kept instanceof Error) fetchIt.mockRejectedValue(kept)
  else fetchIt.mockResolvedValue(kept)
  const ask = vi.spyOn(noiseApi, 'previewNoiseFilters').mockResolvedValue(preview())
  const save = vi.spyOn(noiseApi, 'saveNoiseFilters')
  const mounted = await mountWithPlugins(NoiseFiltersView, { signedIn: 'admin', withApp: true })
  await flushPromises()
  // From here the pause before the page asks is ours to wait out. `flushPromises` waits on a timer,
  // so it is `settle` that lets what is pending finish.
  vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] })
  const find = (selector: string) => mounted.wrapper.find(`[data-test="${selector}"]`)
  const slider = () => mounted.wrapper.findComponent(VSlider)
  const move = async (to: number) => {
    slider().vm.$emit('update:modelValue', to)
    await settle()
  }
  // Waits out the pause before the page asks what a change would do, then for the answer.
  const wait = async () => {
    await vi.advanceTimersByTimeAsync(400)
    await settle()
  }
  return { ...mounted, fetchIt, ask, save, find, slider, move, wait }
}

describe('NoiseFiltersView', () => {
  afterEach(() => {
    vi.useRealTimers()
  })

  describe('looking at them', () => {
    it('shows a placeholder while it asks', async () => {
      vi.spyOn(noiseApi, 'fetchNoiseFilters').mockReturnValue(new Promise(() => {}))
      const { wrapper } = await mountWithPlugins(NoiseFiltersView, { signedIn: 'admin' })

      expect(wrapper.find('[data-test="noise-loading"]').exists()).toBe(true)
    })

    it('shows how they are kept: the floor, each program, and inside', async () => {
      const { slider, wrapper } = await open(
        noiseFilters({
          confidence_floor: 50,
          quiet_inside: true,
          sources: [source({ floor: 'high' })],
        }),
      )

      expect(slider().props('modelValue')).toBe(50)
      expect(wrapper.findComponent(VSelect).props('modelValue')).toBe('high')
      expect(wrapper.findComponent(VSwitch).props('modelValue')).toBe(true)
      expect(wrapper.find('[data-test="effect-idle"]').text()).toBe(
        'Change something above to see what it would do.',
      )
    })

    it('links to the verdicts, which come first', async () => {
      const { find } = await open()

      expect(find('manage-verdicts').text()).toBe('Manage your 3 verdicts')
      expect(find('manage-verdicts').attributes('href')).toBe('/settings/verdicts')
    })

    it('says one verdict in the singular', async () => {
      const { find } = await open(noiseFilters({ verdicts: 1 }))

      expect(find('manage-verdicts').text()).toBe('Manage your 1 verdict')
    })

    it('shows the gaps and the minimum as they are kept', async () => {
      const { find } = await open(noiseFilters({ scan_gap_hours: 8, thin_low_signals: 3 }))

      expect(find('gap-sentence').text()).toContain('less than 8 hours')
      expect(find('thin-sentence').text()).toContain('once it has 3 of them')
    })

    it('says why it could not load, and tries again on request', async () => {
      const { find, fetchIt } = await open(offline())

      expect(find('noise-error').text()).toContain("Can't reach AresGate.")

      fetchIt.mockResolvedValue(noiseFilters())
      await find('noise-error').find('button').trigger('click')
      await settle()

      expect(find('noise-error').exists()).toBe(false)
      expect(find('floor-card').exists()).toBe(true)
    })
  })

  describe('seeing what a change would do', () => {
    it('asks once, a moment after the last change, with everything on the page', async () => {
      const { ask, move, wait, find } = await open()

      await move(40)
      await move(45)
      expect(ask).not.toHaveBeenCalled()
      expect(find('effect-card').find('[role="progressbar"]').exists()).toBe(true)

      await wait()

      expect(ask).toHaveBeenCalledTimes(1)
      expect(ask).toHaveBeenCalledWith(
        { ...KEPT_GAPS, confidence_floor: 45, quiet_inside: false, source_floors: {} },
        'a-security-token',
      )
      expect(find('effect-sentence').text()).toContain('2 incidents would need you instead of 5')
      expect(find('effect-save').attributes('disabled')).toBeUndefined()
    })

    it('asks about a program given a floor and about inside', async () => {
      const { ask, wrapper, wait } = await open()

      wrapper.findAllComponents(VSelect)[0]?.vm.$emit('update:modelValue', 'high')
      wrapper.findComponent(VSwitch).vm.$emit('update:modelValue', true)
      await settle()
      await wait()

      expect(ask).toHaveBeenCalledWith(
        {
          ...KEPT_GAPS,
          confidence_floor: 35,
          quiet_inside: true,
          source_floors: { wazuh: 'high' },
        },
        'a-security-token',
      )
    })

    it('asks about the gaps and the minimum as they are changed', async () => {
      const { ask, wrapper, wait } = await open()

      wrapper.findComponent(NoiseGapCard).vm.$emit('update:scanHours', 8)
      wrapper.findComponent(NoiseGapCard).vm.$emit('update:bruteForceHours', 2)
      wrapper.findComponent(NoiseThinCard).vm.$emit('update:modelValue', 3)
      await settle()
      await wait()

      expect(ask).toHaveBeenCalledWith(
        {
          confidence_floor: 35,
          quiet_inside: false,
          source_floors: {},
          scan_gap_hours: 8,
          brute_force_gap_hours: 2,
          thin_low_signals: 3,
        },
        'a-security-token',
      )
    })

    it('does not ask when the page goes back to what is kept, and drops what it was told', async () => {
      const { ask, move, wait, find } = await open()
      await move(45)
      await wait()
      expect(find('effect-table').exists()).toBe(true)

      await move(35)
      await wait()

      expect(ask).toHaveBeenCalledTimes(1)
      expect(find('effect-table').exists()).toBe(false)
      expect(find('effect-save').attributes('disabled')).toBeDefined()
    })

    it('does not ask at all if the change is undone before the pause is over', async () => {
      const { ask, move, wait } = await open()

      await move(45)
      await move(35)
      await wait()

      expect(ask).not.toHaveBeenCalled()
    })

    it('ignores the answer to an older question', async () => {
      const { ask, move, wait, find } = await open()
      let late: (value: noiseApi.Preview) => void = () => {}
      ask.mockReturnValueOnce(new Promise((resolve) => (late = resolve)))

      await move(45)
      await wait()
      ask.mockResolvedValueOnce(
        preview({ after: { ...preview().after, set_aside: preview().now.set_aside } }),
      )
      await move(50)
      await wait()
      late(preview())
      await settle()

      expect(ask).toHaveBeenCalledTimes(2)
      expect(find('effect-set-aside').find('[data-test="effect-after"]').text()).toBe('0')
    })

    it('ignores the failure of an older question', async () => {
      const { ask, move, wait, find } = await open()
      let late: (error: Error) => void = () => {}
      ask.mockReturnValueOnce(new Promise((_resolve, reject) => (late = reject)))

      await move(45)
      await wait()
      await move(50)
      await wait()
      late(offline())
      await settle()

      expect(find('effect-failure').exists()).toBe(false)
      expect(find('effect-table').exists()).toBe(true)
    })

    it('says why it could not work it out', async () => {
      const { ask, move, wait, find } = await open()
      ask.mockRejectedValue(offline())

      await move(45)
      await wait()

      expect(find('effect-failure').text()).toBe("Can't reach AresGate.")
      expect(find('effect-idle').text()).toBe("It couldn't be worked out.")
    })

    it('stops waiting when the page is left', async () => {
      const { ask, move, wrapper } = await open()
      await move(45)

      wrapper.unmount()
      await vi.advanceTimersByTimeAsync(1000)

      expect(ask).not.toHaveBeenCalled()
    })
  })

  describe('keeping them', () => {
    it('saves all of it with the security token, and shows what was kept', async () => {
      const { find, move, wait, save } = await open()
      save.mockResolvedValue(noiseFilters({ confidence_floor: 45 }))
      await move(45)
      await wait()

      await find('effect-save').trigger('click')
      await settle()

      expect(save).toHaveBeenCalledWith(
        { ...KEPT_GAPS, confidence_floor: 45, quiet_inside: false, source_floors: {} },
        'a-security-token',
      )
      expect(find('effect-saved').exists()).toBe(true)
      expect(find('effect-save').attributes('disabled')).toBeDefined()
      expect(find('effect-table').exists()).toBe(false)
    })

    it('withdraws the note that it saved when something changes again', async () => {
      const { find, move, wait, save } = await open()
      save.mockResolvedValue(noiseFilters({ confidence_floor: 45 }))
      await move(45)
      await wait()
      await find('effect-save').trigger('click')
      await settle()

      await move(60)

      expect(find('effect-saved').exists()).toBe(false)
    })

    it('says why it could not save, and keeps what the page says', async () => {
      const { find, move, wait, save, slider } = await open()
      save.mockRejectedValue(offline())
      await move(45)
      await wait()

      await find('effect-save').trigger('click')
      await settle()

      expect(find('effect-failure').text()).toBe("Can't reach AresGate.")
      expect(slider().props('modelValue')).toBe(45)
      expect(find('effect-saved').exists()).toBe(false)
    })

    it('puts the page back to what is kept on request', async () => {
      const { find, move, wait, slider, save } = await open()
      await move(45)
      await wait()

      await find('effect-discard').trigger('click')
      await settle()

      expect(slider().props('modelValue')).toBe(35)
      expect(save).not.toHaveBeenCalled()
    })
  })
})
