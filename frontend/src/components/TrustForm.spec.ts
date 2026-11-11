import { nextTick } from 'vue'

import TrustForm from '@/components/TrustForm.vue'
import { trustRule } from '@/test/trust'
import { mountWithPlugins } from '@/test/mount'
import type { Trust } from '@/api/trust'

async function form(rule: Trust | null = null, props: Record<string, unknown> = {}) {
  const mounted = await mountWithPlugins(TrustForm, {
    props: { rule, saveLabel: 'Save', ...props },
    signedIn: 'admin',
  })
  const find = (selector: string) => mounted.wrapper.find(`[data-test="${selector}"]`)
  const type = async (field: string, text: string) => {
    await find(field).find('input').setValue(text)
  }
  return { ...mounted, find, type }
}

describe('TrustForm', () => {
  it('starts empty and safe for a new decision', async () => {
    const { find } = await form()

    expect(find('field-address').find('input').element.value).toBe('')
    expect(find('level-not_suspicious').find('input').element.checked).toBe(true)
    expect(find('trust-save').text()).toBe('Save')
  })

  it('starts from what a decision says', async () => {
    const { find } = await form(trustRule({ note: 'camera', verdict: 'low_priority' }))

    expect(find('field-address').find('input').element.value).toBe('52.1.2.3')
    expect(find('field-note').find('input').element.value).toBe('camera')
    expect(find('level-low_priority').find('input').element.checked).toBe(true)
  })

  it('asks for something to be named, and does not save until it is', async () => {
    const { find, wrapper } = await form()

    await find('trust-form').trigger('submit')
    await nextTick()

    expect(find('trust-problem').text()).toContain('Say what to trust')
    expect(wrapper.emitted('save')).toBeUndefined()
  })

  it('saves what was typed, trimmed', async () => {
    const { find, type, wrapper } = await form()
    await type('field-address', ' 52.1.2.3 ')
    await type('field-note', 'my camera')

    await find('trust-form').trigger('submit')

    expect(wrapper.emitted('save')).toEqual([
      [{ verdict: 'not_suspicious', note: 'my camera', address: '52.1.2.3' }],
    ])
    expect(find('trust-problem').exists()).toBe(false)
  })

  it('saves what it is limited to: where it sends, the program and the alert', async () => {
    const { find, type, wrapper } = await form()
    await type('field-address', '192.168.1.30')
    await type('field-destination', '52.0.0.0/8')
    await type('field-signature', 'ET POLICY Odd call')
    wrapper.findComponent({ name: 'VSelect' }).vm.$emit('update:modelValue', 'wazuh')
    await nextTick()

    await find('trust-form').trigger('submit')

    expect(wrapper.emitted('save')?.[0]?.[0]).toEqual({
      verdict: 'not_suspicious',
      note: '',
      address: '192.168.1.30',
      destination: '52.0.0.0/8',
      source: 'wazuh',
      signature: 'ET POLICY Odd call',
    })
  })

  it('saves the level that was chosen', async () => {
    const { find, type, wrapper } = await form()
    await type('field-address', '52.1.2.3')
    await find('level-low_priority').find('input').setValue(true)

    await find('trust-form').trigger('submit')

    expect(wrapper.emitted('save')?.[0]?.[0]).toMatchObject({ verdict: 'low_priority' })
  })

  it('sends a note that was cleared as empty, which takes it off', async () => {
    const { find, type, wrapper } = await form(trustRule({ note: 'camera' }))
    await type('field-note', '')

    await find('trust-form').trigger('submit')

    expect(wrapper.emitted('save')?.[0]?.[0]).toMatchObject({ note: '' })
  })

  it('starts again from the decision when it is replaced by one that was saved', async () => {
    const { find, type, wrapper } = await form(trustRule())
    await type('field-address', 'typed over')

    await wrapper.setProps({ rule: trustRule({ address: '8.8.8.8' }) })

    expect(find('field-address').find('input').element.value).toBe('8.8.8.8')
  })

  it('forgets a problem when it starts again', async () => {
    const { find, wrapper } = await form()
    await find('trust-form').trigger('submit')
    expect(find('trust-problem').exists()).toBe(true)

    await wrapper.setProps({ rule: trustRule() })

    expect(find('trust-problem').exists()).toBe(false)
  })

  it('says why the server refused', async () => {
    const { find } = await form(null, { failure: 'Another decision says the same.' })

    expect(find('trust-failure').text()).toBe('Another decision says the same.')
  })

  it('cancels', async () => {
    const { find, wrapper } = await form()

    await find('trust-cancel').trigger('click')

    expect(wrapper.emitted('cancel')).toHaveLength(1)
  })

  it('cannot be cancelled while it saves', async () => {
    const { find } = await form(null, { busy: true })

    expect(find('trust-cancel').attributes('disabled')).toBeDefined()
  })
})
