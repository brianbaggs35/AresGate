import { VSnackbar } from 'vuetify/components'

import { ApiError } from '@/api/client'
import * as verdictsApi from '@/api/verdicts'
import JudgedNotice from '@/components/JudgedNotice.vue'
import { flushPromises, mountWithPlugins } from '@/test/mount'
import { given, judged } from '@/test/verdicts'
import type { Judged } from '@/verdicts'

/** What the notice says at the bottom of the page, which is outside the component itself. */
const notice = (selector: string) =>
  document.querySelector<HTMLElement>(`[data-test="${selector}"]`)

async function open() {
  const mounted = await mountWithPlugins(JudgedNotice, { signedIn: 'admin', withApp: true })
  const shown = mounted.wrapper.findComponent(JudgedNotice)
  const show = async (verdict: Judged = judged()) => {
    ;(shown.vm as unknown as { show: (verdict: Judged) => void }).show(verdict)
    await flushPromises()
  }
  const undo = async () => {
    notice('undo')?.click()
    await flushPromises()
    await flushPromises()
  }
  return { ...mounted, shown, show, undo }
}

describe('JudgedNotice', () => {
  it('says nothing until it is told of a verdict', async () => {
    await open()

    expect(notice('judged')).toBeNull()
  })

  it('says what was remembered, with a way to take it back', async () => {
    const { show } = await open()

    await show()

    expect(notice('judged-text')?.textContent).toBe('Remembered: 93.184.216.34 is not suspicious.')
    expect(notice('undo')).not.toBeNull()
  })

  it('says what a verdict that changed another was before', async () => {
    const { show } = await open()

    await show(judged({ kind: 'threat', rule: given({ replaced: 'low_priority' }) }))

    expect(notice('judged-text')?.textContent).toBe(
      'Remembered: 93.184.216.34 is a real threat. It was low priority.',
    )
  })

  it('takes back a new verdict, and says it has', async () => {
    const remove = vi.spyOn(verdictsApi, 'removeVerdict').mockResolvedValue(undefined)
    const { shown, show, undo } = await open()
    await show(judged({ rule: given({ id: 7 }) }))

    await undo()

    expect(remove).toHaveBeenCalledWith(7, 'a-security-token')
    expect(notice('judged-text')?.textContent).toBe('Taken back.')
    expect(notice('undo')).toBeNull()
    expect(shown.emitted('undone')).toHaveLength(1)
  })

  it('changes a verdict that replaced another back to what it was', async () => {
    const change = vi.spyOn(verdictsApi, 'changeVerdict').mockResolvedValue(given())
    const remove = vi.spyOn(verdictsApi, 'removeVerdict').mockResolvedValue(undefined)
    const { show, undo } = await open()
    await show(judged({ rule: given({ id: 7, replaced: 'low_priority' }) }))

    await undo()

    expect(change).toHaveBeenCalledWith(7, { verdict: 'low_priority' }, 'a-security-token')
    expect(remove).not.toHaveBeenCalled()
  })

  it('says so when it could not be taken back, and does not say it was', async () => {
    vi.spyOn(verdictsApi, 'removeVerdict').mockRejectedValue(
      new ApiError(0, "Can't reach AresGate.", 'offline'),
    )
    const { shown, show, undo } = await open()
    await show()

    await undo()

    expect(notice('judged-text')?.textContent).toBe("Can't reach AresGate.")
    expect(shown.emitted('undone')).toBeUndefined()
  })

  it('stops saying it once it has been dismissed or its time is up', async () => {
    const { wrapper, show } = await open()
    await show()

    wrapper.findComponent(VSnackbar).vm.$emit('update:modelValue', false)
    await flushPromises()

    expect(wrapper.findComponent(VSnackbar).props('modelValue')).toBe(false)
  })
})
