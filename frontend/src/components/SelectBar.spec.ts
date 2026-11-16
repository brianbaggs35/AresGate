import { h } from 'vue'

import SelectBar from '@/components/SelectBar.vue'
import { mountWithPlugins } from '@/test/mount'

async function show(props: { count?: number; whole?: boolean } = {}) {
  const mounted = await mountWithPlugins(SelectBar, {
    props: { count: 0, whole: false, singular: 'decision', plural: 'decisions', ...props },
    slots: { default: () => h('button', { 'data-test': 'action' }, 'Do it') },
    withApp: true,
  })
  const find = (selector: string) => mounted.wrapper.find(`[data-test="${selector}"]`)
  const said = (name: string) => mounted.wrapper.findComponent(SelectBar).emitted(name) ?? []
  return { ...mounted, find, said }
}

describe('SelectBar', () => {
  it('says what it is for while none is picked, and offers no change', async () => {
    const { find } = await show()

    expect(find('select-hint').text()).toBe('Select decisions to change them together')
    expect(find('select-count').exists()).toBe(false)
    expect(find('action').exists()).toBe(false)
  })

  it('picks every row with its box, which says what it picks', async () => {
    const { find, said } = await show()

    await find('select-all').trigger('change')

    expect(said('toggle-all')).toHaveLength(1)
    expect(find('select-all').attributes('aria-label')).toBe('Select every decision on this list')
  })

  it('says how many are picked, in the singular for one, and shows the changes', async () => {
    const one = await show({ count: 1 })
    const many = await show({ count: 1200 })

    expect(one.find('select-count').text()).toBe('1 decision selected')
    expect(many.find('select-count').text()).toBe('1,200 decisions selected')
    expect(one.find('action').exists()).toBe(true)
  })

  it('is half ticked while some are picked, and ticked when all are', async () => {
    const some = await show({ count: 1 })
    const all = await show({ count: 2, whole: true })

    expect((some.find('select-all').element as HTMLInputElement).indeterminate).toBe(true)
    expect((all.find('select-all').element as HTMLInputElement).checked).toBe(true)
    expect((all.find('select-all').element as HTMLInputElement).indeterminate).toBe(false)
  })

  it('lets them all go', async () => {
    const { find, said } = await show({ count: 2 })

    await find('select-clear').trigger('click')

    expect(said('clear')).toHaveLength(1)
  })
})
