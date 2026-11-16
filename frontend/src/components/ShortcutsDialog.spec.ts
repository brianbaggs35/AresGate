import { defineComponent, h, ref } from 'vue'
import { VDialog } from 'vuetify/components'

import ShortcutsDialog from '@/components/ShortcutsDialog.vue'
import { SHORTCUTS } from '@/shortcuts'
import { flushPromises, mountWithPlugins } from '@/test/mount'

async function mountDialog() {
  const open = ref(false)
  const Page = defineComponent({
    render: () =>
      h('div', [
        h('button', { 'data-test': 'opener', onClick: () => (open.value = true) }, 'Keys'),
        h(ShortcutsDialog, {
          modelValue: open.value,
          'onUpdate:modelValue': (value: boolean) => (open.value = value),
        }),
      ]),
  })
  const mounted = await mountWithPlugins(Page, { withApp: true })
  const one = (selector: string) => document.querySelector<HTMLElement>(`[data-test="${selector}"]`)
  const opener = mounted.wrapper.find<HTMLButtonElement>('[data-test="opener"]')
  return { ...mounted, open, one, opener }
}

describe('ShortcutsDialog', () => {
  it('is closed until it is opened', async () => {
    const { one } = await mountDialog()

    expect(one('shortcuts')).toBeNull()
  })

  it('lists every shortcut under the page it works on', async () => {
    const { one, opener } = await mountDialog()

    opener.element.focus()
    await opener.trigger('click')
    await flushPromises()

    expect(one('shortcuts')?.querySelector('h2')?.textContent).toBe('Keyboard shortcuts')
    expect(one('shortcuts-everywhere')?.textContent).toContain('Open the command palette')
    expect(one('shortcuts-incidents')?.textContent).toContain('Move to the next incident')
    expect(one('shortcuts-logs')?.textContent).toContain('Move through the events')
    expect(one('shortcuts')?.querySelectorAll('dd')).toHaveLength(SHORTCUTS.length)
  })

  it('closes with its button and gives the keyboard back to what opened it', async () => {
    const { wrapper, one, opener, open } = await mountDialog()
    opener.element.focus()
    await opener.trigger('click')
    await flushPromises()

    one('shortcuts-close')!.click()
    await flushPromises()
    // jsdom plays no transitions, so the end of the one that closes the dialog is announced here.
    wrapper.findComponent(VDialog).vm.$emit('afterLeave')

    expect(open.value).toBe(false)
    expect(document.activeElement).toBe(opener.element)
  })
})
