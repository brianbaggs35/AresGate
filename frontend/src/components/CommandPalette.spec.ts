import { defineComponent, h, ref } from 'vue'
import { VDialog } from 'vuetify/components'

import CommandPalette from '@/components/CommandPalette.vue'
import { useThemeStore } from '@/stores/theme'
import { flushPromises, mountWithPlugins } from '@/test/mount'

/** The palette in a page with a button that opens it, as the app does through its store. */
async function mountPalette() {
  const open = ref(false)
  const Page = defineComponent({
    render: () =>
      h('div', [
        h('button', { 'data-test': 'opener', onClick: () => (open.value = true) }, 'Search'),
        h(CommandPalette, {
          modelValue: open.value,
          'onUpdate:modelValue': (value: boolean) => (open.value = value),
        }),
      ]),
  })
  const mounted = await mountWithPlugins(Page, { withApp: true, route: '/' })
  const opener = mounted.wrapper.find<HTMLButtonElement>('[data-test="opener"]')
  const inPalette = (selector: string) => document.querySelector<HTMLElement>(selector)
  const rows = () => Array.from(document.querySelectorAll<HTMLElement>('.palette__row'))
  const titles = () => rows().map((row) => row.textContent.trim())
  const search = () =>
    document.querySelector<HTMLInputElement>('[data-test="palette-search"] input')!
  const press = async (target: HTMLElement, key: string) => {
    const event = new KeyboardEvent('keydown', { key, bubbles: true, cancelable: true })
    target.dispatchEvent(event)
    await flushPromises()
    return event
  }
  const type = async (text: string) => {
    const field = search()
    field.value = text
    field.dispatchEvent(new Event('input', { bubbles: true }))
    await flushPromises()
  }
  const openIt = async () => {
    opener.element.focus()
    await opener.trigger('click')
    await flushPromises()
  }
  return { ...mounted, open, opener, inPalette, rows, titles, search, press, type, openIt }
}

