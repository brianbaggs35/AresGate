import RawRecord from '@/components/RawRecord.vue'
import { mountWithPlugins } from '@/test/mount'

const raw = {
  action: 'block',
  dport: 22,
  ok: true,
  note: '<b>not markup</b>',
  tags: [],
  none: null,
}

const open = (props: { raw: Record<string, unknown> | null }) =>
  mountWithPlugins(RawRecord, { withApp: true, props })

describe('RawRecord', () => {
  it('shows the record pretty-printed, with its size', async () => {
    const { wrapper } = await open({ raw })

    expect(wrapper.find('[data-test="raw-text"]').element.textContent).toBe(
      JSON.stringify(raw, null, 2),
    )
    expect(wrapper.find('[data-test="raw-size"]').text()).toMatch(/^\d+ B$/)
    expect(wrapper.find('h3').text()).toBe('Record as received')
  })

  it('colours the parts by what they are', async () => {
    const { wrapper } = await open({ raw })
    const parts = (kind: string) => wrapper.findAll(`.raw__${kind}`).map((part) => part.text())

    expect(parts('key')).toEqual(['"action"', '"dport"', '"ok"', '"note"', '"tags"', '"none"'])
    expect(parts('string')).toEqual(['"block"', '"<b>not markup</b>"'])
    expect(parts('number')).toEqual(['22'])
    expect(parts('literal')).toEqual(['true', 'null'])
  })

  it('shows what is in the record as text, never as markup', async () => {
    const { wrapper } = await open({ raw })

    expect(wrapper.find('[data-test="raw-text"] b').exists()).toBe(false)
  })

  it('has a button to copy all of it', async () => {
    const { wrapper } = await open({ raw })

    expect(wrapper.find('[aria-label="Copy the record"]').exists()).toBe(true)
  })

  it('says so when no record was kept', async () => {
    const { wrapper } = await open({ raw: null })

    expect(wrapper.find('[data-test="raw-none"]').text()).toContain('did not send a record')
    expect(wrapper.find('[data-test="raw-text"]').exists()).toBe(false)
    expect(wrapper.find('[aria-label="Copy the record"]').exists()).toBe(false)
  })
})
