import { ApiError } from '@/api/client'
import * as retentionApi from '@/api/retentionSettings'
import { flushPromises, mountWithPlugins } from '@/test/mount'
import { retentionSettings } from '@/test/retention'
import RetentionSettingsView from '@/views/RetentionSettingsView.vue'

async function open(kept: retentionApi.RetentionSettings | Error = retentionSettings()) {
  const fetchIt = vi.spyOn(retentionApi, 'fetchRetentionSettings')
  if (kept instanceof Error) fetchIt.mockRejectedValue(kept)
  else fetchIt.mockResolvedValue(kept)
  const save = vi
    .spyOn(retentionApi, 'saveRetentionSettings')
    .mockImplementation((draft) => Promise.resolve(retentionSettings(draft)))
  const mounted = await mountWithPlugins(RetentionSettingsView, {
    signedIn: 'admin',
    withApp: true,
  })
  await flushPromises()
  const find = (selector: string) => mounted.wrapper.find(`[data-test="${selector}"]`)
  const input = (selector: string) =>
    mounted.wrapper.find<HTMLInputElement>(`[data-test="${selector}"] input`)
  const type = async (selector: string, value: string) => {
    await input(selector).setValue(value)
    await flushPromises()
  }
  const turn = async (selector: string, on: boolean) => {
    await input(selector).setValue(on)
    await flushPromises()
  }
  return { ...mounted, fetchIt, save, find, input, type, turn }
}

describe('RetentionSettingsView', () => {
  it('shows a placeholder while it asks, and says when it could not', async () => {
    vi.spyOn(retentionApi, 'fetchRetentionSettings').mockReturnValue(new Promise(() => {}))
    const loading = await mountWithPlugins(RetentionSettingsView, { signedIn: 'admin' })
    expect(loading.wrapper.find('[data-test="retention-settings-loading"]').exists()).toBe(true)

    const failed = await open(new ApiError(0, "Can't reach AresGate.", 'offline'))
    expect(failed.find('retention-settings-error').text()).toContain("Can't reach AresGate.")
  })

  it('starts switched off, says how long each kind is kept now, and has nothing to save', async () => {
    const { find, input } = await open()

    expect(input('retention-managed').element.checked).toBe(false)
    expect(find('retention-built-in').text()).toContain('Events 30 days')
    expect(find('retention-built-in').text()).toContain('AI requests 90 days')
    expect(find('retention-built-in').text()).toContain('Activity 365 days.')
    expect(find('retention-time-card').exists()).toBe(false)
    expect(find('retention-quota-card').exists()).toBe(false)
    expect(find('retention-save').attributes('disabled')).toBeDefined()
  })

  it('keeps a number of days once it is switched on, and says so until the next change', async () => {
    const { find, turn, type, save } = await open()

    await turn('retention-managed', true)
    expect(find('retention-built-in').exists()).toBe(false)
    expect(find('retention-days').exists()).toBe(true)
    await type('retention-days', '14')
    await find('retention-save').trigger('click')
    await flushPromises()

    expect(save).toHaveBeenCalledWith(
      { managed: true, keep_forever: false, days: 14, quota_gb: null },
      'a-security-token',
    )
    expect(find('retention-saved').text()).toBe('Saved.')
    await type('retention-days', '20')
    expect(find('retention-saved').exists()).toBe(false)
  })

  it('refuses days that are not a whole number in range', async () => {
    const { find, turn, type, save } = await open()
    await turn('retention-managed', true)

    for (const bad of ['0', '4000', '1.5', '']) {
      await type('retention-days', bad)
      expect(find('retention-save').attributes('disabled')).toBeDefined()
      expect(find('retention-time-card').text()).toContain('from 1 to 3650')
    }
    expect(save).not.toHaveBeenCalled()
    await type('retention-days', '3650')
    expect(find('retention-save').attributes('disabled')).toBeUndefined()
  })

  it('keeps everything forever, with no days or limit to give', async () => {
    const { find, input, turn, save } = await open()
    await turn('retention-managed', true)

    await input('retention-mode-forever').setValue(true)
    await flushPromises()

    expect(find('retention-days').exists()).toBe(false)
    expect(find('retention-own').exists()).toBe(false)
    expect(find('retention-quota-card').exists()).toBe(false)
    await find('retention-save').trigger('click')
    await flushPromises()
    expect(save).toHaveBeenCalledWith(
      { managed: true, keep_forever: true, days: 30, quota_gb: null },
      'a-security-token',
    )
  })

  it('limits the size of the database, and takes the limit back', async () => {
    const { find, turn, type, save } = await open(
      retentionSettings({ managed: true, quota_gb: null }),
    )
    expect(find('retention-quota').exists()).toBe(false)

    await turn('retention-limited', true)
    expect(find('retention-quota').exists()).toBe(true)
    await type('retention-quota', '0')
    expect(find('retention-save').attributes('disabled')).toBeDefined()
    expect(find('retention-quota-card').text()).toContain('from 1 to 100000')
    await type('retention-quota', '50')
    await find('retention-save').trigger('click')
    await flushPromises()
    expect(save).toHaveBeenLastCalledWith(
      { managed: true, keep_forever: false, days: 30, quota_gb: 50 },
      'a-security-token',
    )

    await turn('retention-limited', false)
    await find('retention-save').trigger('click')
    await flushPromises()
    expect(save).toHaveBeenLastCalledWith(
      { managed: true, keep_forever: false, days: 30, quota_gb: null },
      'a-security-token',
    )
  })

  it('goes back to what is kept', async () => {
    const { find, input, turn } = await open()

    await turn('retention-managed', true)
    await find('retention-discard').trigger('click')

    expect(input('retention-managed').element.checked).toBe(false)
    expect(find('retention-save').attributes('disabled')).toBeDefined()
  })

  it('says when saving failed', async () => {
    const { find, turn, save } = await open()
    save.mockRejectedValue(new ApiError(500, 'Could not save.', 'server'))

    await turn('retention-managed', true)
    await find('retention-save').trigger('click')
    await flushPromises()

    expect(find('retention-save-failure').text()).toBe('Could not save.')
    expect(find('retention-saved').exists()).toBe(false)
  })

  it('says what the database holds, with no limit', async () => {
    const { find } = await open()

    expect(find('retention-usage-total').text()).toBe('2.0 GB')
    expect(find('retention-usage-events').text()).toBe('1.0 GB')
    expect(find('retention-usage-metrics').text()).toBe('256.0 MB')
    expect(find('retention-usage-oldest').text()).not.toBe('None yet')
    expect(find('retention-usage-bar').exists()).toBe(false)
    expect(find('retention-over').exists()).toBe(false)
  })

  it('shows how much of the limit is used, and warns when over it with nothing left to remove', async () => {
    const { find } = await open(
      retentionSettings({
        managed: true,
        quota_gb: 1,
        usage: {
          ...retentionSettings().usage,
          oldest_event_at: null,
          quota_bytes: 1_073_741_824,
          over_quota: true,
        },
      }),
    )

    expect(find('retention-usage-bar').exists()).toBe(true)
    expect(find('retention-limit').text()).toBe('100% of the 1.0 GB limit.')
    expect(find('retention-over').text()).toContain('nothing more can be removed')
    expect(find('retention-usage-oldest').text()).toBe('None yet')
  })
})
