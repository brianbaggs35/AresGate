import { defineComponent, h, ref } from 'vue'
import { VDialog } from 'vuetify/components'

import type { Guide } from '@/api/integrations'
import SetupGuideDialog from '@/components/SetupGuideDialog.vue'
import { guide, part, step } from '@/test/integrations'
import { flushPromises, mountWithPlugins } from '@/test/mount'

/** The window in a page with a button that opens it, as pages use it. */
async function mountGuide(content: Guide = guide(), { width }: { width?: number } = {}) {
  const open = ref(false)
  const Page = defineComponent({
    render: () =>
      h('div', [
        h('button', { 'data-test': 'opener', onClick: () => (open.value = true) }, 'Setup'),
        h(SetupGuideDialog, {
          modelValue: open.value,
          'onUpdate:modelValue': (value: boolean) => (open.value = value),
          name: 'ntopng',
          guide: content,
        }),
      ]),
  })
  const mounted = await mountWithPlugins(Page, { withApp: true, width })
  const opener = mounted.wrapper.find<HTMLButtonElement>('[data-test="opener"]')
  const inWindow = (selector: string) =>
    document.querySelector<HTMLElement>(`.v-overlay--active ${selector}`)
  const all = (selector: string) =>
    Array.from(document.querySelectorAll<HTMLElement>(`.v-overlay--active ${selector}`))
  const openIt = async () => {
    opener.element.focus()
    await opener.trigger('click')
    await flushPromises()
  }
  return { ...mounted, opener, inWindow, all, openIt }
}

