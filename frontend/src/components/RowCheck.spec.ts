import RowCheck from '@/components/RowCheck.vue'
import { mountWithPlugins } from '@/test/mount'

async function show(checked = false) {
  const mounted = await mountWithPlugins(RowCheck, {
    props: { checked, label: 'Select: Everything about 52.1.2.3' },
  })
  const box = mounted.wrapper.find('[data-test="row-select"]')
  return { ...mounted, box, said: () => mounted.wrapper.findComponent(RowCheck).emitted('toggle') }
}

describe('RowCheck', () => {
  it('says what picking it is for, and whether it is picked', async () => {
    const { box } = await show(true)

    expect(box.attributes('aria-label')).toBe('Select: Everything about 52.1.2.3')
    expect((box.element as HTMLInputElement).checked).toBe(true)
  })

  it('says it was clicked, as one row', async () => {
    const { box, said } = await show()

    await box.trigger('click')

    expect(said()).toEqual([[false]])
  })

  it('says a click with Shift held is for the rows from the last one picked', async () => {
    const { box, said } = await show()

    await box.trigger('click', { shiftKey: true })

    expect(said()).toEqual([[true]])
  })
})
