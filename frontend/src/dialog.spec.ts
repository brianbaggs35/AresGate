import { defineComponent, h, nextTick, ref } from 'vue'

import { useKeyboardReturn } from '@/dialog'
import { mountWithPlugins } from '@/test/mount'

/** A button that opens a "dialog", which is only a flag here, and a way to close it again. */
function opener() {
  const open = ref(false)
  let giveBack = () => {}
  const component = defineComponent({
    setup() {
      giveBack = useKeyboardReturn(open)
      return () =>
        h(
          'button',
          {
            'data-test': 'opener',
            onClick: () => {
              open.value = true
            },
          },
          'Open',
        )
    },
  })
  return {
    open,
    component,
    giveBack: () => {
      giveBack()
    },
  }
}

describe('useKeyboardReturn', () => {
  it('gives the keyboard back to what had it when the dialog opened', async () => {
    const { open, component, giveBack } = opener()
    const { wrapper } = await mountWithPlugins(component)
    const button = wrapper.find<HTMLButtonElement>('[data-test="opener"]').element
    button.focus()

    open.value = true
    await nextTick()
    button.blur()
    open.value = false
    await nextTick()
    giveBack()

    expect(document.activeElement).toBe(button)
  })

  it('gives it back once, and not to something that closed the dialog and has gone', async () => {
    const { open, component, giveBack } = opener()
    const { wrapper } = await mountWithPlugins(component)
    const button = wrapper.find<HTMLButtonElement>('[data-test="opener"]').element
    button.focus()
    open.value = true
    await nextTick()
    giveBack()
    button.blur()

    giveBack()

    expect(document.activeElement).not.toBe(button)
  })

  it('does nothing for a dialog that was never opened', async () => {
    const { component, giveBack } = opener()
    await mountWithPlugins(component)

    expect(() => {
      giveBack()
    }).not.toThrow()
  })
})
