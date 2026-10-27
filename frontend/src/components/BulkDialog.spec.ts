import { defineComponent, h, ref } from 'vue'

import { ApiError } from '@/api/client'
import * as incidentsApi from '@/api/incidents'
import BulkDialog from '@/components/BulkDialog.vue'
import type { Change } from '@/bulk'
import { bulkResult } from '@/test/incidents'
import { flushPromises, mountWithPlugins } from '@/test/mount'

const inDialog = (selector: string) => document.querySelector<HTMLElement>(selector)
const lines = () =>
  [...document.querySelectorAll('[data-test="bulk-would"]')].map((line) => line.textContent.trim())

/** The dialog in a page that opens it, as the list of incidents does. */
async function mountDialog(
  props: {
    change?: Change
    selection?: incidentsApi.BulkSelection
    count?: number
    busy?: boolean
    error?: string | null
  } = {},
) {
  const confirmed = vi.fn()
  const open = ref(false)
  const Page = defineComponent({
    render: () =>
      h('div', [
        h('button', { 'data-test': 'opener', onClick: () => (open.value = true) }, 'Change'),
        h(BulkDialog, {
          modelValue: open.value,
          'onUpdate:modelValue': (value: boolean) => (open.value = value),
          change: { status: 'resolved' },
          selection: { ids: [4, 7] },
          count: 2,
          busy: false,
          error: null,
          onConfirm: confirmed,
          ...props,
        }),
      ]),
  })
  const mounted = await mountWithPlugins(Page, { signedIn: 'admin', withApp: true })
  const openIt = async () => {
    await mounted.wrapper.find('[data-test="opener"]').trigger('click')
    await flushPromises()
    await flushPromises()
  }
  return { ...mounted, confirmed, open, openIt }
}

