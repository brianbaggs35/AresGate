import { VSlider } from 'vuetify/components'

import { ApiError } from '@/api/client'
import * as reviewApi from '@/api/review'
import { flushPromises, mountWithPlugins } from '@/test/mount'
import { reviewSettings } from '@/test/review'
import ReviewSettingsView from '@/views/ReviewSettingsView.vue'

async function open(kept: reviewApi.ReviewSettings | Error = reviewSettings()) {
  const fetchIt = vi.spyOn(reviewApi, 'fetchReviewSettings')
  if (kept instanceof Error) fetchIt.mockRejectedValue(kept)
  else fetchIt.mockResolvedValue(kept)
  const save = vi
    .spyOn(reviewApi, 'saveReviewSettings')
    .mockImplementation((draft) => Promise.resolve(reviewSettings(draft)))
  const mounted = await mountWithPlugins(ReviewSettingsView, { signedIn: 'admin', withApp: true })
  await flushPromises()
  const find = (selector: string) => mounted.wrapper.find(`[data-test="${selector}"]`)
  const checked = (selector: string) =>
    mounted.wrapper.find<HTMLInputElement>(`[data-test="${selector}"] input`).element.checked
  const choose = async (mode: string) => {
    await find(`review-mode-${mode}`).find('input').setValue(true)
  }
  return { ...mounted, fetchIt, save, find, choose, checked }
}

describe('ReviewSettingsView', () => {
  it('shows a placeholder while it asks, and says when it could not', async () => {
    vi.spyOn(reviewApi, 'fetchReviewSettings').mockReturnValue(new Promise(() => {}))
    const loading = await mountWithPlugins(ReviewSettingsView, { signedIn: 'admin' })
    expect(loading.wrapper.find('[data-test="review-settings-loading"]').exists()).toBe(true)

    const failed = await open(new ApiError(0, "Can't reach AresGate.", 'offline'))
    expect(failed.find('review-settings-error').text()).toContain("Can't reach AresGate.")
  })

  it('shows how it is kept, with nothing to save', async () => {
    const { find, checked } = await open(reviewSettings({ mode: 'auto', learn: false }))

    expect(checked('review-mode-auto')).toBe(true)
    expect(find('review-save').attributes('disabled')).toBeDefined()
    expect(find('review-from-bar').exists()).toBe(false)
    expect(checked('review-learn')).toBe(false)
  })

  it('keeps a change, and says so until the next one', async () => {
    const { find, choose, save } = await open()

    await choose('auto')
    await find('review-save').trigger('click')
    await flushPromises()

    expect(save).toHaveBeenCalledWith(
      { mode: 'auto', auto_from: 85, learn: true },
      'a-security-token',
    )
    expect(find('review-saved').text()).toBe('Saved.')
    await choose('all')
    expect(find('review-saved').exists()).toBe(false)
  })

  it('asks how sure the AI has to be, and can go back to the usual', async () => {
    const { find, choose, wrapper } = await open()
    expect(find('review-from-bar').exists()).toBe(false)

    await choose('uncertain')
    expect(find('review-from-value').text()).toBe('85% sure')
    expect(find('review-from-reset').exists()).toBe(false)

    wrapper.findComponent(VSlider).vm.$emit('update:modelValue', 92)
    await flushPromises()
    expect(find('review-from-sentence').text()).toContain('92% sure')

    await find('review-from-reset').trigger('click')
    expect(find('review-from-value').text()).toBe('85% sure')
  })

  it('keeps the switch for telling the AI what was disagreed with', async () => {
    const { find, wrapper, save } = await open()

    await wrapper.find('[data-test="review-learn"] input').setValue(false)
    await find('review-save').trigger('click')
    await flushPromises()

    expect(save).toHaveBeenCalledWith(expect.objectContaining({ learn: false }), expect.any(String))
  })

  it('goes back to what is kept', async () => {
    const { find, choose, checked } = await open()

    await choose('auto')
    await find('review-discard').trigger('click')

    expect(checked('review-mode-all')).toBe(true)
    expect(find('review-save').attributes('disabled')).toBeDefined()
  })

  it('says when saving failed', async () => {
    const { find, choose, save } = await open()
    save.mockRejectedValue(new ApiError(500, 'Could not save.', 'server'))

    await choose('auto')
    await find('review-save').trigger('click')
    await flushPromises()

    expect(find('review-save-failure').text()).toBe('Could not save.')
    expect(find('review-saved').exists()).toBe(false)
  })
})
