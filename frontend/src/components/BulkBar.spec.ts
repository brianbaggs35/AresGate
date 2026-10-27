import BulkBar from '@/components/BulkBar.vue'
import { flushPromises, mountWithPlugins } from '@/test/mount'

interface Props {
  count?: number
  total?: number
  shown?: number
  whole?: boolean
  everything?: boolean
  busy?: boolean
}

async function show(props: Props = {}, width?: number) {
  const mounted = await mountWithPlugins(BulkBar, {
    props: { count: 0, total: 3, shown: 3, whole: false, everything: false, ...props },
    withApp: true,
    ...(width ? { width } : {}),
  })
  const find = (selector: string) => mounted.wrapper.find(`[data-test="${selector}"]`)
  const said = (name: string) => mounted.wrapper.findComponent(BulkBar).emitted(name) ?? []
  return { ...mounted, find, said }
}

describe('BulkBar', () => {
  it('says what it is for while none is picked, and offers no change', async () => {
    const { find } = await show()

    expect(find('bulk-hint').text()).toBe('Select incidents to change them together')
    expect(find('bulk-count').exists()).toBe(false)
    expect(find('bulk-status').exists()).toBe(false)
  })

  it('picks every incident on the page with its box', async () => {
    const { find, said } = await show()

    await find('bulk-page').trigger('change')

    expect(said('toggle-page')).toHaveLength(1)
    expect(find('bulk-page').attributes('aria-label')).toBe('Select every incident on this page')
  })

  it('shows its box ticked when the page is, and between when only some are', async () => {
    const some = await show({ count: 1 })
    const whole = await show({ count: 3, whole: true })
    const none = await show()

    const state = (shown: Awaited<ReturnType<typeof show>>) => {
      const box = shown.find('bulk-page').element as HTMLInputElement
      return [box.checked, box.indeterminate]
    }
    expect(state(none)).toEqual([false, false])
    expect(state(some)).toEqual([false, true])
    expect(state(whole)).toEqual([true, false])
  })

  it('says how many are picked, and offers the changes and letting go', async () => {
    const { find } = await show({ count: 1500 })

    expect(find('bulk-count').text()).toBe('1,500 selected')
    expect(find('bulk-count').element.tagName).toBe('OUTPUT')
    expect(
      ['not_suspicious', 'low_priority', 'threat'].map((kind) => find(`bulk-${kind}`).text()),
    ).toEqual(['Not suspicious', 'Low priority', 'Real threat'])
    expect(find('bulk-clear').text()).toBe('Clear')
  })

  it('gives a verdict, and lets go', async () => {
    const { find, said } = await show({ count: 2 })

    await find('bulk-low_priority').trigger('click')
    await find('bulk-clear').trigger('click')

    expect(said('verdict')).toEqual([['low_priority']])
    expect(said('clear')).toHaveLength(1)
  })

  it('offers each status in a menu, named for what it does', async () => {
    const { find, said } = await show({ count: 2 })

    await find('bulk-status').trigger('click')
    await flushPromises()
    const items = [...document.querySelectorAll<HTMLElement>('[data-test^="bulk-status-"]')]

    expect(items.map((item) => item.textContent.trim())).toEqual([
      'Start investigating',
      'Resolve',
      'Dismiss',
      'Reopen',
    ])
    items[1]?.click()
    await flushPromises()
    expect(said('status')).toEqual([['resolved']])
  })

  it('stacks the icon over the name on a phone', async () => {
    const { find } = await show({ count: 2 }, 400)

    expect(find('bulk-threat').classes()).toContain('v-btn--stacked')
  })

  it('cannot be changed again while a change is under way', async () => {
    const { find } = await show({ count: 2, busy: true })

    expect(find('bulk-threat').attributes('disabled')).toBeDefined()
    expect(find('bulk-status').attributes('disabled')).toBeDefined()
  })

  it('offers all that match, once the page is picked and there are more', async () => {
    const { find, said } = await show({ count: 3, whole: true, shown: 3, total: 143 })

    expect(find('bulk-offer').text().replace(/\s+/g, ' ')).toBe(
      'All 3 on this page are selected. Select all 143 incidents that match',
    )
    await find('bulk-everything').trigger('click')
    expect(said('pick-everything')).toHaveLength(1)
  })

  it('does not offer it when the page is all there is, or is not picked', async () => {
    const all = await show({ count: 3, whole: true, shown: 3, total: 3 })
    const part = await show({ count: 1, whole: false, shown: 3, total: 143 })

    expect(all.find('bulk-offer').exists()).toBe(false)
    expect(part.find('bulk-offer').exists()).toBe(false)
  })

  it('says all that match are picked, once they are', async () => {
    const { find } = await show({ count: 143, whole: true, everything: true, total: 143 })

    expect(find('bulk-all').text()).toBe('All 143 incidents that match are selected.')
    expect(find('bulk-offer').exists()).toBe(false)
  })
})
