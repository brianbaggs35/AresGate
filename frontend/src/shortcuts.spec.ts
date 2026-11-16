import { defineComponent, h } from 'vue'

import { SHORTCUTS, overlayOpen, typingIn, useShortcuts } from '@/shortcuts'
import { mountWithPlugins } from '@/test/mount'

function listening(handlers: Record<string, () => void>) {
  return mountWithPlugins(
    defineComponent({
      setup() {
        useShortcuts(handlers)
        return () => h('div', [h('input', { 'data-test': 'field' })])
      },
    }),
  )
}

const press = (key: string, init: KeyboardEventInit = {}, on: EventTarget = window) => {
  const event = new KeyboardEvent('keydown', { key, bubbles: true, cancelable: true, ...init })
  on.dispatchEvent(event)
  return event
}

describe('shortcuts', () => {
  it('lists each key once for each page it works on', () => {
    const seen = SHORTCUTS.map(({ keys, page }) => `${page}:${keys.join('+')}`)

    expect(new Set(seen).size).toBe(seen.length)
    expect(new Set(SHORTCUTS.map(({ page }) => page))).toEqual(
      new Set(['Everywhere', 'Incidents', 'Logs']),
    )
  })

  describe('typingIn', () => {
    it('is true for a field and for what is in one, and not for anything else', () => {
      const field = document.createElement('input')
      const editable = document.createElement('div')
      editable.setAttribute('contenteditable', 'true')
      const plain = document.createElement('button')

      expect(typingIn(field)).toBe(true)
      expect(typingIn(editable)).toBe(true)
      expect(typingIn(plain)).toBe(false)
      expect(typingIn(window)).toBe(false)
      expect(typingIn(null)).toBe(false)
    })
  })

  describe('overlayOpen', () => {
    afterEach(() => document.querySelector('.v-overlay--active')?.remove())

    it('is true while something is over the page', () => {
      expect(overlayOpen()).toBe(false)
      const overlay = document.createElement('div')
      overlay.className = 'v-overlay v-overlay--active'
      document.body.append(overlay)

      expect(overlayOpen()).toBe(true)
    })
  })

  describe('useShortcuts', () => {
    it('runs what a key is for, and keeps the browser from doing it too', async () => {
      const run = vi.fn()
      await listening({ j: run })

      const event = press('j')

      expect(run).toHaveBeenCalledTimes(1)
      expect(event.defaultPrevented).toBe(true)
    })

    it('leaves a key it has nothing for alone', async () => {
      const run = vi.fn()
      await listening({ j: run })

      const event = press('q')

      expect(run).not.toHaveBeenCalled()
      expect(event.defaultPrevented).toBe(false)
    })

    it.each([['ctrlKey'], ['metaKey'], ['altKey']])(
      'does not answer a key with %s',
      async (held) => {
        const run = vi.fn()
        await listening({ j: run })

        press('j', { [held]: true })

        expect(run).not.toHaveBeenCalled()
      },
    )

    it('does not answer a key typed into a field', async () => {
      const run = vi.fn()
      const { wrapper } = await listening({ j: run })

      press('j', {}, wrapper.find('input').element)

      expect(run).not.toHaveBeenCalled()
    })

    it('does not answer a key while something is over the page', async () => {
      const run = vi.fn()
      await listening({ j: run })
      const overlay = document.createElement('div')
      overlay.className = 'v-overlay--active'
      document.body.append(overlay)

      press('j')
      overlay.remove()

      expect(run).not.toHaveBeenCalled()
    })

    it('stops answering when the page goes', async () => {
      const run = vi.fn()
      const { wrapper } = await listening({ j: run })

      wrapper.unmount()
      press('j')

      expect(run).not.toHaveBeenCalled()
    })
  })
})
