import { defineComponent, h, ref } from 'vue'
import { VDialog } from 'vuetify/components'

import * as layoutApi from '@/api/dashboardLayout'
import DashboardCustomize from '@/components/DashboardCustomize.vue'
import { DEFAULT_PLACES } from '@/dashboardLayout'
import { useDashboardLayoutStore } from '@/stores/dashboardLayout'
import { flushPromises, mountWithPlugins } from '@/test/mount'

const presets = [
  { key: 'overview', title: 'Overview', description: 'All of it.', widgets: [] },
  {
    key: 'quiet',
    title: 'Quiet',
    description: 'Only what needs you.',
    widgets: [{ id: 'needs_you', size: 'full' as const, hidden: false }],
  },
]

async function mountSheet(withPresets = true, startOpen = true) {
  const open = ref(startOpen)
  const Page = defineComponent({
    render: () =>
      h('div', [
        h('button', { 'data-test': 'opener', onClick: () => (open.value = true) }, 'Customize'),
        h(DashboardCustomize, {
          modelValue: open.value,
          'onUpdate:modelValue': (value: boolean) => (open.value = value),
        }),
      ]),
  })
  const mounted = await mountWithPlugins(Page, { withApp: true })
  const layout = useDashboardLayoutStore()
  if (withPresets) layout.presets = presets
  const save = vi.spyOn(layout, 'save').mockResolvedValue(undefined)
  await flushPromises()
  const one = (selector: string) => document.querySelector<HTMLElement>(`[data-test="${selector}"]`)
  const all = (selector: string) =>
    Array.from(document.querySelectorAll<HTMLElement>(`[data-test="${selector}"]`))
  const row = (id: string) => one(`widget-${id}`)!
  const inRow = (id: string, selector: string) =>
    row(id).querySelector<HTMLElement>(`[data-test="${selector}"]`)!
  const flush = async () => {
    await flushPromises()
    await flushPromises()
  }
  return { ...mounted, layout, open, save, one, all, row, inRow, flush }
}

/** A drag event, as jsdom has none of its own. */
function drag(name: string, on: Element) {
  const event = new Event(name, { bubbles: true, cancelable: true })
  Object.assign(event, { dataTransfer: { setData: vi.fn() } })
  on.dispatchEvent(event)
  return event
}