describe('SetupGuideDialog', () => {
  it('is closed until it is opened', async () => {
    const { inWindow } = await mountGuide()
    expect(inWindow('[data-test="setup-guide"]')).toBeNull()
  })

  it('is named for what is being set up, and labelled by that name', async () => {
    const { inWindow, openIt } = await mountGuide()
    await openIt()
    expect(inWindow('[data-test="guide-title"]')?.textContent.trim()).toBe('Set up ntopng')
    const title = inWindow('[data-test="guide-title"]')!
    expect(document.querySelector('[role="dialog"]')?.getAttribute('aria-labelledby')).toBe(
      title.id,
    )
  })

  it('takes the keyboard to its title once it has opened', async () => {
    const { wrapper, inWindow, openIt } = await mountGuide()
    await openIt()
    // The transition that ends it doesn't run here, so it is said to have ended.
    wrapper.findComponent(VDialog).vm.$emit('afterEnter')
    expect(document.activeElement).toBe(inWindow('[data-test="guide-title"]'))
  })

  it('numbers the steps of each part under its name and what it is for', async () => {
    const { inWindow, all, openIt } = await mountGuide(
      guide({
        parts: [
          part({
            title: 'Make a token',
            connection: 'api',
            intro: 'AresGate needs a token.',
            steps: [
              step({ title: 'Open the users', detail: 'Go to the users.' }),
              step({ title: 'Make the token', detail: 'Generate it.' }),
            ],
          }),
        ],
      }),
    )
    await openIt()
    const section = inWindow('[data-test="guide-part-api"]')!
    expect(section.querySelector('h3')?.textContent).toBe('Make a token')
    expect(section.textContent).toContain('AresGate needs a token.')
    expect(all('[data-test="step-title"]').map((item) => item.textContent.trim())).toEqual([
      'Open the users',
      'Make the token',
    ])
    expect(section.querySelector('ol.guide__steps')).not.toBeNull()
    expect(inWindow('[data-test="guide-optional"]')).toBeNull()
  })

  it('says which parts can be left out', async () => {
    const { all, openIt } = await mountGuide(
      guide({
        parts: [
          part({ connection: 'api' }),
          part({ title: 'Zenarmor', connection: 'zenarmor', optional: true }),
        ],
      }),
    )
    await openIt()
    expect(all('[data-test="guide-optional"]').map((item) => item.textContent.trim())).toEqual([
      'Optional',
    ])
  })

  it('shows the menus to go through, in order, as a list', async () => {
    const { inWindow, openIt } = await mountGuide(
      guide({
        parts: [part({ steps: [step({ menu: ['System', 'Access', 'Users'] })] })],
      }),
    )
    await openIt()
    const menu = inWindow('.guide__menu')!
    expect(menu.getAttribute('aria-label')).toBe('Where to find it')
    expect(Array.from(menu.querySelectorAll('li')).map((item) => item.textContent.trim())).toEqual([
      'System',
      'Access',
      'Users',
    ])
  })

  it('shows each value to enter next to what it is for', async () => {
    const { inWindow, openIt } = await mountGuide(
      guide({
        parts: [
          part({
            steps: [
              step({
                fills: [
                  { label: 'User Role', value: 'Non Privileged User' },
                  { label: 'Allow Alerts', value: 'On' },
                ],
              }),
            ],
          }),
        ],
      }),
    )
    await openIt()
    const terms = Array.from(inWindow('[data-test="step-fills"]')!.querySelectorAll('dt'))
    const values = Array.from(inWindow('[data-test="step-fills"]')!.querySelectorAll('dd'))
    expect(terms.map((item) => item.textContent)).toEqual(['User Role', 'Allow Alerts'])
    expect(values.map((item) => item.textContent)).toEqual(['Non Privileged User', 'On'])
  })

  it('shows a command to copy, and says where the result goes', async () => {
    const { inWindow, openIt } = await mountGuide(
      guide({
        parts: [
          part({
            steps: [
              step({
                command: 'sudo cscli bouncers add aresgate',
                result: 'Paste the key into API key.',
              }),
            ],
          }),
        ],
      }),
    )
    const written = vi.fn().mockResolvedValue(undefined)
    Object.defineProperty(navigator, 'clipboard', {
      value: { writeText: written },
      configurable: true,
    })
    await openIt()
    expect(inWindow('[data-test="step-command"]')?.textContent).toBe(
      'sudo cscli bouncers add aresgate',
    )
    expect(inWindow('[data-test="step-result"]')?.textContent).toContain(
      'Paste the key into API key.',
    )
    inWindow('[data-test="copy"]')!.click()
    await flushPromises()
    expect(written).toHaveBeenCalledWith('sudo cscli bouncers add aresgate')
  })

  it('says what is easy to get wrong and what is not from the documentation, in words', async () => {
    const { inWindow, openIt } = await mountGuide(
      guide({
        parts: [
          part({
            steps: [
              step({
                watch: 'The secret is shown once.',
                inferred: 'Worked out from the source.',
              }),
            ],
          }),
        ],
      }),
    )
    await openIt()
    expect(inWindow('[data-test="step-watch"]')?.textContent).toContain(
      'Easy to get wrong. The secret is shown once.',
    )
    expect(inWindow('[data-test="step-inferred"]')?.textContent).toContain(
      'Not from the documentation. Worked out from the source.',
    )
  })

  it('leaves out what a step has nothing to say about', async () => {
    const { inWindow, openIt } = await mountGuide()
    await openIt()
    for (const selector of [
      '.guide__menu',
      '[data-test="step-fills"]',
      '[data-test="step-command"]',
      '[data-test="step-result"]',
      '[data-test="step-watch"]',
      '[data-test="step-inferred"]',
    ]) {
      expect(inWindow(selector)).toBeNull()
    }
  })

  it('lists the pages it was written from, which open in a new tab', async () => {
    const { all, openIt } = await mountGuide()
    await openIt()
    const [link] = all('[data-test="guide-sources"] a')
    expect(link?.getAttribute('href')).toBe('https://www.ntop.org/guides/ntopng/')
    expect(link?.getAttribute('target')).toBe('_blank')
    expect(link?.getAttribute('rel')).toBe('noopener noreferrer')
    expect(link?.getAttribute('aria-label')).toBe('ntopng: authentication (opens in a new tab)')
  })

  it('closes with either Close button, and gives the keyboard back to what opened it', async () => {
    const { inWindow, opener, openIt } = await mountGuide()
    await openIt()
    inWindow('[data-test="guide-close"]')!.click()
    await flushPromises()
    expect(inWindow('[data-test="setup-guide"]')).toBeNull()

    await openIt()
    inWindow('[data-test="guide-done"]')!.click()
    await flushPromises()
    expect(inWindow('[data-test="setup-guide"]')).toBeNull()
    await vi.waitFor(() => {
      expect(document.activeElement).toBe(opener.element)
    })
  })

  it('takes the whole screen on a phone, and a window on a larger one', async () => {
    const phone = await mountGuide(guide(), { width: 400 })
    await phone.openIt()
    expect(document.querySelector('.v-overlay--active.v-dialog--fullscreen')).not.toBeNull()
    expect(phone.inWindow('.guide--screen')).not.toBeNull()
    phone.wrapper.unmount()

    const desktop = await mountGuide(guide(), { width: 1280 })
    await desktop.openIt()
    expect(desktop.inWindow('[data-test="setup-guide"]')).not.toBeNull()
    expect(document.querySelector('.v-overlay--active.v-dialog--fullscreen')).toBeNull()
    expect(desktop.inWindow('.guide--screen')).toBeNull()
  })
})
