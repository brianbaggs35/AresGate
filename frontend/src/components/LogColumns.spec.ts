import { defineComponent, h, ref } from 'vue'

import LogColumns from '@/components/LogColumns.vue'
import { DEFAULT_COLUMNS, type ColumnKey, type TimeMode } from '@/logs'
import { flushPromises, mountWithPlugins } from '@/test/mount'

async function open(columns: ColumnKey[] = [...DEFAULT_COLUMNS]) {
  const chosen = ref(columns)
  const time = ref<TimeMode>('exact')
  const Page = defineComponent({
    render: () =>
      h(LogColumns, {
        columns: chosen.value,
        time: time.value,
        'onUpdate:columns': (value: ColumnKey[]) => (chosen.value = value),
        'onUpdate:time': (value: TimeMode) => (time.value = value),
      }),
  })
  const mounted = await mountWithPlugins(Page, { withApp: true })
  mounted.wrapper.find<HTMLButtonElement>('[data-test="log-view"]').element.click()
  await flushPromises()
  const inMenu = (selector: string) =>
    document.querySelector<HTMLElement>(`[data-test="${selector}"]`)
  const box = (key: string) => inMenu(`column-${key}`)?.querySelector('input') as HTMLInputElement
  return { ...mounted, chosen, time, inMenu, box }
}

describe('LogColumns', () => {
  it('keeps the way time is shown when the radio group lets go of its choice', async () => {
    const { wrapper, time } = await open()
    const group = wrapper.findComponent({ name: 'VRadioGroup' })

    group.vm.$emit('update:modelValue', 'relative')
    group.vm.$emit('update:modelValue', null)
    await flushPromises()

    expect(time.value).toBe('relative')
  })

  it('is closed until it is asked for', async () => {
    const { wrapper } = await mountWithPlugins(LogColumns, {
      withApp: true,
      props: { columns: DEFAULT_COLUMNS, time: 'exact' },
    })

    expect(wrapper.find('[data-test="log-view"]').text()).toBe('View')
    expect(document.querySelector('[data-test="log-view-panel"]')).toBeNull()
  })

  it('lists the columns, with the ones in the table ticked', async () => {
    const { box } = await open()

    expect(box('severity').checked).toBe(true)
    expect(box('protocol').checked).toBe(false)
    expect(box('received').checked).toBe(false)
  })

  it('keeps the time and the summary, which a row cannot do without', async () => {
    const { box } = await open()

    expect(box('time').disabled).toBe(true)
    expect(box('summary').disabled).toBe(true)
    expect(box('time').checked).toBe(true)
  })

  it('adds a column in the table’s own order, and takes one out', async () => {
    const { box, chosen } = await open(['time', 'source', 'summary'])

    box('protocol').click()
    await flushPromises()
    expect(chosen.value).toEqual(['time', 'source', 'protocol', 'summary'])

    box('severity').click()
    await flushPromises()
    expect(chosen.value).toEqual(['time', 'severity', 'source', 'protocol', 'summary'])

    box('source').click()
    await flushPromises()
    expect(chosen.value).toEqual(['time', 'severity', 'protocol', 'summary'])
  })

  it('goes back to the usual columns', async () => {
    const { inMenu, chosen } = await open(['time', 'summary'])

    inMenu('columns-reset')?.click()
    await flushPromises()

    expect(chosen.value).toEqual(DEFAULT_COLUMNS)
  })

  it('shows the time as the exact time or as how long ago', async () => {
    const { inMenu, time } = await open()
    const radio = (key: string) => inMenu(key)?.querySelector('input') as HTMLInputElement
    expect(radio('time-exact').checked).toBe(true)

    radio('time-relative').click()
    await flushPromises()

    expect(time.value).toBe('relative')
  })
})
