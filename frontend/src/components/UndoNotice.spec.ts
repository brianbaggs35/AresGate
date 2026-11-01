import UndoNotice from '@/components/UndoNotice.vue'
import type { Done } from '@/interface-board'
import { flushPromises, mountWithPlugins } from '@/test/mount'

/** What the notice says at the bottom of the page, which is outside the component itself. */
const notice = (selector: string) =>
  document.querySelector<HTMLElement>(`[data-test="${selector}"]`)

async function open() {
  const mounted = await mountWithPlugins(UndoNotice, { signedIn: 'admin', withApp: true })
  const shown = mounted.wrapper.findComponent(UndoNotice)
  const show = async (done: Done) => {
    ;(shown.vm as unknown as { show: (done: Done) => void }).show(done)
    await flushPromises()
  }
  return { ...mounted, shown, show }
}

describe('UndoNotice', () => {
  it('says nothing until it is told of a change', async () => {
    await open()

    expect(notice('undo-notice')).toBeNull()
  })

  it('says what was done, with a way to take it back', async () => {
    const { show } = await open()

    await show({ text: 'OPNsense igc0 is now on Internet.', undo: async () => {} })

    expect(notice('undo-notice-text')?.textContent).toBe('OPNsense igc0 is now on Internet.')
    expect(notice('undo-notice-undo')).not.toBeNull()
  })

  it('offers no way back for a change that has none', async () => {
    const { show } = await open()

    await show({ text: 'Guests saved.', undo: null })

    expect(notice('undo-notice-text')?.textContent).toBe('Guests saved.')
    expect(notice('undo-notice-undo')).toBeNull()
  })

  it('hands the change back to whoever shows it when Undo is pressed', async () => {
    const { show, shown } = await open()
    const done: Done = { text: 'Placed.', undo: async () => {} }
    await show(done)

    notice('undo-notice-undo')?.click()
    await flushPromises()

    expect(shown.emitted('undo')).toEqual([[done]])
  })
})
