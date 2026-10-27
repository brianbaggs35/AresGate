import { VSnackbar } from 'vuetify/components'

import { ApiError } from '@/api/client'
import * as incidentsApi from '@/api/incidents'
import BulkNotice from '@/components/BulkNotice.vue'
import { flushPromises, mountWithPlugins } from '@/test/mount'

/** What the notice says at the bottom of the page, which is outside the component itself. */
const notice = (selector: string) =>
  document.querySelector<HTMLElement>(`[data-test="${selector}"]`)

const WAY: incidentsApi.BulkUndo = { statuses: { open: [4, 7] }, rules: [] }

async function open() {
  const mounted = await mountWithPlugins(BulkNotice, { signedIn: 'admin', withApp: true })
  const shown = mounted.wrapper.findComponent(BulkNotice)
  const show = async (
    text = 'Marked 2 incidents as resolved.',
    undo = WAY as typeof WAY | null,
  ) => {
    ;(
      shown.vm as unknown as { show: (text: string, undo: incidentsApi.BulkUndo | null) => void }
    ).show(text, undo)
    await flushPromises()
  }
  const undo = async () => {
    notice('bulk-undo')?.click()
    await flushPromises()
    await flushPromises()
  }
  return { ...mounted, shown, show, undo }
}

describe('BulkNotice', () => {
  it('says nothing until it is told of a change', async () => {
    await open()

    expect(notice('bulk-notice')).toBeNull()
  })

  it('says what was done, with a way to take it back', async () => {
    const { show } = await open()

    await show()

    expect(notice('bulk-notice-text')?.textContent).toBe('Marked 2 incidents as resolved.')
    expect(notice('bulk-undo')).not.toBeNull()
  })

  it('offers no way back for a change that has none', async () => {
    const { show } = await open()

    await show('Nothing changed: all already are resolved.', null)

    expect(notice('bulk-notice-text')?.textContent).toContain('Nothing changed')
    expect(notice('bulk-undo')).toBeNull()
  })

  it('takes the change back as it said how, and says it has', async () => {
    const undone = vi
      .spyOn(incidentsApi, 'undoChange')
      .mockResolvedValue({ incidents: 2, verdicts: 0 })
    const { shown, show, undo } = await open()
    await show()

    await undo()

    expect(undone).toHaveBeenCalledWith(WAY, 'a-security-token')
    expect(notice('bulk-notice-text')?.textContent).toBe('Taken back.')
    expect(notice('bulk-undo')).toBeNull()
    expect(shown.emitted('undone')).toHaveLength(1)
  })

  it('says so when it could not be taken back, and does not say it was', async () => {
    vi.spyOn(incidentsApi, 'undoChange').mockRejectedValue(
      new ApiError(0, "Can't reach AresGate.", 'offline'),
    )
    const { shown, show, undo } = await open()
    await show()

    await undo()

    expect(notice('bulk-notice-text')?.textContent).toBe("Can't reach AresGate.")
    expect(shown.emitted('undone')).toBeUndefined()
  })

  it('stops saying it once it has been dismissed or its time is up', async () => {
    const { wrapper, show } = await open()
    await show()

    wrapper.findComponent(VSnackbar).vm.$emit('update:modelValue', false)
    await flushPromises()

    expect(wrapper.findComponent(VSnackbar).props('modelValue')).toBe(false)
  })

  it('says a second change in the place of the first', async () => {
    const { show } = await open()
    await show('First.')

    await show('Second.', null)

    expect(notice('bulk-notice-text')?.textContent).toBe('Second.')
    expect(notice('bulk-undo')).toBeNull()
  })
})