describe('CommandPalette', () => {
  it('is closed until it is opened', async () => {
    const { inPalette } = await mountPalette()
    expect(inPalette('[data-test="palette"]')).toBeNull()
  })

  it('opens with a field that has the keyboard, and everything listed under its group', async () => {
    const { openIt, inPalette, search, titles } = await mountPalette()

    await openIt()

    // The field asks for the keyboard; browsers give it, and jsdom doesn't, so it's the ask that is seen.
    expect(search().hasAttribute('autofocus')).toBe(true)
    expect(
      Array.from(document.querySelectorAll('.palette__heading')).map(
        (heading) => heading.textContent,
      ),
    ).toEqual(['Go to', 'Incidents', 'Appearance'])
    expect(titles()).toContain('Dashboard')
    expect(titles()).toContain('Show all incidents')
    expect(titles()).toContain('Use the dark theme')
    expect(inPalette('[data-test="palette-count"]')?.textContent).toMatch(/\d+ found/)
    expect(inPalette('[data-test="palette-empty"]')).toBeNull()
  })

  it('is named, and each group of rows is named by its heading', async () => {
    const { openIt, inPalette } = await mountPalette()
    await openIt()

    const title = inPalette('.palette__hidden')!
    expect(inPalette('[role="dialog"]')?.getAttribute('aria-labelledby')).toBe(title.id)
    for (const list of document.querySelectorAll('.palette__rows')) {
      const heading = document.getElementById(list.getAttribute('aria-labelledby') as string)
      expect(heading?.tagName).toBe('H3')
    }
  })

  it('narrows the list to what was typed, and says how many were found', async () => {
    const { openIt, type, titles, inPalette } = await mountPalette()
    await openIt()

    await type('status')

    expect(titles()).toEqual(['Status'])
    expect(inPalette('[data-test="palette-count"]')?.textContent).toBe('1 found')
    expect(document.querySelectorAll('.palette__heading')).toHaveLength(1)
  })

  it('says when nothing matches, in the same words that were typed', async () => {
    const { openIt, type, rows, inPalette } = await mountPalette()
    await openIt()

    await type('  zzzz ')

    expect(rows()).toHaveLength(0)
    expect(inPalette('[data-test="palette-empty"]')?.textContent.trim()).toBe(
      'Nothing matches “zzzz”. Try the name of a page.',
    )
    expect(inPalette('[data-test="palette-count"]')?.textContent).toBe('Nothing found')
  })

  it('goes to the first thing found when Enter is pressed, and closes', async () => {
    const { openIt, type, search, press, router, open } = await mountPalette()
    await openIt()
    await type('status')

    await press(search(), 'Enter')

    await vi.waitFor(() => {
      expect(router.currentRoute.value.name).toBe('status')
    })
    expect(open.value).toBe(false)
  })

  it('does nothing on Enter when nothing was found', async () => {
    const { openIt, type, search, press, router, open } = await mountPalette()
    await openIt()
    await type('zzzz')

    await press(search(), 'Enter')

    expect(router.currentRoute.value.name).toBe('home')
    expect(open.value).toBe(true)
  })

  it('looks for the incidents about an address that was typed whole', async () => {
    const { openIt, type, search, press, router } = await mountPalette()
    await openIt()
    await type('93.184.216.34')

    await press(search(), 'Enter')

    await vi.waitFor(() => {
      expect(router.currentRoute.value.name).toBe('incidents')
    })
    expect(router.currentRoute.value.query).toEqual({ view: 'all', address: '93.184.216.34' })
  })

  it('ignores the other keys in the field', async () => {
    const { openIt, search, press, open, rows } = await mountPalette()
    await openIt()

    const event = await press(search(), 'a')

    expect(event.defaultPrevented).toBe(false)
    expect(open.value).toBe(true)
    expect(rows().length).toBeGreaterThan(0)
  })

  it('moves down from the field into the list, and through it with the arrow keys', async () => {
    const { openIt, search, press, rows } = await mountPalette()
    await openIt()

    const down = await press(search(), 'ArrowDown')
    expect(down.defaultPrevented).toBe(true)
    expect(document.activeElement).toBe(rows()[0])

    await press(rows()[0]!, 'ArrowDown')
    expect(document.activeElement).toBe(rows()[1])
    await press(rows()[1]!, 'ArrowUp')
    expect(document.activeElement).toBe(rows()[0])
  })

  it('goes back to the field from the top of the list, and stops at the bottom', async () => {
    const { openIt, search, press, rows } = await mountPalette()
    await openIt()
    rows()[0]!.focus()

    await press(rows()[0]!, 'ArrowUp')
    expect(document.activeElement).toBe(search())

    const last = rows().at(-1)!
    last.focus()
    await press(last, 'ArrowDown')
    // There is nothing after it, so the keyboard stays where it was.
    expect(document.activeElement).toBe(last)
  })

  it('leaves the other keys to the row', async () => {
    const { openIt, press, rows } = await mountPalette()
    await openIt()
    rows()[0]!.focus()

    const event = await press(rows()[0]!, 'Tab')

    expect(event.defaultPrevented).toBe(false)
    expect(document.activeElement).toBe(rows()[0])
  })

  it('goes to a page when its row is chosen, and closes', async () => {
    const { openIt, inPalette, router, open } = await mountPalette()
    await openIt()

    inPalette('[data-test="command-go-settings-verdicts"]')!.click()
    await flushPromises()

    await vi.waitFor(() => {
      expect(router.currentRoute.value.name).toBe('settings-verdicts')
    })
    expect(open.value).toBe(false)
  })

  it('changes the theme when that is chosen, and closes', async () => {
    const { openIt, inPalette, open } = await mountPalette()
    await openIt()
    const theme = useThemeStore()

    inPalette('[data-test="command-theme-dark"]')!.click()
    await flushPromises()

    expect(theme.preference).toBe('dark')
    expect(open.value).toBe(false)
  })

  it('opens empty each time', async () => {
    const { openIt, type, search, open, rows } = await mountPalette()
    await openIt()
    await type('status')
    expect(rows()).toHaveLength(1)

    open.value = false
    await flushPromises()
    await openIt()

    expect(search().value).toBe('')
    expect(rows().length).toBeGreaterThan(1)
  })

  it('closes on Escape, as dialogs do', async () => {
    const { openIt, inPalette, open } = await mountPalette()
    await openIt()

    inPalette('[data-test="palette"]')!.dispatchEvent(
      new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }),
    )
    await flushPromises()

    expect(open.value).toBe(false)
  })

  it('gives the keyboard back to what opened it, once it has gone', async () => {
    const { wrapper, openIt, opener } = await mountPalette()
    await openIt()
    const dialog = wrapper.findComponent(VDialog)

    // jsdom plays no transitions, so the end of the one that closes the dialog is announced here.
    dialog.vm.$emit('afterLeave')

    expect(document.activeElement).toBe(opener.element)
  })
})