describe('DashboardCustomize', () => {
  it('lists every widget, with what it shows, and the presets to start from', async () => {
    const { all, one, layout } = await mountSheet()

    expect(all('widget-grip')).toHaveLength(DEFAULT_PLACES.length)
    expect(one('widget-list')?.textContent).toContain('Traffic')
    expect(one('preset-overview')?.textContent).toContain('All of it.')
    expect(one('preset-overview')?.getAttribute('aria-pressed')).toBe('true')
    expect(one('preset-quiet')?.getAttribute('aria-pressed')).toBe('false')
    expect(layout.places).toHaveLength(DEFAULT_PLACES.length)
  })

  it('has no presets to offer until the server has sent them', async () => {
    const { one } = await mountSheet(false)

    expect(one('preset-overview')).toBeNull()
    expect(one('widget-list')).not.toBeNull()
  })

  it('starts over from a preset', async () => {
    const { one, layout, flush } = await mountSheet()
    const apply = vi.spyOn(layout, 'apply').mockResolvedValue(undefined)

    one('preset-quiet')!.click()
    await flush()

    expect(apply).toHaveBeenCalledWith('quiet')
  })

  it('shows why a change could not be saved', async () => {
    const { one, layout, flush } = await mountSheet()
    layout.error = 'The dashboard could not be saved.'
    await flush()

    expect(one('customize-error')?.textContent).toContain('could not be saved')
  })

  it('hides and shows a widget with its switch', async () => {
    const { inRow, save, flush } = await mountSheet()

    inRow('traffic', 'widget-show').querySelector<HTMLInputElement>('input')!.click()
    await flush()

    const next = save.mock.calls[0]![0]
    expect(next.find((place) => place.id === 'traffic')?.hidden).toBe(true)
  })

  it('makes a widget half or full width', async () => {
    const { inRow, save, flush } = await mountSheet()

    inRow('traffic', 'widget-full').click()
    await flush()

    expect(save.mock.calls[0]![0].find((place) => place.id === 'traffic')?.size).toBe('full')
  })

  it('moves a widget with the buttons, and says where it went', async () => {
    const { inRow, one, save, flush } = await mountSheet()

    inRow('filtered', 'widget-down').click()
    await flush()

    expect(save).toHaveBeenCalledTimes(1)
    expect(one('customize-status')?.textContent).toMatch(/is now number 2 of 9\.$/)
  })

  it('stops the first widget going up and the last going down', async () => {
    const { layout, row, inRow } = await mountSheet()
    const first = layout.places[0]!.id
    const last = layout.places.at(-1)!.id

    expect(inRow(first, 'widget-up').hasAttribute('disabled')).toBe(true)
    expect(inRow(last, 'widget-down').hasAttribute('disabled')).toBe(true)
    expect(row(first)).not.toBeNull()
  })

  it('drags a widget by its handle onto another', async () => {
    const { row, inRow, save, layout, flush } = await mountSheet()
    const [from, onto] = [layout.places[0]!.id, layout.places[2]!.id]

    inRow(from, 'widget-grip').dispatchEvent(new Event('mousedown', { bubbles: true }))
    const started = drag('dragstart', row(from))
    drag('dragover', row(onto))
    await flush()
    expect(row(onto).className).toContain('widget--over')
    drag('drop', row(onto))
    await flush()

    expect(started.defaultPrevented).toBe(false)
    expect(save).toHaveBeenCalledTimes(1)
    expect(save.mock.calls[0]![0].map((place) => place.id).indexOf(from)).toBe(2)
  })

  it('does not drag a widget that was not taken by its handle', async () => {
    const { row, save, layout, flush } = await mountSheet()
    const [from, onto] = [layout.places[0]!.id, layout.places[2]!.id]

    const started = drag('dragstart', row(from))
    drag('drop', row(onto))
    await flush()

    expect(started.defaultPrevented).toBe(true)
    expect(save).not.toHaveBeenCalled()
  })

  it('does nothing when a widget is dropped on itself or the drag is let go', async () => {
    const { row, inRow, save, layout, flush } = await mountSheet()
    const from = layout.places[0]!.id

    inRow(from, 'widget-grip').dispatchEvent(new Event('mousedown', { bubbles: true }))
    drag('dragstart', row(from))
    drag('drop', row(from))
    inRow(from, 'widget-grip').dispatchEvent(new Event('mousedown', { bubbles: true }))
    drag('dragstart', row(from))
    drag('dragend', row(from))
    await flush()

    expect(save).not.toHaveBeenCalled()
  })

  it('puts the default back', async () => {
    const { one, layout, flush } = await mountSheet()
    const reset = vi.spyOn(layoutApi, 'resetLayout').mockResolvedValue(undefined)

    one('customize-reset')!.click()
    await flush()

    expect(reset).toHaveBeenCalled()
    expect(layout.preset).toBe('overview')
  })

  it('moves a widget up with its button', async () => {
    const { inRow, save, flush } = await mountSheet()

    inRow('review', 'widget-up').click()
    await flush()

    expect(save.mock.calls[0]![0].map((place) => place.id).indexOf('review')).toBe(0)
  })

  it('gives the keyboard back to what opened it', async () => {
    const { wrapper, open, one, flush } = await mountSheet(true, false)
    const opener = wrapper.find<HTMLButtonElement>('[data-test="opener"]')
    opener.element.focus()
    await opener.trigger('click')
    await flush()

    one('customize-done')!.click()
    await flush()
    await new Promise((resolve) => setTimeout(resolve, 400))

    expect(open.value).toBe(false)
    expect(document.activeElement).toBe(opener.element)
  })

  it('closes when the window asks to be, as when the page behind it is pressed', async () => {
    const { wrapper, open, flush } = await mountSheet()

    wrapper.findComponent(VDialog).vm.$emit('update:modelValue', false)
    await flush()

    expect(open.value).toBe(false)
  })

  it('closes with Done and with the close button', async () => {
    const { one, open, flush } = await mountSheet()

    one('customize-done')!.click()
    await flush()
    expect(open.value).toBe(false)

    open.value = true
    await flush()
    one('customize-close')!.click()
    await flush()
    expect(open.value).toBe(false)
  })
})
