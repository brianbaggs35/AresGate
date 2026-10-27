import { defineComponent, h, ref } from 'vue'

import { ApiError } from '@/api/client'
import * as api from '@/api/logs'
import type { LogEvent } from '@/api/logs'
import LogDrawer from '@/components/LogDrawer.vue'
import { flushPromises, mountWithPlugins } from '@/test/mount'
import { logDetail, logEvent } from '@/test/logs'

const first = logEvent({ id: 2, signature: 'ET SCAN Potential SSH Scan' })
const second = logEvent({ id: 1, summary: 'Blocked udp', src_address: null, src_port: null })

async function mountDrawer(
  options: { event?: LogEvent | null; open?: boolean; older?: boolean; newer?: boolean } = {},
) {
  const event = ref<LogEvent | null>(options.event === undefined ? first : options.event)
  const open = ref(options.open ?? true)
  const flags = ref({ older: options.older ?? true, newer: options.newer ?? true })
  const searched = vi.fn<(term: string) => void>()
  const stepped = vi.fn<(direction: string) => void>()
  const Page = defineComponent({
    render: () =>
      h(LogDrawer, {
        modelValue: open.value,
        'onUpdate:modelValue': (value: boolean) => (open.value = value),
        event: event.value,
        hasOlder: flags.value.older,
        hasNewer: flags.value.newer,
        onSearch: searched,
        onStep: stepped,
      }),
  })
  const mounted = await mountWithPlugins(Page, { withApp: true, signedIn: 'admin' })
  await flushPromises()
  const inDrawer = (selector: string) =>
    document.querySelector<HTMLElement>(`[data-test="${selector}"]`)
  const click = async (selector: string) => {
    inDrawer(selector)?.click()
    await flushPromises()
  }
  const press = async (key: string, modifiers: KeyboardEventInit = {}) => {
    inDrawer('log-drawer')?.dispatchEvent(
      new KeyboardEvent('keydown', { key, bubbles: true, ...modifiers }),
    )
    await flushPromises()
  }
  return { ...mounted, event, open, flags, searched, stepped, inDrawer, click, press }
}

afterEach(() => {
  vi.restoreAllMocks()
})