describe('BulkDialog', () => {
  it('is closed until it is opened, and asks nothing', async () => {
    const preview = vi.spyOn(incidentsApi, 'changeIncidents')
    await mountDialog()

    expect(inDialog('[data-test="confirm-dialog"]')).toBeNull()
    expect(preview).not.toHaveBeenCalled()
  })

  it('asks the API what the change would do, and says so', async () => {
    const preview = vi
      .spyOn(incidentsApi, 'changeIncidents')
      .mockResolvedValue(bulkResult({ preview: true, incidents: 12, signals: 31, changed: 9 }))
    const { openIt } = await mountDialog({ selection: { ids: [4, 7] } })

    await openIt()

    expect(preview).toHaveBeenCalledWith(
      { ids: [4, 7] },
      { status: 'resolved' },
      'a-security-token',
      true,
    )
    expect(inDialog('[data-test="confirm-title"]')?.textContent).toBe('Resolve 12 incidents?')
    expect(lines()).toEqual([
      '12 incidents, with 31 signals.',
      '9 will be marked as resolved; 3 already are.',
    ])
    expect(inDialog('[data-test="confirm-accept"]')?.textContent.trim()).toBe('Resolve')
    expect(inDialog('[data-test="bulk-note"]')).toBeNull()
  })

  it('names the incidents it was asked of while it counts, and cannot go ahead yet', async () => {
    vi.spyOn(incidentsApi, 'changeIncidents').mockReturnValue(new Promise(() => {}))
    const { openIt } = await mountDialog({ count: 40 })

    await openIt()

    expect(inDialog('[data-test="confirm-title"]')?.textContent).toBe('Resolve 40 incidents?')
    expect(inDialog('[data-test="bulk-looking"]')?.textContent).toContain('Counting')
    expect(inDialog('[data-test="confirm-accept"]')?.hasAttribute('disabled')).toBe(true)
  })

  it('goes ahead when told to', async () => {
    vi.spyOn(incidentsApi, 'changeIncidents').mockResolvedValue(bulkResult({ preview: true }))
    const { openIt, confirmed } = await mountDialog()
    await openIt()

    inDialog('[data-test="confirm-accept"]')!.click()
    await flushPromises()

    expect(confirmed).toHaveBeenCalledExactlyOnceWith('')
  })

  it('cannot go ahead when there is nothing to change', async () => {
    vi.spyOn(incidentsApi, 'changeIncidents').mockResolvedValue(
      bulkResult({ preview: true, changed: 0 }),
    )
    const { openIt } = await mountDialog()

    await openIt()

    expect(lines()[1]).toBe('Nothing to change: all already are resolved.')
    expect(inDialog('[data-test="confirm-accept"]')?.hasAttribute('disabled')).toBe(true)
  })

  it('says why a verdict is given, and keeps it with the verdict', async () => {
    vi.spyOn(incidentsApi, 'changeIncidents').mockResolvedValue(
      bulkResult({ preview: true, incidents: 5, changed: 5, verdicts: 2 }),
    )
    const { openIt, confirmed } = await mountDialog({ change: { verdict: 'not_suspicious' } })
    await openIt()

    const note = inDialog('[data-test="bulk-note"] textarea') as HTMLTextAreaElement
    note.value = 'My own scanner'
    note.dispatchEvent(new Event('input'))
    await flushPromises()
    inDialog('[data-test="confirm-accept"]')!.click()
    await flushPromises()

    expect(inDialog('[data-test="confirm-title"]')?.textContent).toBe(
      'Say 5 incidents are not suspicious?',
    )
    expect(lines()[1]).toMatch(/^2 verdicts will be remembered as not suspicious/)
    expect(confirmed).toHaveBeenCalledExactlyOnceWith('My own scanner')
  })

  it('starts each look with no note', async () => {
    vi.spyOn(incidentsApi, 'changeIncidents').mockResolvedValue(
      bulkResult({ preview: true, verdicts: 1 }),
    )
    const { openIt, open } = await mountDialog({ change: { verdict: 'threat' } })
    await openIt()
    const note = () => inDialog('[data-test="bulk-note"] textarea') as HTMLTextAreaElement
    note().value = 'Something'
    note().dispatchEvent(new Event('input'))
    open.value = false
    await flushPromises()

    await openIt()

    expect(note().value).toBe('')
  })

  it('closes when it is cancelled, asking nothing more', async () => {
    const preview = vi
      .spyOn(incidentsApi, 'changeIncidents')
      .mockResolvedValue(bulkResult({ preview: true }))
    const { openIt, open, confirmed } = await mountDialog()
    await openIt()

    inDialog('[data-test="confirm-cancel"]')!.click()
    await flushPromises()

    expect(open.value).toBe(false)
    expect(confirmed).not.toHaveBeenCalled()
    expect(preview).toHaveBeenCalledTimes(1)
  })

  it('says why it cannot look, and cannot go ahead', async () => {
    vi.spyOn(incidentsApi, 'changeIncidents').mockRejectedValue(
      new ApiError(
        422,
        'That is 3,000 incidents, and 1,000 is the most that can be changed.',
        'invalid',
      ),
    )
    const { openIt } = await mountDialog()

    await openIt()

    expect(inDialog('[data-test="bulk-problem"]')?.textContent).toContain('3,000 incidents')
    expect(inDialog('[data-test="bulk-looking"]')).toBeNull()
    expect(inDialog('[data-test="confirm-accept"]')?.hasAttribute('disabled')).toBe(true)
  })

  it('says why the change itself failed', async () => {
    vi.spyOn(incidentsApi, 'changeIncidents').mockResolvedValue(bulkResult({ preview: true }))
    const { openIt } = await mountDialog({ error: "Can't reach AresGate." })

    await openIt()

    expect(inDialog('[data-test="bulk-problem"]')?.textContent).toContain("Can't reach AresGate.")
  })

  it('drops the answer to a look that was overtaken by another', async () => {
    let first!: (result: incidentsApi.BulkResult) => void
    vi.spyOn(incidentsApi, 'changeIncidents')
      .mockReturnValueOnce(new Promise((resolve) => (first = resolve)))
      .mockResolvedValueOnce(bulkResult({ preview: true, incidents: 7 }))
    const { openIt, open } = await mountDialog()
    await openIt()
    open.value = false
    await flushPromises()
    await openIt()

    first(bulkResult({ preview: true, incidents: 99 }))
    await flushPromises()

    expect(lines()[0]).toMatch(/^7 incidents/)
  })

  it('drops the failure of a look that was overtaken by another', async () => {
    let fail!: (error: Error) => void
    vi.spyOn(incidentsApi, 'changeIncidents')
      .mockReturnValueOnce(new Promise((_, reject) => (fail = reject)))
      .mockResolvedValueOnce(bulkResult({ preview: true, incidents: 7 }))
    const { openIt, open } = await mountDialog()
    await openIt()
    open.value = false
    await flushPromises()
    await openIt()

    fail(new ApiError(0, "Can't reach AresGate.", 'offline'))
    await flushPromises()

    expect(inDialog('[data-test="bulk-problem"]')).toBeNull()
  })
})