describe('LogDrawer', () => {
  it('is closed until it is opened, and never asks for an event while it is', async () => {
    const fetchLog = vi.spyOn(api, 'fetchLog')
    const { inDrawer } = await mountDrawer({ open: false })

    expect(inDrawer('log-drawer')).toBeNull()
    expect(fetchLog).not.toHaveBeenCalled()
  })

  it('shows nothing where there is no event', async () => {
    const fetchLog = vi.spyOn(api, 'fetchLog')
    const { inDrawer } = await mountDrawer({ event: null })

    expect(inDrawer('log-drawer')).toBeNull()
    expect(fetchLog).not.toHaveBeenCalled()
  })

  it('shows what the list had at once, while it asks for the rest', async () => {
    vi.spyOn(api, 'fetchLog').mockReturnValue(new Promise(() => undefined))
    const { inDrawer } = await mountDrawer()

    expect(inDrawer('drawer-title')?.textContent.trim()).toBe(first.summary)
    expect(inDrawer('log-drawer')?.textContent).toContain('Medium')
    expect(inDrawer('log-drawer')?.textContent).toContain('OPNsense · firewall')
    expect(inDrawer('drawer-loading')).not.toBeNull()
    expect(inDrawer('raw-record')).toBeNull()
  })

  it('names the dialog by what the event says', async () => {
    vi.spyOn(api, 'fetchLog').mockResolvedValue(logDetail())
    const { inDrawer } = await mountDrawer()

    const dialog = document.querySelector('[role="dialog"]')
    expect(dialog?.getAttribute('aria-labelledby')).toBe(inDrawer('drawer-title')?.id)
  })

  it('asks for the event by where it is in the order, and shows its record', async () => {
    const fetchLog = vi.spyOn(api, 'fetchLog').mockResolvedValue(logDetail())
    const { inDrawer } = await mountDrawer()

    expect(fetchLog).toHaveBeenCalledWith(first.cursor)
    expect(inDrawer('drawer-loading')).toBeNull()
    expect(inDrawer('raw-text')?.textContent).toContain('"action": "block"')
  })

  it('links to the incident the event was filed into', async () => {
    vi.spyOn(api, 'fetchLog').mockResolvedValue(logDetail())
    const { inDrawer } = await mountDrawer()

    const link = inDrawer('drawer-incident')
    expect(link?.getAttribute('href')).toBe('/incidents/7')
    expect(link?.textContent).toContain('Brute force on ssh (93.184.216.34)')
    expect(link?.textContent).toContain('High')
    expect(link?.textContent).toContain('Open')
    expect(inDrawer('drawer-no-incident')).toBeNull()
  })

  it('says so when it is not part of an incident', async () => {
    vi.spyOn(api, 'fetchLog').mockResolvedValue(logDetail({ incident: null }))
    const { inDrawer } = await mountDrawer()

    expect(inDrawer('drawer-incident')).toBeNull()
    expect(inDrawer('drawer-no-incident')?.textContent).toContain('Not part of an incident')
  })

  it('says so when no record was kept', async () => {
    vi.spyOn(api, 'fetchLog').mockResolvedValue(logDetail({ raw: null }))
    const { inDrawer } = await mountDrawer()

    expect(inDrawer('raw-none')).not.toBeNull()
  })

  it('lists every field, each with a button to copy it', async () => {
    vi.spyOn(api, 'fetchLog').mockResolvedValue(logDetail())
    const { inDrawer } = await mountDrawer()

    expect(inDrawer('field-from')?.textContent).toContain('93.184.216.34')
    expect(inDrawer('field-to-port')?.textContent).toContain('22')
    expect(inDrawer('field-signature')?.textContent).toContain('ET SCAN Potential SSH Scan')
    expect(inDrawer('field-from')?.querySelector('[aria-label="Copy From"]')).not.toBeNull()
  })

  it('offers a search for others like each field that can be searched for', async () => {
    vi.spyOn(api, 'fetchLog').mockResolvedValue(logDetail())
    const { inDrawer, click, searched } = await mountDrawer()

    expect(inDrawer('find-time')).toBeNull()
    expect(inDrawer('find-from')?.getAttribute('aria-label')).toBe(
      'Show events with from 93.184.216.34',
    )

    await click('find-from')
    await click('find-signature')

    expect(searched.mock.calls).toEqual([
      ['from:93.184.216.34'],
      ['signature:"ET SCAN Potential SSH Scan"'],
    ])
  })

  it('links to all the events with each address it names, once', async () => {
    vi.spyOn(api, 'fetchLog').mockResolvedValue(logDetail())
    const { inDrawer } = await mountDrawer()

    const links = [...(inDrawer('drawer-addresses')?.querySelectorAll('a') ?? [])]
    expect(links.map((link) => link.getAttribute('href'))).toEqual([
      '/logs?q=address:93.184.216.34',
      '/logs?q=address:192.168.1.20',
    ])
    expect(links[0]?.textContent.trim()).toBe('All events with 93.184.216.34')
  })

  it('links to an address that both ends share only once, and has none where it names none', async () => {
    vi.spyOn(api, 'fetchLog').mockResolvedValue(logDetail())
    const same = await mountDrawer({
      event: logEvent({ src_address: '10.0.0.5', dst_address: '10.0.0.5' }),
    })
    expect(same.inDrawer('drawer-addresses')?.querySelectorAll('a')).toHaveLength(1)

    same.event.value = logEvent({ id: 9, src_address: null, dst_address: null })
    await flushPromises()
    expect(same.inDrawer('drawer-addresses')).toBeNull()
  })

  describe('going to another event', () => {
    it('has buttons for the older and the newer, which are off where there is none', async () => {
      vi.spyOn(api, 'fetchLog').mockResolvedValue(logDetail())
      const { inDrawer, click, stepped, flags } = await mountDrawer()

      await click('drawer-older')
      await click('drawer-newer')
      expect(stepped.mock.calls).toEqual([['older'], ['newer']])

      flags.value = { older: false, newer: false }
      await flushPromises()
      expect(inDrawer('drawer-older')?.hasAttribute('disabled')).toBe(true)
      expect(inDrawer('drawer-newer')?.hasAttribute('disabled')).toBe(true)
    })

    it('is j for the older and k for the newer', async () => {
      vi.spyOn(api, 'fetchLog').mockResolvedValue(logDetail())
      const { press, stepped } = await mountDrawer()

      await press('j')
      await press('k')

      expect(stepped.mock.calls).toEqual([['older'], ['newer']])
    })

    it('is heard from wherever the keyboard is, as it is in the dialog itself on opening', async () => {
      vi.spyOn(api, 'fetchLog').mockResolvedValue(logDetail())
      const { stepped } = await mountDrawer()
      const box = document.querySelector('.log-drawer') as HTMLElement

      box.dispatchEvent(new KeyboardEvent('keydown', { key: 'j', bubbles: true }))
      document.body.dispatchEvent(new KeyboardEvent('keydown', { key: 'k', bubbles: true }))

      expect(stepped.mock.calls).toEqual([['older'], ['newer']])
    })

    it('is not heard while typing in a field, or once the sheet is closed', async () => {
      vi.spyOn(api, 'fetchLog').mockResolvedValue(logDetail())
      const { stepped, open } = await mountDrawer()
      const field = document.body.appendChild(document.createElement('input'))

      field.dispatchEvent(new KeyboardEvent('keydown', { key: 'j', bubbles: true }))
      expect(stepped).not.toHaveBeenCalled()

      open.value = false
      await flushPromises()
      document.body.dispatchEvent(new KeyboardEvent('keydown', { key: 'j', bubbles: true }))
      expect(stepped).not.toHaveBeenCalled()
      field.remove()
    })

    it('stops listening when it is taken away while open', async () => {
      vi.spyOn(api, 'fetchLog').mockResolvedValue(logDetail())
      const { stepped, wrapper } = await mountDrawer()

      wrapper.unmount()
      document.body.dispatchEvent(new KeyboardEvent('keydown', { key: 'j', bubbles: true }))

      expect(stepped).not.toHaveBeenCalled()
    })

    it('does not go where there is nothing, or when another key is held', async () => {
      vi.spyOn(api, 'fetchLog').mockResolvedValue(logDetail())
      const { press, stepped } = await mountDrawer({ older: false, newer: false })

      await press('j')
      await press('k')
      await press('x')
      expect(stepped).not.toHaveBeenCalled()

      const held = await mountDrawer()
      await held.press('j', { ctrlKey: true })
      await held.press('j', { metaKey: true })
      await held.press('k', { altKey: true })
      expect(held.stepped).not.toHaveBeenCalled()
    })

    it('asks for the event it is given, and drops the answer for one it has left', async () => {
      let answerFirst: (found: ReturnType<typeof logDetail>) => void = () => undefined
      const fetchLog = vi
        .spyOn(api, 'fetchLog')
        .mockReturnValueOnce(new Promise((resolve) => (answerFirst = resolve)))
        .mockResolvedValueOnce(logDetail({ raw: { which: 'second' } }))
      const { event, inDrawer } = await mountDrawer()

      event.value = second
      await flushPromises()
      answerFirst(logDetail({ raw: { which: 'first' } }))
      await flushPromises()

      expect(fetchLog.mock.calls).toEqual([[first.cursor], [second.cursor]])
      expect(inDrawer('raw-text')?.textContent).toContain('second')
      expect(inDrawer('drawer-title')?.textContent.trim()).toBe('Blocked udp')
    })
  })

  it('is closed by its button', async () => {
    vi.spyOn(api, 'fetchLog').mockResolvedValue(logDetail())
    const { click, open } = await mountDrawer()

    await click('drawer-close')

    expect(open.value).toBe(false)
  })

  it('is closed by the dialog itself, as with the Escape key', async () => {
    vi.spyOn(api, 'fetchLog').mockResolvedValue(logDetail())
    const { open } = await mountDrawer()

    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))
    await flushPromises()

    expect(open.value).toBe(false)
  })

  describe('when the event cannot be read', () => {
    it('says why, keeps what the list had, and tries again on request', async () => {
      const fetchLog = vi
        .spyOn(api, 'fetchLog')
        .mockRejectedValueOnce(new ApiError(404, "That event isn't there.", 'not_found'))
        .mockResolvedValueOnce(logDetail())
      const { inDrawer, click } = await mountDrawer()

      expect(inDrawer('drawer-error')?.textContent).toContain("That event isn't there.")
      expect(inDrawer('drawer-title')?.textContent.trim()).toBe(first.summary)
      expect(inDrawer('drawer-loading')).toBeNull()

      await click('drawer-retry')

      expect(fetchLog).toHaveBeenCalledTimes(2)
      expect(inDrawer('drawer-error')).toBeNull()
      expect(inDrawer('raw-record')).not.toBeNull()
    })

    it('drops the error of an event it has left', async () => {
      let failFirst: (error: Error) => void = () => undefined
      vi.spyOn(api, 'fetchLog')
        .mockReturnValueOnce(new Promise((_resolve, reject) => (failFirst = reject)))
        .mockResolvedValueOnce(logDetail())
      const { event, inDrawer } = await mountDrawer()

      event.value = second
      await flushPromises()
      failFirst(new Error('late'))
      await flushPromises()

      expect(inDrawer('drawer-error')).toBeNull()
    })
  })
})
